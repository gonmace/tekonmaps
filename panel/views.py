from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse

from docs import company_loader, seguimiento
from docs.models import (
    AccesoSitio,
    DocumentoEsperado,
    EmpresaLink,
    EstructuraCache,
    PlantillaEstructura,
    ProyectoFinalCache,
    ROLES_TODO_SITIO,
    SeguimientoCache,
    SiteConfig,
    SitioCache,
    SitioEstructura,
    UserProfile,
)

from .forms import (
    DocumentoEsperadoForm,
    EmpresaLinkForm,
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
        'n_empresas': EmpresaLink.objects.count(),
        'n_sitios': SiteConfig.objects.count(),
        'n_usuarios': User.objects.count(),
        'n_documentos': DocumentoEsperado.objects.count(),
        'n_plantillas': PlantillaEstructura.objects.count(),
        'n_cache': (EstructuraCache.objects.count()
                    + SitioCache.objects.count()
                    + ProyectoFinalCache.objects.count()
                    + SeguimientoCache.objects.count()),
    })


# ── Empresas (EmpresaLink) ──────────────────────────────────────────────────────
@superuser_required
def empresas(request):
    try:
        codes = [c.nombre for c in company_loader.get_all()]
    except Exception:
        codes = []
    return render(request, 'panel/empresas.html', {
        'titulo_pagina': 'Panel · Empresas',
        'seccion': 'empresas',
        'items': EmpresaLink.objects.all(),
        'codes': codes,
    })


@superuser_required
def empresa_form(request, pk=None):
    obj = get_object_or_404(EmpresaLink, pk=pk) if pk else None
    if request.method == 'POST':
        form = EmpresaLinkForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Empresa guardada.')
            return redirect('panel:empresas')
    else:
        form = EmpresaLinkForm(instance=obj)
    return render(request, 'panel/form.html', {
        'titulo_pagina': 'Panel · Empresas',
        'seccion': 'empresas',
        'form': form,
        'titulo': 'Editar empresa' if obj else 'Nueva empresa',
        'volver': 'panel:empresas',
    })


@superuser_required
def empresa_eliminar(request, pk):
    obj = get_object_or_404(EmpresaLink, pk=pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Empresa eliminada.')
    return redirect('panel:empresas')


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
    for u in User.objects.all().order_by('email', 'username'):
        profile = getattr(u, 'profile', None)
        rows.append({
            'u': u,
            'rol': profile.get_rol_display() if profile else '—',
            'sin_password': not u.has_usable_password(),
            'acceso_contratista': getattr(profile, 'acceso_contratista', False),
            'acceso_finales': getattr(profile, 'acceso_finales', False),
            'acceso_seguimiento': getattr(profile, 'acceso_seguimiento', False),
        })
    return render(request, 'panel/usuarios.html', {
        'titulo_pagina': 'Panel · Usuarios',
        'seccion': 'usuarios',
        'usuarios': rows,
    })


@superuser_required
def usuario_crear(request):
    if request.method == 'POST':
        form = UserCreateForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            u = User.objects.create_user(username=cd['email'], email=cd['email'])
            u.first_name = cd['full_name']
            u.set_unusable_password()  # el usuario crea su contraseña en el 1er ingreso
            u.is_active = True
            u.save()
            # Por defecto el usuario nuevo accede a Seguimiento (Contratista/Finales se
            # habilitan luego con los toggles de la lista).
            UserProfile.objects.update_or_create(
                user=u, defaults={'rol': cd['rol'], 'acceso_seguimiento': True})
            messages.success(request, 'Usuario creado. Creará su contraseña al ingresar.')
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
    'seguimiento': 'acceso_seguimiento',
}


@superuser_required
def usuario_toggle_acceso(request, pk, seccion):
    """Invierte el acceso del usuario a una sección del navbar (contratista/finales/seguimiento)."""
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
