import hashlib
import json
import os
from datetime import date, time

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Prefetch
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from docs import company_loader, nextcloud, seguimiento
from docs.views import (_denegar_sitio, _empresas_permitidas, _es_admin, _es_coordinador,
                        _gate_api, _guard_seccion, _sitios_permitidos)

from . import calendario, servicios
from .models import (ETAPAS, ESTADO_PROYECTO, Etapa, Imagen, Nota, Pendiente,
                     Proyecto)

SECCION = "acceso_proyectos"
# Carpeta raíz «Docs. ITO» de la sección: está al mismo nivel que las `/20 <EMPRESA>` y
# contiene una subcarpeta por sitio. (Distinta del área de subidas /20-ITO_SEGUIMIENTO.)
ROOT_ITO_INTERNO = "/20-ITO INTERNO"


def _body(request):
    try:
        return json.loads(request.body or b"{}")
    except ValueError:
        return {}


def _err(msg, status=400):
    return JsonResponse({"error": msg}, status=status)


def _hora(txt):
    """``"HH:MM"`` → ``time`` o None."""
    try:
        return time.fromisoformat(txt) if txt else None
    except ValueError:
        return None


def _fecha(txt):
    try:
        return date.fromisoformat(txt) if txt else None
    except ValueError:
        return None


def _etapa_o_403(request, etapa_id, escritura=True):
    """Devuelve ``(etapa, None)`` o ``(None, JsonResponse)`` aplicando sección, rol y sitio."""
    denied = _gate_api(request.user, SECCION)
    if denied:
        return None, denied
    if escritura and not _es_admin(request.user):
        return None, _err("Solo lectura.", 403)
    etapa = get_object_or_404(Etapa.objects.select_related("proyecto"), pk=etapa_id)
    denied = _denegar_sitio(request.user, etapa.proyecto.empresa, etapa.proyecto.sitio)
    if denied:
        return None, denied
    if not etapa.proyecto.activo:
        return None, _err("El proyecto no está habilitado para seguimiento.", 403)
    return etapa, None


def _proyecto_activo(empresa, sitio):
    return Proyecto.objects.filter(empresa=empresa, sitio=sitio, activo=True).first()


def _serializar(proyecto, user):
    from django.urls import reverse
    etapas = []
    qs = (proyecto.etapas.filter(etapa__in=[c for c, _ in ETAPAS])
          .prefetch_related(
              Prefetch("pendientes", queryset=Pendiente.objects.filter(eliminado_en__isnull=True)
                       .select_related("responsable_user")),
              "imagenes",
              Prefetch("notas", queryset=Nota.objects.filter(eliminado_en__isnull=True)
                       .select_related("usuario")))
          .select_related("actualizado_por"))
    for e in qs:
        etapas.append({
            "id": e.pk, "etapa": e.etapa, "nombre": e.get_etapa_display(),
            "estado": e.estado, "estado_display": e.get_estado_display(),
            "pendientes": [{
                "id": p.pk, "titulo": p.titulo, "fecha": p.fecha.isoformat() if p.fecha else "",
                "hora": p.hora.strftime("%H:%M") if p.hora else "",
                "responsable": servicios.responsable_nombre(p),
                "responsable_id": p.responsable_user_id, "prioridad": p.prioridad,
                "hecho": p.hecho,
            } for p in e.pendientes.all()],
            "imagenes": [{
                "id": i.pk, "url": reverse("proyectos:imagen_ver", args=[i.pk]),
                "descripcion": i.descripcion, "fecha": i.fecha.isoformat(),
                "usuario": i.subido_por.username if i.subido_por else "",
                "puede_borrar": _puede_borrar(user, i.subido_por_id),
            } for i in e.imagenes.all()],
            "notas": [{
                "id": n.pk, "texto": n.texto, "fecha": n.fecha.isoformat(),
                "usuario": n.usuario.username if n.usuario else "",
                "puede_borrar": _puede_borrar(user, n.usuario_id),
            } for n in e.notas.all()],
        })
    emp = next((e for e in company_loader.get_all() if e.nombre == proyecto.empresa), None)
    return {
        # Nombre de las carpetas raíz en Nextcloud (títulos de las secciones de archivos).
        "carpetas": {"contratista": emp.carpeta_nextcloud if emp else "Docs. Contratista",
                     "ito": ROOT_ITO_INTERNO.lstrip("/")},
        "estado": proyecto.estado, "estado_display": proyecto.get_estado_display(),
        "lat": proyecto.lat, "lon": proyecto.lon,
        "itos": [{"id": u.pk, "nombre": servicios.nombre_usuario(u)}
                 for u in servicios.itos_asignados(proyecto.empresa, proyecto.sitio)],
        # Usuarios elegibles como responsable de un pendiente (además del texto libre).
        "responsables": [{"id": u.pk, "nombre": servicios.nombre_usuario(u)}
                         for u in servicios.responsables_posibles()],
        "actualizado": proyecto.actualizado.isoformat(), "etapas": etapas,
    }


def _puede_cambiar_estado(user):
    """El estado del proyecto lo fijan el superusuario y los roles que ven todos los sitios
    (Coordinador, TK Redline); el ITO u otras funciones solo lo ven."""
    from docs.models import ROLES_TODO_SITIO
    from docs.views import _get_user_rol
    return user.is_superuser or _get_user_rol(user) in ROLES_TODO_SITIO


def _puede_borrar(user, autor_id):
    return _es_coordinador(user) or (autor_id is not None and autor_id == user.pk)


@login_required
def index(request):
    guard = _guard_seccion(request, SECCION)
    if guard:
        return guard
    empresas = company_loader.get_all()
    permitidas = _empresas_permitidas(request.user)
    if permitidas is not None:
        empresas = [e for e in empresas if e.nombre in permitidas]
    return render(request, "proyectos/seguimiento.html", {
        "titulo_pagina": "Seguimiento",
        "empresas": empresas,
        "es_admin": _es_admin(request.user),
        "es_superuser": request.user.is_superuser,
        "puede_estado": _puede_cambiar_estado(request.user),
        "estados_proyecto": ESTADO_PROYECTO,
    })


@login_required
@require_GET
def api_proyecto(request):
    denied = _gate_api(request.user, SECCION)
    if denied:
        return denied
    empresa = request.GET.get("empresa", "")
    sitio = request.GET.get("sitio", "")
    if not empresa or not sitio:
        return _err("Faltan empresa/sitio.")
    denied = _denegar_sitio(request.user, empresa, sitio)
    if denied:
        return denied
    proyecto = _proyecto_activo(empresa, sitio)
    if not proyecto:
        return _err("El proyecto no está habilitado para seguimiento.", 404)
    return JsonResponse(_serializar(proyecto, request.user))


@login_required
@require_POST
def api_proyecto_estado(request):
    denied = _gate_api(request.user, SECCION)
    if denied:
        return denied
    if not _puede_cambiar_estado(request.user):
        return _err("No tienes permiso para cambiar el estado del proyecto.", 403)
    d = _body(request)
    denied = _denegar_sitio(request.user, d.get("empresa", ""), d.get("sitio", ""))
    if denied:
        return denied
    proyecto = _proyecto_activo(d.get("empresa", ""), d.get("sitio", ""))
    if not proyecto:
        return _err("El proyecto no está habilitado para seguimiento.", 404)
    try:
        servicios.cambiar_estado_proyecto(proyecto, d.get("estado"), request.user)
    except servicios.ReglaEtapa as ex:
        return _err(str(ex))
    servicios.registrar(proyecto, "estado", f"Estado: {proyecto.get_estado_display()}", request.user)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def api_proyecto_ubicacion(request):
    denied = _gate_api(request.user, SECCION)
    if denied:
        return denied
    if not _es_admin(request.user):
        return _err("Solo lectura.", 403)
    d = _body(request)
    denied = _denegar_sitio(request.user, d.get("empresa", ""), d.get("sitio", ""))
    if denied:
        return denied
    proyecto = _proyecto_activo(d.get("empresa", ""), d.get("sitio", ""))
    if not proyecto:
        return _err("El proyecto no está habilitado para seguimiento.", 404)
    try:
        servicios.fijar_ubicacion(proyecto, d.get("lat"), d.get("lon"), request.user)
    except servicios.ReglaEtapa as ex:
        return _err(str(ex))
    servicios.registrar(proyecto, "ubicacion",
                        "Ubicación fijada" if proyecto.lat is not None else "Ubicación quitada",
                        request.user)
    return JsonResponse({"ok": True, "lat": proyecto.lat, "lon": proyecto.lon})


def _proyectos_visibles(user, empresa=""):
    """Proyectos habilitados que el usuario puede ver (todas las empresas si no se indica)."""
    qs = Proyecto.objects.filter(activo=True)
    if empresa:
        qs = qs.filter(empresa=empresa)
    cache_permisos = {}
    out = []
    for p in qs.order_by("empresa", "sitio"):
        if p.empresa not in cache_permisos:
            cache_permisos[p.empresa] = _sitios_permitidos(user, p.empresa)
        permitidos = cache_permisos[p.empresa]
        if permitidos is None or p.sitio in permitidos:
            out.append(p)
    return out


@login_required
@require_GET
def api_habilitados(request):
    """Sitios en seguimiento que el usuario puede ver. Con ``?empresa=`` solo esa empresa."""
    denied = _gate_api(request.user, SECCION)
    if denied:
        return denied
    nombres = {e.nombre: e.nombre_display for e in company_loader.get_all()}
    proyectos = _proyectos_visibles(request.user, request.GET.get("empresa", ""))
    return JsonResponse({
        "habilitados": [p.sitio for p in proyectos],
        "proyectos": [{
            "empresa": p.empresa, "empresa_display": nombres.get(p.empresa, p.empresa),
            "sitio": p.sitio, "estado": p.estado, "estado_display": p.get_estado_display(),
        } for p in proyectos],
    })


@login_required
@require_POST
def api_proyecto_habilitar(request):
    """Check de «en seguimiento». Solo superusuario (como la sincronización de sitios)."""
    if not request.user.is_superuser:
        return _err("Solo el superusuario puede habilitar proyectos.", 403)
    d = _body(request)
    empresa, sitio = (d.get("empresa") or "").strip(), (d.get("sitio") or "").strip()
    if not empresa or not sitio:
        return _err("Faltan empresa/sitio.")
    proyecto = servicios.obtener_proyecto(empresa, sitio)
    proyecto.activo = bool(d.get("activo"))
    proyecto.actualizado_por = request.user
    proyecto.save()
    servicios.registrar(proyecto, "seguimiento",
                        "Sitio agregado a seguimiento" if proyecto.activo else "Sitio quitado de seguimiento",
                        request.user)
    return JsonResponse({"ok": True, "activo": proyecto.activo})


# ── Archivos del sitio en Nextcloud (lectura bajo demanda) ───────────────────
ORIGENES = ("contratista", "ito")
MAX_ARCHIVOS = 1500
VER_INLINE = ("application/pdf", "image/")


def _carpeta_sitio(root, sitio):
    """Nombre de la carpeta del sitio dentro de ``root``. Las raíces no nombran igual a un
    mismo sitio («CL-AN-1300 (ZA380) La Chimba» vs «CL-AN-1300 ZA380 LA CHIMBA»), así que
    si no hay coincidencia exacta se busca por el código «CL-XX-NNNN». Si no hay ninguna,
    devuelve ``sitio`` (el listado dirá que no existe)."""
    key = "proy:carpetas:" + hashlib.md5(root.encode("utf-8")).hexdigest()
    nombres = cache.get(key)
    if nombres is None:
        try:
            nombres = [i["nombre"] for i in nextcloud.list_folder(root) if i["es_dir"]]
            cache.set(key, nombres, 600)
        except Exception:
            return sitio
    if sitio in nombres:
        return sitio
    codigo = seguimiento._codigo_sitio(sitio).upper()
    if codigo:
        for n in nombres:
            if codigo in n.upper():
                return n
    return sitio


def _base_docs(empresa, sitio, origen):
    """Carpeta del sitio en Nextcloud: la del contratista (``/<raíz empresa>/<sitio>``) o
    la ITO (``/20-ITO INTERNO/<sitio>``). None si no se puede resolver."""
    if not sitio or "/" in sitio or ".." in sitio:
        return None
    if origen == "ito":
        root = ROOT_ITO_INTERNO
    else:
        emp = next((e for e in company_loader.get_all() if e.nombre == empresa), None)
        if not emp:
            return None
        root = emp.root_path()
    return f"{root}/{_carpeta_sitio(root, sitio)}"


def _acceso_docs(request, empresa, sitio, origen):
    """``(base, None)`` o ``(None, JsonResponse)`` tras validar sección, sitio y que el
    proyecto esté habilitado."""
    denied = _gate_api(request.user, SECCION)
    if denied:
        return None, denied
    denied = _denegar_sitio(request.user, empresa, sitio)
    if denied:
        return None, denied
    if not _proyecto_activo(empresa, sitio):
        return None, _err("El proyecto no está habilitado para seguimiento.", 404)
    base = _base_docs(empresa, sitio, origen) if origen in ORIGENES else None
    if not base:
        return None, _err("Origen o sitio inválido.")
    return base, None


def _datos_etapa(base, origen, etapa, refresh=False):
    """Árbol de la carpeta de la etapa dentro del sitio (cacheado 2 min). Devuelve
    ``(data, None)`` o ``(None, JsonResponse)`` si Nextcloud falla."""
    key = "proy:docs:" + hashlib.md5(f"{origen}|{base}|{etapa}".encode("utf-8")).hexdigest()
    data = None if refresh else cache.get(key)
    if data is None:
        try:
            raiz = nextcloud.list_folder(base)
            carpetas = servicios.carpetas_de_etapa(
                [i["nombre"] for i in raiz if i["es_dir"]], etapa)
            items = []
            for nombre in carpetas:
                sub = f"{base.rstrip('/')}/{nombre}"
                items.append({"path": sub, "nombre": nombre, "es_dir": True,
                              "mtime": None, "size": None})
                items.extend(nextcloud.tree(sub, max_depth=3))
            data = {"existe": True, "carpetas": carpetas, "items": items}
        except nextcloud.NextcloudNotConfigured:
            return None, _err("Nextcloud no está configurado.", 503)
        except Exception as ex:
            resp = getattr(ex, "response", None)
            if resp is not None and resp.status_code == 404:
                data = {"existe": False, "carpetas": [], "items": []}  # el sitio no tiene carpeta
            else:
                return None, _err("No se pudo leer Nextcloud.", 502)
        cache.set(key, data, 120)
    return data, None


@login_required
@require_GET
def api_archivos(request):
    """Archivos de la **carpeta de una etapa** dentro de la carpeta del sitio
    (``origen`` = contratista | ito; ``etapa`` = ING | CON | CIE). La carpeta de la
    etapa se detecta por su nombre (contiene INGENIERIA / CONSTRUCCION / CIERRE). Solo se
    consulta Nextcloud cuando el usuario despliega los documentos de la card."""
    empresa, sitio = request.GET.get("empresa", ""), request.GET.get("sitio", "")
    origen, etapa = request.GET.get("origen", ""), request.GET.get("etapa", "")
    if etapa not in servicios.PALABRAS_ETAPA:
        return _err("Etapa inválida.")
    base, denied = _acceso_docs(request, empresa, sitio, origen)
    if denied:
        return denied
    data, err = _datos_etapa(base, origen, etapa, request.GET.get("refresh") == "1")
    if err:
        return err
    prefijo = base.rstrip("/") + "/"
    out = [{
        "ruta": it["path"][len(prefijo):] if it["path"].startswith(prefijo) else it["nombre"],
        "nombre": it["nombre"], "es_dir": it["es_dir"],
        "size": it.get("size"), "mtime": it.get("mtime"),
    } for it in data["items"]]
    out.sort(key=lambda i: i["ruta"].lower())
    return JsonResponse({
        "existe": data["existe"], "carpetas": data["carpetas"], "base": base,
        "items": out[:MAX_ARCHIVOS], "truncado": len(out) > MAX_ARCHIVOS,
        "archivos": sum(1 for i in out if not i["es_dir"]),
    })


MAX_IMAGENES = 120


@login_required
@require_GET
def api_imagenes(request):
    """Imágenes de las carpetas de fotos (FOTOGRAFIAS, FOTOS, IMAGENES…) que hay dentro
    de la carpeta de la etapa, en ITO interno y en la carpeta del contratista. Se llama
    solo cuando el usuario lo pide."""
    empresa, sitio = request.GET.get("empresa", ""), request.GET.get("sitio", "")
    etapa = request.GET.get("etapa", "")
    if etapa not in servicios.PALABRAS_ETAPA:
        return _err("Etapa inválida.")
    refresh = request.GET.get("refresh") == "1"
    imagenes, errores = [], []
    for origen in ORIGENES:
        base, denied = _acceso_docs(request, empresa, sitio, origen)
        if denied:
            if denied.status_code in (403, 404):
                return denied
            continue
        data, err = _datos_etapa(base, origen, etapa, refresh)
        if err:
            errores.append(origen)
            continue
        prefijo = base.rstrip("/") + "/"
        for it in servicios.imagenes_de_carpetas_fotos(data["items"], base):
            imagenes.append({
                "origen": origen, "ruta": it["path"][len(prefijo):], "nombre": it["nombre"],
                "mtime": it.get("mtime"), "size": it.get("size"),
            })
    imagenes.sort(key=lambda i: (i["mtime"] or 0), reverse=True)
    return JsonResponse({"imagenes": imagenes[:MAX_IMAGENES],
                         "total": len(imagenes), "errores": errores})


def _ruta_valida(base, ruta):
    """Ruta absoluta de ``ruta`` bajo ``base`` o None si intenta salirse de la carpeta."""
    if not ruta or ".." in ruta.split("/") or ruta.startswith("/"):
        return None
    path = f"{base.rstrip('/')}/{ruta}"
    return path if os.path.normpath(path).startswith(base.rstrip("/") + "/") else None


@login_required
@require_GET
def miniatura(request):
    """Miniatura de una imagen del sitio (vista previa de Nextcloud; si no hay, el original)."""
    empresa, sitio = request.GET.get("empresa", ""), request.GET.get("sitio", "")
    base, denied = _acceso_docs(request, empresa, sitio, request.GET.get("origen", ""))
    if denied:
        return denied
    path = _ruta_valida(base, request.GET.get("ruta", ""))
    if not path or not servicios.es_imagen(path):
        return HttpResponse(status=404)
    key = "proy:mini:" + hashlib.md5(path.encode("utf-8")).hexdigest()
    hit = cache.get(key)
    if hit is None:
        try:
            hit = nextcloud.preview(path, 320)
            cache.set(key, hit, 3600)
        except Exception:
            try:  # sin vista previa (p. ej. HEIC): se sirve el original si es imagen web
                contenido, ctype = nextcloud.download(path)
            except Exception:
                return HttpResponse(status=404)
            if not ctype.startswith("image/") or "svg" in ctype:
                return HttpResponse(status=404)
            hit = (contenido, ctype)
    resp = HttpResponse(hit[0], content_type=hit[1])
    resp["Cache-Control"] = "private, max-age=3600"
    return resp


@login_required
@require_GET
def archivo_ver(request):
    """Descarga/visualiza un archivo del sitio. Solo rutas **dentro** de la carpeta del
    sitio (contratista o ITO); nada fuera de ella."""
    empresa, sitio = request.GET.get("empresa", ""), request.GET.get("sitio", "")
    base, denied = _acceso_docs(request, empresa, sitio, request.GET.get("origen", ""))
    if denied:
        return denied
    path = _ruta_valida(base, request.GET.get("ruta", ""))
    if not path:
        return HttpResponse(status=404)
    try:
        contenido, ctype = nextcloud.download(path)
    except Exception:
        return HttpResponse(status=404)
    nombre = path.rsplit("/", 1)[-1].replace('"', "")
    inline = ctype.startswith(VER_INLINE) and "svg" not in ctype
    resp = HttpResponse(contenido, content_type=ctype)
    resp["Content-Disposition"] = f'{"inline" if inline else "attachment"}; filename="{nombre}"'
    return resp


@login_required
@require_GET
def api_mapa(request):
    """Sitios ubicados en seguimiento (solo los que el usuario puede ver). Con
    ``?empresa=`` se limita a esa empresa; sin él, todas."""
    denied = _gate_api(request.user, SECCION)
    if denied:
        return denied
    proyectos = [p for p in _proyectos_visibles(request.user, request.GET.get("empresa", ""))
                 if p.lat is not None and p.lon is not None]
    return JsonResponse({"sitios": [{
        "empresa": p.empresa, "sitio": p.sitio, "lat": p.lat, "lon": p.lon,
        "estado": p.estado, "estado_display": p.get_estado_display(),
    } for p in proyectos]})


@login_required
@require_GET
def api_itos(request):
    """Candidatos ITO y cuáles están asignados al sitio (solo superusuario)."""
    if not request.user.is_superuser:
        return _err("Solo el superusuario asigna ITOs.", 403)
    empresa, sitio = request.GET.get("empresa", ""), request.GET.get("sitio", "")
    if not _proyecto_activo(empresa, sitio):
        return _err("El proyecto no está habilitado para seguimiento.", 404)
    asignados = {u.pk for u in servicios.itos_asignados(empresa, sitio)}
    return JsonResponse({"candidatos": [{
        "id": u.pk, "nombre": servicios.nombre_usuario(u), "email": u.email or u.username,
        "asignado": u.pk in asignados,
    } for u in servicios.candidatos_ito()]})


@login_required
@require_POST
def api_itos_guardar(request):
    """Fija los ITOs del sitio. Cada ITO solo verá los sitios que tenga asignados."""
    if not request.user.is_superuser:
        return _err("Solo el superusuario asigna ITOs.", 403)
    d = _body(request)
    empresa, sitio = d.get("empresa", ""), d.get("sitio", "")
    if not _proyecto_activo(empresa, sitio):
        return _err("El proyecto no está habilitado para seguimiento.", 404)
    try:
        ids = [int(i) for i in (d.get("ids") or [])]
    except (TypeError, ValueError):
        return _err("Identificadores inválidos.")
    servicios.asignar_itos(empresa, sitio, ids)
    itos = [{"id": u.pk, "nombre": servicios.nombre_usuario(u)}
            for u in servicios.itos_asignados(empresa, sitio)]
    servicios.registrar(_proyecto_activo(empresa, sitio), "itos",
                        "ITOs: " + (", ".join(i["nombre"] for i in itos) or "ninguno"), request.user)
    return JsonResponse({"ok": True, "itos": itos})


@login_required
@require_POST
def api_etapa_estado(request):
    d = _body(request)
    etapa, denied = _etapa_o_403(request, d.get("etapa_id"))
    if denied:
        return denied
    try:
        servicios.cambiar_estado_etapa(etapa, d.get("estado"), request.user)
    except servicios.ReglaEtapa as ex:
        return _err(str(ex))
    return JsonResponse({"ok": True})


@login_required
@require_POST
def api_pendiente_crear(request):
    d = _body(request)
    etapa, denied = _etapa_o_403(request, d.get("etapa_id"))
    if denied:
        return denied
    titulo = (d.get("titulo") or "").strip()[:200]
    if not titulo:
        return _err("El título es obligatorio.")
    fecha = _fecha(d.get("fecha"))
    r_user, r_txt = _responsable(d, etapa.proyecto)
    p = Pendiente.objects.create(
        etapa=etapa, titulo=titulo, fecha=fecha,
        hora=_hora(d.get("hora")) if fecha else None,
        responsable=r_txt, responsable_user=r_user, creado_por=request.user,
        prioridad="A" if d.get("prioridad") == "A" else "N")
    servicios.registrar(etapa.proyecto, "pend_crear", titulo, request.user, etapa)
    return JsonResponse({"ok": True, "calendario": _sync_calendario(p)})


def _responsable(d, proyecto):
    """``(usuario|None, texto)`` del responsable enviado: un usuario elegible del sitio
    (``responsable_id``) o un nombre escrito a mano (``responsable``)."""
    rid = d.get("responsable_id")
    if rid not in (None, "", 0) and str(rid).isdigit():
        u = servicios.responsables_posibles().filter(pk=int(rid)).first()
        if u:
            return u, servicios.nombre_usuario(u)[:100]
    return None, (d.get("responsable") or "").strip()[:100]


def _sync_calendario(p):
    """Refleja el pendiente en el calendario de Nextcloud. Un fallo de Nextcloud nunca
    impide guardar el pendiente: se informa al usuario con ``"error"``."""
    if not calendario.habilitado():
        return "desactivado"
    try:
        hay_evento = calendario.sincronizar(p)
    except Exception:
        return "error"
    if hay_evento != p.en_calendario:
        p.en_calendario = hay_evento
        p.save(update_fields=["en_calendario"])
    return "ok" if hay_evento else "sin_fecha"


def _pendiente_o_403(request, pk):
    p = (Pendiente.objects.filter(eliminado_en__isnull=True, pk=pk)
         .select_related("etapa__proyecto").first()) if str(pk).isdigit() else None
    if p is None:
        return None, _err("El pendiente no existe o ya fue eliminado.", 404)
    _, denied = _etapa_o_403(request, p.etapa_id)
    return (None, denied) if denied else (p, None)


@login_required
@require_POST
def api_pendiente_toggle(request):
    p, denied = _pendiente_o_403(request, _body(request).get("id"))
    if denied:
        return denied
    p.hecho = not p.hecho
    p.hecho_en = timezone.now() if p.hecho else None
    p.save(update_fields=["hecho", "hecho_en"])
    servicios.registrar(p.etapa.proyecto, "pend_hecho" if p.hecho else "pend_reabrir",
                        p.titulo, request.user, p.etapa)
    cal = _sync_calendario(p) if (p.fecha or p.en_calendario) else "sin_fecha"
    return JsonResponse({"ok": True, "hecho": p.hecho, "calendario": cal})


@login_required
@require_POST
def api_pendiente_editar(request):
    """Edita título, fecha, hora, responsable y prioridad; el evento del calendario se
    actualiza (o se crea/borra según haya fecha)."""
    d = _body(request)
    p, denied = _pendiente_o_403(request, d.get("id"))
    if denied:
        return denied
    titulo = (d.get("titulo") or "").strip()[:200]
    if not titulo:
        return _err("El título es obligatorio.")
    fecha = _fecha(d.get("fecha"))
    p.titulo = titulo
    p.fecha = fecha
    p.hora = _hora(d.get("hora")) if fecha else None
    p.responsable_user, p.responsable = _responsable(d, p.etapa.proyecto)
    p.prioridad = "A" if d.get("prioridad") == "A" else "N"
    p.save()
    servicios.registrar(p.etapa.proyecto, "pend_editar", titulo, request.user, p.etapa)
    return JsonResponse({"ok": True, "calendario": _sync_calendario(p)})


@login_required
@require_POST
def api_pendiente_eliminar(request):
    p, denied = _pendiente_o_403(request, _body(request).get("id"))
    if denied:
        return denied
    cal = "sin_fecha"
    if p.en_calendario and calendario.habilitado():
        try:
            calendario.borrar_evento(p)
            cal = "ok"
        except Exception:
            cal = "error"
    # Borrado lógico: se conserva el registro; el evento del calendario sí se quita.
    p.eliminado_en = timezone.now()
    p.eliminado_por = request.user
    p.en_calendario = False
    p.save(update_fields=["eliminado_en", "eliminado_por", "en_calendario"])
    servicios.registrar(p.etapa.proyecto, "pend_eliminar", p.titulo, request.user, p.etapa)
    return JsonResponse({"ok": True, "calendario": cal})


@login_required
@require_POST
def api_nota_crear(request):
    d = _body(request)
    etapa, denied = _etapa_o_403(request, d.get("etapa_id"))
    if denied:
        return denied
    texto = (d.get("texto") or "").strip()
    if not texto:
        return _err("La nota está vacía.")
    Nota.objects.create(etapa=etapa, texto=texto[:2000], usuario=request.user)
    servicios.registrar(etapa.proyecto, "nota_crear", texto[:120], request.user, etapa)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def api_nota_eliminar(request):
    pk = _body(request).get("id")
    n = Nota.objects.filter(eliminado_en__isnull=True, pk=pk).first() if str(pk).isdigit() else None
    if n is None:
        return _err("La nota no existe o ya fue eliminada.", 404)
    _, denied = _etapa_o_403(request, n.etapa_id)
    if denied:
        return denied
    if not _puede_borrar(request.user, n.usuario_id):
        return _err("Solo el autor o un coordinador pueden eliminarla.", 403)
    n.eliminado_en = timezone.now()   # borrado lógico
    n.eliminado_por = request.user
    n.save(update_fields=["eliminado_en", "eliminado_por"])
    servicios.registrar(n.etapa.proyecto, "nota_eliminar", n.texto[:120], request.user, n.etapa)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def api_imagen_subir(request):
    etapa, denied = _etapa_o_403(request, request.POST.get("etapa_id"))
    if denied:
        return denied
    archivos = request.FILES.getlist("archivos")
    if not archivos:
        return _err("No se envió ninguna imagen.")
    descripcion = (request.POST.get("descripcion") or "").strip()[:200]
    subidas, errores = 0, []
    for f in archivos:
        try:
            path = servicios.subir_imagen(etapa.proyecto, etapa, f.read(), f.name,
                                          f.content_type)
        except ValueError as ex:
            errores.append(f"{f.name}: {ex}")
            continue
        except Exception:
            errores.append(f"{f.name}: no se pudo subir a Nextcloud.")
            continue
        Imagen.objects.create(etapa=etapa, path=path, descripcion=descripcion,
                              subido_por=request.user)
        subidas += 1
    if subidas:
        servicios.registrar(etapa.proyecto, "img_subir", f"{subidas} imagen(es)", request.user, etapa)
    status = 200 if subidas else 400
    return JsonResponse({"ok": subidas > 0, "subidas": subidas, "errores": errores},
                        status=status)


@login_required
@require_POST
def api_imagen_eliminar(request):
    img = get_object_or_404(Imagen, pk=_body(request).get("id"))
    _, denied = _etapa_o_403(request, img.etapa_id)
    if denied:
        return denied
    if not _puede_borrar(request.user, img.subido_por_id):
        return _err("Solo el autor o un coordinador pueden eliminarla.", 403)
    try:
        nextcloud.delete(img.path)
    except Exception:
        return _err("No se pudo eliminar el archivo en Nextcloud.", 502)
    servicios.registrar(img.etapa.proyecto, "img_eliminar", img.descripcion or img.path.rsplit("/", 1)[-1],
                        request.user, img.etapa)
    img.delete()
    return JsonResponse({"ok": True})


@login_required
@require_GET
def imagen_ver(request, pk):
    """Proxy de la imagen en Nextcloud (exige sección + acceso al sitio)."""
    if _gate_api(request.user, SECCION):
        return HttpResponse(status=403)
    img = get_object_or_404(Imagen.objects.select_related("etapa__proyecto"), pk=pk)
    p = img.etapa.proyecto
    if not p.activo or _denegar_sitio(request.user, p.empresa, p.sitio):
        return HttpResponse(status=403)
    try:
        contenido, ctype = nextcloud.download(img.path)
    except Exception:
        raise Http404("No se pudo descargar la imagen.")
    if not ctype.startswith("image/"):
        ctype = "application/octet-stream"
    resp = HttpResponse(contenido, content_type=ctype)
    resp["Cache-Control"] = "private, max-age=3600"
    return resp


# ── Actividad, papelera y tablero ───────────────────────────────────────────
def _proyecto_o_err(request, empresa, sitio):
    """``(proyecto, None)`` o ``(None, JsonResponse)`` con sección, sitio y habilitado."""
    denied = _gate_api(request.user, SECCION)
    if denied:
        return None, denied
    denied = _denegar_sitio(request.user, empresa, sitio)
    if denied:
        return None, denied
    proyecto = _proyecto_activo(empresa, sitio)
    if not proyecto:
        return None, _err("El proyecto no está habilitado para seguimiento.", 404)
    return proyecto, None


@login_required
@require_GET
def api_actividad(request):
    """Últimos movimientos del proyecto (registro automático)."""
    if not request.user.is_superuser:
        return _err("Solo el superusuario puede ver el historial.", 403)
    proyecto, denied = _proyecto_o_err(request, request.GET.get("empresa", ""),
                                       request.GET.get("sitio", ""))
    if denied:
        return denied
    qs = proyecto.actividades.select_related("usuario", "etapa")[:80]
    return JsonResponse({"actividad": [{
        "tipo": a.tipo, "tipo_display": a.get_tipo_display(), "detalle": a.detalle,
        "usuario": servicios.nombre_usuario(a.usuario) if a.usuario else "",
        "etapa": a.etapa.get_etapa_display() if a.etapa else "",
        "fecha": a.creado.isoformat(),
    } for a in qs]})


@login_required
@require_GET
def api_papelera(request):
    """Pendientes y notas eliminados (borrado lógico) del proyecto."""
    if not request.user.is_superuser:
        return _err("Solo el superusuario puede ver el historial.", 403)
    proyecto, denied = _proyecto_o_err(request, request.GET.get("empresa", ""),
                                       request.GET.get("sitio", ""))
    if denied:
        return denied
    items = []
    for p in (Pendiente.objects.filter(etapa__proyecto=proyecto, eliminado_en__isnull=False)
              .select_related("etapa", "eliminado_por")):
        items.append({"tipo": "pendiente", "id": p.pk, "texto": p.titulo,
                      "etapa": p.etapa.get_etapa_display(), "fecha": p.eliminado_en.isoformat(),
                      "por": servicios.nombre_usuario(p.eliminado_por) if p.eliminado_por else "",
                      "puede_restaurar": _es_admin(request.user)})
    for n in (Nota.objects.filter(etapa__proyecto=proyecto, eliminado_en__isnull=False)
              .select_related("etapa", "eliminado_por")):
        items.append({"tipo": "nota", "id": n.pk, "texto": n.texto[:160],
                      "etapa": n.etapa.get_etapa_display(), "fecha": n.eliminado_en.isoformat(),
                      "por": servicios.nombre_usuario(n.eliminado_por) if n.eliminado_por else "",
                      "puede_restaurar": _puede_borrar(request.user, n.usuario_id)})
    items.sort(key=lambda i: i["fecha"], reverse=True)
    return JsonResponse({"papelera": items[:100]})


@login_required
@require_POST
def api_restaurar(request):
    """Restaura un pendiente o una nota eliminados."""
    d = _body(request)
    tipo, pk = d.get("tipo"), d.get("id")
    if tipo not in ("pendiente", "nota") or not str(pk).isdigit():
        return _err("Solicitud inválida.")
    modelo = Pendiente if tipo == "pendiente" else Nota
    obj = modelo.objects.filter(pk=pk, eliminado_en__isnull=False).select_related("etapa__proyecto").first()
    if obj is None:
        return _err("El elemento no está en la papelera.", 404)
    _, denied = _etapa_o_403(request, obj.etapa_id)
    if denied:
        return denied
    if tipo == "nota" and not _puede_borrar(request.user, obj.usuario_id):
        return _err("Solo el autor o un coordinador pueden restaurarla.", 403)
    obj.eliminado_en = None
    obj.eliminado_por = None
    obj.save(update_fields=["eliminado_en", "eliminado_por"])
    cal = "sin_fecha"
    if tipo == "pendiente":
        cal = _sync_calendario(obj)        # vuelve a su evento del calendario si tiene fecha
        texto = obj.titulo
    else:
        texto = obj.texto[:120]
    servicios.registrar(obj.etapa.proyecto, "pend_restaurar" if tipo == "pendiente" else "nota_restaurar",
                        texto, request.user, obj.etapa)
    return JsonResponse({"ok": True, "calendario": cal})


def _resumen_proyecto(p, hoy):
    """Datos del tablero de un proyecto: avance, vencidos, próximo pendiente, última nota."""
    pend = list(Pendiente.objects.filter(etapa__proyecto=p, eliminado_en__isnull=True))
    abiertos = [x for x in pend if not x.hecho]
    vencidos = [x for x in abiertos if x.fecha and x.fecha < hoy]
    con_fecha = sorted((x for x in abiertos if x.fecha),
                       key=lambda x: (x.fecha, x.hora or time(23, 59)))
    prox = con_fecha[0] if con_fecha else None
    nota = (Nota.objects.filter(etapa__proyecto=p, eliminado_en__isnull=True)
            .select_related("usuario").first())
    return {
        "empresa": p.empresa, "sitio": p.sitio, "estado": p.estado,
        "estado_display": p.get_estado_display(),
        "itos": [servicios.nombre_usuario(u) for u in servicios.itos_asignados(p.empresa, p.sitio)],
        "abiertos": len(abiertos), "hechos": len(pend) - len(abiertos), "total": len(pend),
        "vencidos": len(vencidos), "altas": sum(1 for x in abiertos if x.prioridad == "A"),
        "proximo": ({"titulo": prox.titulo, "fecha": prox.fecha.isoformat(),
                     "hora": prox.hora.strftime("%H:%M") if prox.hora else ""} if prox else None),
        "ultima_nota": ({"texto": nota.texto[:140], "fecha": nota.fecha.isoformat(),
                         "usuario": servicios.nombre_usuario(nota.usuario) if nota.usuario else ""}
                        if nota else None),
        "lat": p.lat, "lon": p.lon,
    }


@login_required
def tablero(request):
    """Panorama de todos los sitios en seguimiento que el usuario puede ver."""
    guard = _guard_seccion(request, SECCION)
    if guard:
        return guard
    return render(request, "proyectos/tablero.html", {
        "titulo_pagina": "Seguimiento · Tablero",
        "estados_proyecto": ESTADO_PROYECTO,
    })


@login_required
@require_GET
def api_tablero(request):
    denied = _gate_api(request.user, SECCION)
    if denied:
        return denied
    hoy = timezone.localdate()
    nombres = {e.nombre: e.nombre_display for e in company_loader.get_all()}
    filas = []
    for p in _proyectos_visibles(request.user):
        r = _resumen_proyecto(p, hoy)
        r["empresa_display"] = nombres.get(p.empresa, p.empresa)
        filas.append(r)
    # Lo más urgente primero: vencidos, luego próxima fecha.
    filas.sort(key=lambda r: (-r["vencidos"], r["proximo"]["fecha"] if r["proximo"] else "9999",
                              r["sitio"]))
    return JsonResponse({"sitios": filas, "hoy": hoy.isoformat()})
