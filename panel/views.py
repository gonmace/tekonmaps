from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_POST

from django.conf import settings

from docs import company_loader, nextcloud, seguimiento
from docs.models import (
    AccesoSitio,
    CarpetaRaiz,
    DocumentoEsperado,
    EstructuraCache,
    NextcloudConfig,
    PlantillaEstructura,
    ProyectoFinalCache,
    ROLES_TODO_SITIO,
    RolConfig,
    SeguimientoCache,
    SiteConfig,
    SitioCache,
    SitioEstructura,
    UserProfile,
)

from .forms import (
    CarpetaRaizForm,
    DocumentoEsperadoForm,
    NextcloudConfigForm,
    PlantillaEstructuraForm,
    SiteConfigForm,
    UserCreateForm,
    UserEditForm,
)

# Gate: solo superusuarios. Redirige al login si no lo es.
superuser_required = user_passes_test(lambda u: u.is_superuser, login_url='accounts:login')


def _invalidar_seguimiento():
    """Borra los snapshots de Seguimiento (TTL ~20 min). Se llama tras editar
    documentos del ITO para que los cambios (código, roles, etc.) se vean al instante."""
    SeguimientoCache.objects.all().delete()


def _plantilla_activa(request):
    """Plantilla seleccionada (``?plantilla=<id>`` o en el POST); la default si no hay."""
    pid = request.GET.get('plantilla') or request.POST.get('plantilla')
    if pid:
        p = PlantillaEstructura.objects.filter(pk=pid).first()
        if p:
            return p
    return PlantillaEstructura.get_default()


# ── Inicio ─────────────────────────────────────────────────────────────────────
@superuser_required
def index(request):
    return render(request, 'panel/index.html', {
        'titulo_pagina': 'Panel',
        'seccion': 'index',
        'n_empresas': CarpetaRaiz.objects.filter(es_contratista=True).count(),
        'n_sitios': SiteConfig.objects.count(),
        'n_usuarios': User.objects.count(),
        'n_documentos': DocumentoEsperado.objects.count(),
        'n_plantillas': PlantillaEstructura.objects.count(),
        'n_cache': (EstructuraCache.objects.count()
                    + SitioCache.objects.count()
                    + ProyectoFinalCache.objects.count()
                    + SeguimientoCache.objects.count()),
    })


# ── Nextcloud (NextcloudConfig + CarpetaRaiz) ───────────────────────────────────
def _invalidar_carpetas():
    """Cambiar las carpetas raíz (toggles/sync/eliminar) altera las fuentes del
    seguimiento: se purgan los snapshots y toda la caché (firmas del fast-path
    incluidas). Evento raro de administración; la próxima carga re-escanea."""
    SeguimientoCache.objects.all().delete()
    cache.clear()


@superuser_required
def nextcloud_view(request):
    row = NextcloudConfig.get()
    if row is not None:
        form = NextcloudConfigForm(instance=row)
    else:
        # Sin fila aún: se muestran los valores de .env como referencia (menos el
        # app-password, que no se expone en el HTML).
        form = NextcloudConfigForm(initial={
            'base_url': settings.NEXTCLOUD_BASE_URL,
            'usuario': settings.NEXTCLOUD_USER,
            'final_base': settings.NEXTCLOUD_FINAL_BASE,
            'templates_path': settings.NEXTCLOUD_TEMPLATES_PATH,
        })
    return render(request, 'panel/nextcloud.html', {
        'titulo_pagina': 'Panel · Nextcloud',
        'seccion': 'nextcloud',
        'form': form,
        'carpetas': CarpetaRaiz.objects.all(),
        # Resumen "qué se escaneará": carpetas con el toggle Escanear + el área ITO (fija).
        'escaneadas': CarpetaRaiz.objects.filter(escanear=True),
        'root_ito': seguimiento.ROOT_ITO.lstrip('/'),
        'configurado': nextcloud.is_configured(),
        'hay_fila': row is not None,
    })


@superuser_required
def nextcloud_credenciales(request):
    if request.method == 'POST':
        row = NextcloudConfig.get() or NextcloudConfig()
        form = NextcloudConfigForm(request.POST, instance=row)
        if form.is_valid():
            form.save()
            cache.delete(nextcloud.CONFIG_CACHE_KEY)
            messages.success(request, 'Configuración de Nextcloud guardada.')
        else:
            messages.error(request, 'Revisa los campos de la configuración.')
    return redirect('panel:nextcloud')


@superuser_required
def nextcloud_probar(request):
    """Prueba la conexión WebDAV con la config efectiva (BD > .env). JSON."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST requerido'}, status=405)
    try:
        items = nextcloud.list_folder('/')
        return JsonResponse({'ok': True, 'carpetas': sum(1 for i in items if i['es_dir'])})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)})


@superuser_required
def nextcloud_sincronizar(request):
    """Trae las carpetas raíz ``/20*`` de Nextcloud y crea las filas que falten en
    ``CarpetaRaiz`` (nunca borra: las carpetas desaparecidas se eliminan a mano)."""
    if request.method != 'POST':
        return redirect('panel:nextcloud')
    import re as _re
    ito_name = seguimiento.ROOT_ITO.lstrip('/')
    try:
        items = [it['nombre'] for it in nextcloud.list_folder('/')
                 if it['es_dir'] and it['nombre'].startswith('20')]
    except Exception as e:
        messages.error(request, f'No se pudo listar Nextcloud: {e}')
        return redirect('panel:nextcloud')
    # Dedup de montajes duplicados ('20 AJ (2)' == '20 AJ') y exclusión del área ITO.
    nombres = {_re.sub(r'\s*\(\d+\)$', '', n) for n in items}
    nombres.discard(ito_name)
    nuevas = 0
    for nombre in sorted(nombres):
        _, creada = CarpetaRaiz.objects.get_or_create(
            carpeta=nombre,
            defaults={'codigo': _re.sub(r'^20[\s\-_]*', '', nombre), 'escanear': True})
        nuevas += int(creada)
    if nuevas:
        _invalidar_carpetas()
    messages.success(request, f'Sincronizado: {nuevas} carpeta(s) nueva(s) de {len(nombres)}.')
    return redirect('panel:nextcloud')


@superuser_required
def nextcloud_carpetas_disponibles(request):
    """GET → JSON: carpetas raíz de Nextcloud que aún NO están configuradas (para el
    modal «Agregar carpeta»). Excluye el área ITO y deduplica montajes ' (N)'."""
    import re as _re
    try:
        items = [it['nombre'] for it in nextcloud.list_folder('/') if it['es_dir']]
    except Exception as e:
        return JsonResponse({'error': str(e), 'carpetas': []})
    nombres = {_re.sub(r'\s*\(\d+\)$', '', n) for n in items}
    nombres.discard(seguimiento.ROOT_ITO.lstrip('/'))
    existentes = set(CarpetaRaiz.objects.values_list('carpeta', flat=True))
    return JsonResponse({'carpetas': sorted(nombres - existentes)})


@superuser_required
def carpeta_crear(request):
    """POST: agrega una carpeta raíz a la configuración (quedará escaneada). Recibe
    ``carpeta`` (nombre exacto en la raíz de Nextcloud, del modal o escrito a mano)."""
    if request.method == 'POST':
        import re as _re
        nombre = (request.POST.get('carpeta') or '').strip().strip('/')
        if not nombre or '/' in nombre:
            messages.error(request, 'Nombre de carpeta inválido.')
        else:
            _, creada = CarpetaRaiz.objects.get_or_create(
                carpeta=nombre,
                defaults={'codigo': _re.sub(r'^20[\s\-_]*', '', nombre), 'escanear': True})
            if creada:
                _invalidar_carpetas()
                messages.success(request, f'Carpeta «{nombre}» agregada: se escaneará.')
            else:
                messages.info(request, f'La carpeta «{nombre}» ya estaba configurada.')
    return redirect('panel:nextcloud')


_CARPETA_CAMPOS = {'escanear': 'escanear', 'contratista': 'es_contratista'}


@superuser_required
def carpeta_toggle(request, pk, campo):
    c = get_object_or_404(CarpetaRaiz, pk=pk)
    field = _CARPETA_CAMPOS.get(campo)
    if request.method == 'POST' and field:
        setattr(c, field, not getattr(c, field))
        c.save(update_fields=[field])
        _invalidar_carpetas()
    return redirect('panel:nextcloud')


@superuser_required
def carpeta_form(request, pk):
    obj = get_object_or_404(CarpetaRaiz, pk=pk)
    if request.method == 'POST':
        form = CarpetaRaizForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            _invalidar_carpetas()
            messages.success(request, 'Carpeta guardada.')
            return redirect('panel:nextcloud')
    else:
        form = CarpetaRaizForm(instance=obj)
    return render(request, 'panel/form.html', {
        'titulo_pagina': 'Panel · Nextcloud',
        'seccion': 'nextcloud',
        'form': form,
        'titulo': f'Editar carpeta «{obj.carpeta}»',
        'volver': 'panel:nextcloud',
    })


@superuser_required
def carpeta_eliminar(request, pk):
    obj = get_object_or_404(CarpetaRaiz, pk=pk)
    if request.method == 'POST':
        obj.delete()
        _invalidar_carpetas()
        messages.success(request, 'Carpeta eliminada de la configuración (Nextcloud no se toca).')
    return redirect('panel:nextcloud')


# ── Docs. Finales (SiteConfig) ───────────────────────────────────────────────────
@superuser_required
def sitios(request):
    return render(request, 'panel/sitios.html', {
        'titulo_pagina': 'Panel · Docs. Finales',
        'seccion': 'sitios',
        'items': SiteConfig.objects.all(),
    })


@superuser_required
def sitio_form(request, pk=None):
    obj = get_object_or_404(SiteConfig, pk=pk) if pk else None
    if request.method == 'POST':
        form = SiteConfigForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Configuración guardada.')
            return redirect('panel:sitios')
    else:
        form = SiteConfigForm(instance=obj)
    return render(request, 'panel/form.html', {
        'titulo_pagina': 'Panel · Docs. Finales',
        'seccion': 'sitios',
        'form': form,
        'titulo': 'Editar configuración' if obj else 'Nueva configuración',
        'volver': 'panel:sitios',
    })


@superuser_required
def sitio_eliminar(request, pk):
    obj = get_object_or_404(SiteConfig, pk=pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Configuración eliminada.')
    return redirect('panel:sitios')


# ── Documentos del ITO (DocumentoEsperado), scoped por plantilla ─────────────────
@superuser_required
def documentos(request):
    plantilla = _plantilla_activa(request)
    return render(request, 'panel/documentos.html', {
        'titulo_pagina': 'Panel · Docs. ITO',
        'seccion': 'documentos',
        'items': DocumentoEsperado.objects.filter(plantilla=plantilla),
        'plantilla': plantilla,
        'plantillas': PlantillaEstructura.objects.all(),
    })


@superuser_required
def documento_form(request, pk=None):
    obj = get_object_or_404(DocumentoEsperado, pk=pk) if pk else None
    # Plantilla destino: la del documento (al editar) o la activa (al crear).
    plantilla = obj.plantilla if obj else _plantilla_activa(request)
    # AJAX (modal desde Seguimiento): GET ?partial=1 devuelve solo los campos;
    # POST con cabecera XMLHttpRequest devuelve JSON en vez de redirigir.
    es_ajax = (request.headers.get('x-requested-with') == 'XMLHttpRequest'
               or request.GET.get('partial'))
    if request.method == 'POST':
        form = DocumentoEsperadoForm(request.POST, instance=obj)
        if form.is_valid():
            nuevo = form.save(commit=False)
            nuevo.plantilla = plantilla  # la fija la vista, no el usuario
            nuevo.save()
            _invalidar_seguimiento()
            if es_ajax:
                return JsonResponse({'ok': True})
            messages.success(request, 'Documento guardado.')
            return redirect(f"{reverse('panel:documentos')}?plantilla={plantilla.id}")
        if es_ajax:
            html = render_to_string('panel/_documento_form_fields.html', {'form': form}, request)
            return JsonResponse({'ok': False, 'html': html}, status=400)
    else:
        form = DocumentoEsperadoForm(instance=obj)
    if es_ajax:
        html = render_to_string('panel/_documento_form_fields.html', {'form': form}, request)
        return JsonResponse({'ok': True, 'html': html})
    return render(request, 'panel/form.html', {
        'titulo_pagina': 'Panel · Docs. ITO',
        'seccion': 'documentos',
        'form': form,
        'titulo': 'Editar documento' if obj else 'Nuevo documento',
        'subtitulo': f'Plantilla: {plantilla.nombre}',
        'volver': 'panel:documentos',
    })


@superuser_required
def documento_eliminar(request, pk):
    obj = get_object_or_404(DocumentoEsperado, pk=pk)
    plantilla_id = obj.plantilla_id
    if request.method == 'POST':
        obj.delete()
        _invalidar_seguimiento()
        messages.success(request, 'Documento eliminado.')
    return redirect(f"{reverse('panel:documentos')}?plantilla={plantilla_id}")


@superuser_required
def documento_toggle_obligatorio(request, pk):
    obj = get_object_or_404(DocumentoEsperado, pk=pk)
    if request.method == 'POST':
        obj.obligatorio = not obj.obligatorio
        obj.save(update_fields=['obligatorio'])
        _invalidar_seguimiento()
    return redirect(f"{reverse('panel:documentos')}?plantilla={obj.plantilla_id}")


@superuser_required
def documentos_roles(request):
    """Matriz editable documento × rol (de una plantilla): un selector de acción por celda."""
    plantilla = _plantilla_activa(request)
    qs = DocumentoEsperado.objects.filter(plantilla=plantilla)
    campos = [c for c, _, _ in DocumentoEsperado.ROLES]
    acciones_validas = {a for a, _ in DocumentoEsperado.ACCION_CHOICES}
    if request.method == 'POST':
        n = 0
        for d in qs:
            cambiado = False
            for campo in campos:
                val = request.POST.get(f'doc_{d.id}_{campo}', '').strip()
                if val and val not in acciones_validas:
                    continue
                if val != getattr(d, campo):
                    setattr(d, campo, val)
                    cambiado = True
            if cambiado:
                d.save(update_fields=campos)
                n += 1
        if n:
            _invalidar_seguimiento()
        messages.success(request, f'Responsabilidades actualizadas ({n} documento(s)).')
        return redirect(f"{reverse('panel:documentos_roles')}?plantilla={plantilla.id}")

    filas = []
    for d in qs:
        celdas = [{'name': f'doc_{d.id}_{campo}', 'actual': getattr(d, campo)}
                  for campo in campos]
        filas.append({'doc': d, 'celdas': celdas})
    return render(request, 'panel/roles_matriz.html', {
        'titulo_pagina': 'Panel · Responsabilidades',
        'seccion': 'documentos',
        'filas': filas,
        'plantilla': plantilla,
        'roles': DocumentoEsperado.ROLES,
        'acciones': DocumentoEsperado.ACCION_CHOICES,
    })


# ── Estructuras (PlantillaEstructura) y asignación a sitios ───────────────────────
@superuser_required
def estructuras(request):
    plantillas = list(PlantillaEstructura.objects.all())
    # Conteos por plantilla (documentos y sitios que la usan).
    for p in plantillas:
        p.n_documentos = p.documentos.count()
        p.n_sitios = p.sitios.count()
    # Asignación de sitios: lista los sitios reales y su plantilla actual.
    asignadas = {(s.empresa, s.sitio): s.plantilla_id
                 for s in SitioEstructura.objects.all()}
    default = PlantillaEstructura.get_default()
    sitios = []
    for row in seguimiento.listar_sitios():
        pid = asignadas.get((row['empresa'], row['sitio']), default.id)
        sitios.append({'empresa': row['empresa'], 'sitio': row['sitio'], 'plantilla_id': pid})
    return render(request, 'panel/estructuras.html', {
        'titulo_pagina': 'Panel · Estructuras',
        'seccion': 'estructuras',
        'plantillas': plantillas,
        'sitios': sitios,
        'default_id': default.id,
    })


@superuser_required
def plantilla_form(request, pk=None):
    obj = get_object_or_404(PlantillaEstructura, pk=pk) if pk else None
    if request.method == 'POST':
        form = PlantillaEstructuraForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Plantilla guardada.')
            return redirect('panel:estructuras')
    else:
        form = PlantillaEstructuraForm(instance=obj)
    return render(request, 'panel/form.html', {
        'titulo_pagina': 'Panel · Estructuras',
        'seccion': 'estructuras',
        'form': form,
        'titulo': 'Editar plantilla' if obj else 'Nueva plantilla',
        'volver': 'panel:estructuras',
    })


@superuser_required
def plantilla_clonar(request, pk):
    """Guardar como: crea una plantilla nueva copiando todos los documentos de la origen."""
    origen = get_object_or_404(PlantillaEstructura, pk=pk)
    if request.method == 'POST':
        nombre = (request.POST.get('nombre') or '').strip()
        if not nombre:
            messages.error(request, 'Indica un nombre para la nueva plantilla.')
        elif PlantillaEstructura.objects.filter(nombre__iexact=nombre).exists():
            messages.error(request, 'Ya existe una plantilla con ese nombre.')
        else:
            nueva = PlantillaEstructura.objects.create(
                nombre=nombre, descripcion=origen.descripcion)
            campos = ['etapa', 'carpeta', 'nombre', 'codigo', 'tipo_esperado',
                      'obligatorio', 'orden', 'activo'] + [c for c, _, _ in DocumentoEsperado.ROLES]
            for d in origen.documentos.all():
                DocumentoEsperado.objects.create(
                    plantilla=nueva, **{c: getattr(d, c) for c in campos})
            messages.success(request, f'Plantilla «{nueva.nombre}» creada desde «{origen.nombre}».')
            return redirect(f"{reverse('panel:documentos')}?plantilla={nueva.id}")
    return redirect('panel:estructuras')


@superuser_required
def plantilla_default(request, pk):
    obj = get_object_or_404(PlantillaEstructura, pk=pk)
    if request.method == 'POST':
        PlantillaEstructura.objects.filter(es_default=True).update(es_default=False)
        obj.es_default = True
        obj.save(update_fields=['es_default'])
        _invalidar_seguimiento()  # cambian los sitios sin asignación explícita
        messages.success(request, f'«{obj.nombre}» es ahora la plantilla por defecto.')
    return redirect('panel:estructuras')


@superuser_required
def plantilla_eliminar(request, pk):
    obj = get_object_or_404(PlantillaEstructura, pk=pk)
    if request.method == 'POST':
        if obj.es_default:
            messages.error(request, 'No se puede eliminar la plantilla por defecto.')
        elif obj.sitios.exists():
            messages.error(
                request, 'No se puede eliminar: hay sitios usando esta plantilla. '
                'Reasígnalos a otra plantilla primero.')
        else:
            obj.delete()
            _invalidar_seguimiento()
            messages.success(request, 'Plantilla eliminada.')
    return redirect('panel:estructuras')


@superuser_required
def estructura_asignar(request):
    """Asigna plantillas a sitios (un select por sitio). Asignar la default elimina la
    fila (el sitio vuelve a 'sin asignación')."""
    if request.method == 'POST':
        default = PlantillaEstructura.get_default()
        validas = set(PlantillaEstructura.objects.values_list('id', flat=True))
        n = 0
        for key, val in request.POST.items():
            if not key.startswith('sitio_'):
                continue
            # name = sitio_<empresa>|<sitio>
            try:
                empresa, sitio = key[len('sitio_'):].split('|', 1)
                pid = int(val)
            except (ValueError, IndexError):
                continue
            if pid not in validas:
                continue
            if pid == default.id:
                SitioEstructura.objects.filter(empresa=empresa, sitio=sitio).delete()
            else:
                SitioEstructura.objects.update_or_create(
                    empresa=empresa, sitio=sitio,
                    defaults={'plantilla_id': pid})
            seguimiento.invalidar_cache(empresa, sitio)
            n += 1
        messages.success(request, f'Asignaciones actualizadas ({n} sitio(s)).')
    return redirect('panel:estructuras')


# ── Usuarios y roles ─────────────────────────────────────────────────────────────
@superuser_required
def usuarios(request):
    rows = []
    for u in User.objects.all().order_by('email', 'username').prefetch_related('sitios_permitidos'):
        profile = getattr(u, 'profile', None)
        rows.append({
            'u': u,
            'rol': profile.get_rol_display() if profile else '—',
            'sin_password': not u.has_usable_password(),
            'acceso_contratista': getattr(profile, 'acceso_contratista', False),
            'acceso_finales': getattr(profile, 'acceso_finales', False),
            'acceso_proyectos': getattr(profile, 'acceso_proyectos', False),
            # Sitios asignados (vacío si ve todo). Coordinador/TK Redline y superusuario ven todo.
            've_todo': u.is_superuser or bool(profile and profile.rol in ROLES_TODO_SITIO),
            'sitios': sorted(f"{a.empresa} / {a.sitio}" for a in u.sitios_permitidos.all()),
        })
    return render(request, 'panel/usuarios.html', {
        'titulo_pagina': 'Panel · Usuarios',
        'seccion': 'usuarios',
        'usuarios': rows,
        'roles_responsables': _roles_responsables(),
    })


def _roles_responsables():
    """``[{rol, nombre, activo}]``: qué roles se ofrecen como responsable de pendientes."""
    off = set(RolConfig.objects.filter(responsable_pendientes=False).values_list('rol', flat=True))
    return [{'rol': r, 'nombre': n, 'activo': r not in off} for r, n in UserProfile.ROL_CHOICES]


@superuser_required
@require_POST
def roles_responsables(request):
    """Guarda qué roles pueden ser responsables de un pendiente (casillas ``rol``)."""
    marcados = set(request.POST.getlist('rol'))
    for rol, _n in UserProfile.ROL_CHOICES:
        RolConfig.objects.update_or_create(
            rol=rol, defaults={'responsable_pendientes': rol in marcados})
    messages.success(request, 'Roles elegibles como responsable de pendientes actualizados.')
    return redirect('panel:usuarios')


def _enviar_invitacion(request, u):
    """Correo de bienvenida con el enlace de ingreso. En el primer ingreso (cuenta sin
    contraseña usable) la propia pantalla de login pide crearla. Devuelve True si se envió."""
    from django.core.mail import send_mail
    url = request.build_absolute_uri(reverse('accounts:login'))
    nombre = (u.first_name or u.email or u.username).strip()
    cuerpo = (
        f'Hola {nombre},\n\n'
        'Se creó tu cuenta en Tk Redline.\n\n'
        f'1. Ingresa a: {url}\n'
        f'2. Escribe tu correo ({u.email or u.username}).\n'
        '3. Crea tu contraseña y listo.\n\n'
        'Si no esperabas este correo, ignóralo.\n')
    try:
        send_mail('Tu acceso a Tk Redline', cuerpo, None, [u.email or u.username],
                  fail_silently=False)
        return True
    except Exception:
        return False


@superuser_required
def usuario_invitar(request, pk):
    """Reenvía el correo de ingreso a un usuario que aún no creó su contraseña."""
    u = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        if u.is_superuser or not u.is_active or u.has_usable_password():
            messages.error(request, 'Ese usuario ya tiene contraseña o no puede recibir la invitación.')
        elif _enviar_invitacion(request, u):
            messages.success(request, f'Correo enviado a {u.email or u.username}.')
        else:
            messages.error(request, 'No se pudo enviar el correo. Revisa la configuración de correo.')
    return redirect('panel:usuarios')


@superuser_required
def usuario_crear(request):
    if request.method == 'POST':
        form = UserCreateForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            u = User.objects.create_user(username=cd['email'], email=cd['email'])
            u.first_name = cd['full_name']
            if cd['modo_acceso'] == 'password':
                u.set_password(cd['password'])
            else:
                u.set_unusable_password()  # el usuario crea su contraseña en el 1er ingreso
            u.is_active = True
            u.save()
            # Privilegios elegidos en el formulario (por defecto solo «Seguimiento»).
            UserProfile.objects.update_or_create(user=u, defaults={
                'rol': cd['rol'],
                'acceso_contratista': cd['acceso_contratista'],
                'acceso_finales': cd['acceso_finales'],
                'acceso_proyectos': cd['acceso_proyectos'],
            })
            if cd['modo_acceso'] == 'password':
                messages.success(request, 'Usuario creado con la contraseña indicada.')
            elif _enviar_invitacion(request, u):
                messages.success(request, f'Usuario creado. Se envió un correo a {cd["email"]} '
                                          'para que ingrese y cree su contraseña.')
            else:
                messages.warning(request, 'Usuario creado, pero no se pudo enviar el correo. '
                                          'Puede ingresar con su correo y crear su contraseña, '
                                          'o reenviar la invitación desde la lista.')
            if cd['rol'] not in ROLES_TODO_SITIO:
                # Siguiente paso: asignarle los sitios que puede ver (restrictivo por defecto).
                messages.info(request, 'Asigna ahora los sitios que podrá ver.')
                return redirect('panel:usuario_sitios', pk=u.pk)
            return redirect('panel:usuarios')
    else:
        form = UserCreateForm()
    return render(request, 'panel/form.html', {
        'titulo_pagina': 'Panel · Usuarios',
        'seccion': 'usuarios',
        'form': form,
        'titulo': 'Nuevo usuario',
        'volver': 'panel:usuarios',
    })


@superuser_required
def usuario_editar(request, pk):
    u = get_object_or_404(User, pk=pk)
    profile, _ = UserProfile.objects.get_or_create(user=u)
    if request.method == 'POST':
        form = UserEditForm(request.POST, user_pk=u.pk)
        if form.is_valid():
            cd = form.cleaned_data
            profile.rol = cd['rol']
            profile.acceso_contratista = cd['acceso_contratista']
            profile.acceso_finales = cd['acceso_finales']
            profile.acceso_proyectos = cd['acceso_proyectos']
            profile.save()
            u.first_name = cd['full_name']
            u.email = cd['email']
            u.username = cd['email']
            u.is_active = cd['is_active']
            if cd.get('requerir_password'):
                u.set_unusable_password()
            elif cd.get('password'):
                u.set_password(cd['password'])
            u.save()
            messages.success(request, 'Usuario actualizado.')
            return redirect('panel:usuarios')
    else:
        form = UserEditForm(initial={
            'full_name': u.first_name,
            'email': u.email or u.username,
            'rol': profile.rol,
            'is_active': u.is_active,
            'acceso_contratista': profile.acceso_contratista,
            'acceso_finales': profile.acceso_finales,
            'acceso_proyectos': profile.acceso_proyectos,
        }, user_pk=u.pk)
    return render(request, 'panel/form.html', {
        'titulo_pagina': 'Panel · Usuarios',
        'seccion': 'usuarios',
        'form': form,
        'titulo': 'Editar usuario',
        'subtitulo': u.email or u.username,
        'volver': 'panel:usuarios',
    })


@superuser_required
def usuario_toggle_activo(request, pk):
    u = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        if u == request.user:
            messages.error(request, 'No puedes deshabilitar tu propio usuario.')
        elif u.is_superuser:
            messages.error(request, 'No se puede deshabilitar un superusuario.')
        else:
            u.is_active = not u.is_active
            u.save(update_fields=['is_active'])
            messages.success(
                request, f'Usuario {"habilitado" if u.is_active else "deshabilitado"}.')
    return redirect('panel:usuarios')


_ACCESO_CAMPOS = {
    'contratista': 'acceso_contratista',
    'finales': 'acceso_finales',
    'proyectos': 'acceso_proyectos',
}


@superuser_required
def usuario_toggle_acceso(request, pk, seccion):
    """Invierte el acceso del usuario a una sección del navbar (contratista/finales/proyectos).
    «Seguimiento old» no se asigna: es solo del superusuario."""
    u = get_object_or_404(User, pk=pk)
    campo = _ACCESO_CAMPOS.get(seccion)
    if request.method == 'POST' and campo:
        if u.is_superuser:
            messages.error(request, 'El superusuario ya tiene acceso a todo.')
        else:
            profile, _ = UserProfile.objects.get_or_create(user=u)
            setattr(profile, campo, not getattr(profile, campo))
            profile.save(update_fields=[campo])
    return redirect('panel:usuarios')


@superuser_required
def usuario_impersonar(request, pk):
    """Inicia la impersonación: la app pasa a verse como el usuario objetivo (banner
    con «Volver» en el header). Solo superusuario; nunca sobre otro superusuario."""
    from accounts.middleware import IMPERSONATE_SESSION_KEY
    from accounts.views import _landing
    u = get_object_or_404(User, pk=pk)
    if request.method != 'POST':
        return redirect('panel:usuarios')
    if u.is_superuser or u == request.user:
        messages.error(request, 'No se puede impersonar a un superusuario.')
        return redirect('panel:usuarios')
    if not u.is_active:
        messages.error(request, 'El usuario está deshabilitado.')
        return redirect('panel:usuarios')
    request.session[IMPERSONATE_SESSION_KEY] = u.pk
    return redirect(_landing(u))


@superuser_required
def usuario_eliminar(request, pk):
    u = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        if u == request.user:
            messages.error(request, 'No puedes eliminar tu propio usuario.')
        elif u.is_superuser:
            messages.error(request, 'No se puede eliminar un superusuario.')
        else:
            u.delete()
            messages.success(request, 'Usuario eliminado.')
    return redirect('panel:usuarios')


# ── Accesos por sitio ────────────────────────────────────────────────────────────
@superuser_required
def accesos(request):
    """Lista de usuarios (no superusuarios) con su conteo de sitios asignados."""
    rows = []
    for u in User.objects.filter(is_superuser=False).order_by('email', 'username'):
        profile = getattr(u, 'profile', None)
        rows.append({
            'u': u,
            'rol': profile.get_rol_display() if profile else '—',
            'n_sitios': u.sitios_permitidos.count(),
            # Coordinador / TK Redline ven todos los sitios; no requieren asignación.
            've_todo': bool(profile and profile.rol in ROLES_TODO_SITIO),
        })
    return render(request, 'panel/accesos.html', {
        'titulo_pagina': 'Panel · Accesos',
        'seccion': 'accesos',
        'usuarios': rows,
    })


@superuser_required
def usuario_sitios(request, pk):
    """Página de asignación de sitios para un usuario. Los sitios se cargan por AJAX
    desde docs:api_sitios; los ya asignados se pasan como JSON {empresa: [sitios]}."""
    import json
    u = get_object_or_404(User, pk=pk, is_superuser=False)
    asignados = {}
    for a in u.sitios_permitidos.all():
        asignados.setdefault(a.empresa, []).append(a.sitio)
    profile = getattr(u, 'profile', None)
    return render(request, 'panel/accesos_usuario.html', {
        'titulo_pagina': 'Panel · Accesos',
        'seccion': 'accesos',
        'u': u,
        've_todo': bool(profile and profile.rol in ROLES_TODO_SITIO),
        'empresas': company_loader.get_all(),
        'asignados_json': json.dumps(asignados),
        'api_sitios_url': reverse('docs:api_sitios'),
    })


@superuser_required
def usuario_sitios_guardar(request, pk):
    """Sincroniza AccesoSitio para (user, empresa) con los sitios marcados."""
    u = get_object_or_404(User, pk=pk, is_superuser=False)
    if request.method == 'POST':
        empresa = (request.POST.get('empresa') or '').strip()
        if empresa:
            seleccionados = set(request.POST.getlist('sitio'))
            existentes = set(
                AccesoSitio.objects.filter(user=u, empresa=empresa)
                .values_list('sitio', flat=True))
            for sitio in seleccionados - existentes:
                AccesoSitio.objects.create(user=u, empresa=empresa, sitio=sitio)
            AccesoSitio.objects.filter(
                user=u, empresa=empresa,
                sitio__in=existentes - seleccionados).delete()
            messages.success(
                request,
                f'Accesos de {empresa} actualizados ({len(seleccionados)} sitio(s)).')
    return redirect('panel:usuario_sitios', pk=u.pk)


# ── Cachés ───────────────────────────────────────────────────────────────────────
@superuser_required
def caches(request):
    if request.method == 'POST':
        target = request.POST.get('target')
        if target == 'estructura':
            EstructuraCache.objects.all().delete()
        elif target == 'sitios':
            SitioCache.objects.all().delete()
        elif target == 'proyectos':
            ProyectoFinalCache.objects.all().delete()
        elif target == 'seguimiento':
            SeguimientoCache.objects.all().delete()
        elif target == 'todo':
            EstructuraCache.objects.all().delete()
            SitioCache.objects.all().delete()
            ProyectoFinalCache.objects.all().delete()
            SeguimientoCache.objects.all().delete()
            cache.clear()
        messages.success(request, 'Caché limpiada. Se regenerará en la próxima visita.')
        return redirect('panel:caches')
    return render(request, 'panel/caches.html', {
        'titulo_pagina': 'Panel · Cachés',
        'seccion': 'caches',
        'estructura': EstructuraCache.objects.all(),
        'sitios': SitioCache.objects.all().order_by('empresa', 'sitio'),
        'proyectos': ProyectoFinalCache.objects.all().order_by('nombre'),
        'seguimiento': SeguimientoCache.objects.all().order_by('sitio'),
    })
