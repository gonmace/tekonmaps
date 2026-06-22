import json
import os
from collections import Counter
from datetime import datetime
from urllib.parse import unquote
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from . import company_loader, nextcloud, seguimiento
from .models import (
    ACCIONES_REVISION, ArchivoOculto, AsignacionArchivo, ConfirmacionDocumento,
    DocumentoEsperado, DocumentoNoNecesario, EliminacionPendiente, EstructuraCache,
    ObservacionDocumento, ProyectoFinalCache, ROL_COLORES, SitioCache,
)


FINAL_ROOT_PATH = "/20-PTI SP"


def _parse_name(path_encoded):
    decoded = unquote(path_encoded).rstrip("/")
    return decoded.split("/")[-1]


def _parse_item_date(item):
    """Extrae timestamp de un item. El cliente WebDAV entrega lastModified como float."""
    if not item or not isinstance(item, dict):
        return None
    val = (
        item.get("lastModified")  # n8n Nextcloud node
        or item.get("mtime")
        or item.get("lastmodified")
        or item.get("getlastmodified")
    )
    if val is None and "propstat" in item:
        for ps in item.get("propstat", []) or []:
            props = ps.get("prop", {}) or {}
            val = props.get("getlastmodified")
            if val:
                break
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        s = val.replace("GMT", "").strip()
        fmts = [("%a, %d %b %Y %H:%M:%S", 25), ("%Y-%m-%dT%H:%M:%S", 19), ("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d", 10)]
        for fmt, maxlen in fmts:
            try:
                dt = datetime.strptime(s[:maxlen], fmt)
                return dt.timestamp()
            except (ValueError, TypeError):
                continue
    return None


def _get_folder_lastmod(path):
    """Obtiene la fecha de última modificación de una carpeta (max mtime de sus items)."""
    try:
        items = _fetch_items(path)
        timestamps = [_parse_item_date(i) for i in items if i]
        valid = [t for t in timestamps if t is not None]
        if not valid:
            return None
        return max(valid)
    except Exception:
        return None


_MESES_ES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def _format_lastmod(ts):
    """Formatea timestamp a string legible (ej: 25 feb 2025)."""
    if ts is None:
        return None
    try:
        dt = datetime.fromtimestamp(ts)
        return f"{dt.day:02d} {_MESES_ES[dt.month - 1]} {dt.year}"
    except (ValueError, TypeError, OSError, IndexError):
        return None


def _fetch_items(path):
    """Lista los items directos de una carpeta vía WebDAV, en el formato legacy
    {type, path, name, lastModified} que consumen el resto de helpers."""
    return [
        {
            "type": "folder" if it["es_dir"] else "file",
            "path": it["path"],
            "name": it["nombre"],
            "lastModified": it["mtime"],
        }
        for it in nextcloud.list_folder(path)
    ]


def _fetch_deep(root_folder_path):
    """Cuenta archivos por extensión en cada subcarpeta inmediata de root (recursivo).
    Devuelve {subcarpeta: {ext: count}}, el formato que consume _parse_subfolders.
    Reemplaza al antiguo endpoint deep de n8n."""
    subs = [i for i in _fetch_items(root_folder_path) if i.get("type") == "folder"]
    if not subs:
        return {}

    def one(item):
        nombre = _parse_name(item["path"])
        return nombre, _count_files_in_folder(f"{root_folder_path}/{nombre}")

    result = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for nombre, counts in ex.map(one, subs):
            result[nombre] = counts
    return result


def _parse_subfolders(deep):
    """Parsea la respuesta del endpoint deep a lista de {nombre, archivos}.
    Soporta formatos:
    - {"SubA": {"pdf": 2}, "SubB": {"dwg": 1}}  (dict plano)
    - {"subfolders": [{"nombre": "X", "archivos": {...}}]}
    - [{"nombre": "X", "archivos": {...}}]
    - ["SubA", "SubB"]  (lista de nombres)
    """
    if not deep:
        return []
    if isinstance(deep, list):
        result = []
        for item in deep:
            if isinstance(item, dict):
                result.append({
                    "nombre": str(item.get("nombre") or item.get("name") or ""),
                    "archivos": item.get("archivos") or item.get("files") or {},
                })
            elif isinstance(item, str):
                result.append({"nombre": item, "archivos": {}})
        return result
    if isinstance(deep, dict):
        if "subfolders" in deep:
            raw = deep["subfolders"]
            if isinstance(raw, list):
                return _parse_subfolders(raw)
        return [
            {"nombre": str(sub), "archivos": conteo if isinstance(conteo, dict) else {}}
            for sub, conteo in sorted(deep.items())
            if sub != "subfolders" and isinstance(conteo, dict)
        ]
    return []


def _build_tree(path, depth=0, max_depth=3, structure_only=False):
    """Árbol recursivo de carpetas. structure_only=True omite conteo de archivos."""
    if depth > max_depth:
        return []
    try:
        items = _fetch_items(path)
        subfolder_items = [i for i in items if i.get("type") == "folder"]
        if not subfolder_items:
            return []

        if not structure_only:
            try:
                deep = _fetch_deep(path)
                counts_map = {s["nombre"]: s["archivos"] for s in _parse_subfolders(deep)}
            except Exception:
                counts_map = {}
        else:
            counts_map = {}

        def process_folder(item):
            nombre = _parse_name(item["path"])
            child_path = f"{path}/{nombre}"
            if structure_only:
                archivos = {}
            else:
                archivos = counts_map.get(nombre) or _count_files_in_folder(child_path)
            children = _build_tree(child_path, depth + 1, max_depth, structure_only)
            return {"nombre": nombre, "archivos": archivos, "children": children}

        with ThreadPoolExecutor(max_workers=6) as ex:
            result = list(ex.map(process_folder, subfolder_items))
        return sorted(result, key=lambda c: c["nombre"])
    except Exception:
        return []


def _get_user_rol(user):
    """Rol único del usuario: 'visitante' o una función ITO ('rol_*')."""
    try:
        return user.profile.rol
    except Exception:
        return "visitante"


def _es_admin(user):
    """Puede subir archivos y confirmar (equipo ITO): cualquier rol que no sea visitante."""
    return user.is_superuser or _get_user_rol(user) != "visitante"


def _sitios_permitidos(user, empresa):
    """Sitios a los que el usuario puede acceder en una empresa.

    None = sin restricción (superusuario). set() = ninguno. Restrictivo:
    un usuario sin asignaciones no ve ningún sitio.
    """
    if user.is_superuser:
        return None
    from .models import AccesoSitio
    return set(AccesoSitio.objects.filter(user=user, empresa=empresa)
               .values_list("sitio", flat=True))


def _denegar_sitio(user, empresa, sitio):
    """403 si el usuario no tiene acceso al ``(empresa, sitio)``; ``None`` si puede.

    Reusa ``_sitios_permitidos`` (que devuelve ``None`` para el superusuario, por lo que
    nunca queda denegado). Pensado para las **escrituras**: la restricción por sitio ya se
    aplica en las lecturas y debe valer también al mutar (subir/confirmar/observar/eliminar…).
    """
    permitidos = _sitios_permitidos(user, empresa)
    if permitidos is not None and sitio not in permitidos:
        return JsonResponse({"error": "No tienes acceso a este sitio."}, status=403)
    return None


def _empresas_permitidas(user):
    """Empresas con al menos un sitio asignado. None = sin restricción (superusuario)."""
    if user.is_superuser:
        return None
    from .models import AccesoSitio
    return set(AccesoSitio.objects.filter(user=user)
               .values_list("empresa", flat=True))


def _es_coordinador(user):
    """Puede aceptar/rechazar borrados de archivos: Coordinador o superusuario."""
    return user.is_superuser or _get_user_rol(user) == "rol_coordinador"


def _es_tk_redline(user):
    """Puede dejar una observación general (rol TK Redline) en cualquier documento."""
    return user.is_superuser or _get_user_rol(user) == "rol_tk_redline"


def _puede_ver_seccion(user, campo):
    """Acceso a una sección del navbar (``acceso_contratista``/``acceso_finales``/
    ``acceso_seguimiento``). El superusuario ve todo. Sin perfil → sin acceso."""
    if user.is_superuser:
        return True
    try:
        return getattr(user.profile, campo)
    except Exception:
        return False


def _landing_url(user):
    """Primera sección del navbar a la que el usuario tiene acceso, o 'home' si ninguna."""
    if _puede_ver_seccion(user, "acceso_contratista"):
        return reverse("docs:index")
    if _puede_ver_seccion(user, "acceso_finales"):
        return reverse("docs:final")
    if _puede_ver_seccion(user, "acceso_seguimiento"):
        return reverse("docs:seguimiento")
    return reverse("home")


def _guard_seccion(request, campo):
    """Si el usuario no puede ver la sección, devuelve un redirect amable (a la primera
    sección permitida o a 'home') con un aviso; si puede, devuelve None."""
    if _puede_ver_seccion(request.user, campo):
        return None
    messages.warning(request, "No tienes acceso a esa sección.")
    return redirect(_landing_url(request.user))


def _gate_api(user, *campos):
    """JsonResponse 403 si el usuario no tiene NINGUNA de las secciones dadas; None si ok."""
    if any(_puede_ver_seccion(user, c) for c in campos):
        return None
    return JsonResponse({"error": "No tienes acceso a esta sección."}, status=403)


@login_required
def index(request):
    """Página Docs. Contratista. Las cards se cargan por AJAX."""
    guard = _guard_seccion(request, "acceso_contratista")
    if guard:
        return guard
    rol = _get_user_rol(request.user)
    empresas_list = company_loader.get_all()
    permitidas = _empresas_permitidas(request.user)
    if permitidas is not None:
        empresas_list = [e for e in empresas_list if e.nombre in permitidas]
    primera = empresas_list[0] if empresas_list else None
    empresa = request.GET.get("empresa", primera.nombre if primera else "")
    if not any(e.nombre == empresa for e in empresas_list):
        empresa = primera.nombre if primera else ""
    empresa_links = {e.nombre: e.link_para_rol(rol).rstrip("/") for e in empresas_list}
    return render(request, "docs/index.html", {
        "empresa": empresa,
        "empresas": empresas_list,
        "empresa_links": empresa_links,
        "titulo_pagina": "Docs. Contratista",
    })


@login_required
def final(request):
    """Página Docs. Finales — árbol de /20-PTI SP."""
    guard = _guard_seccion(request, "acceso_finales")
    if guard:
        return guard
    from django.conf import settings
    from .models import SiteConfig
    rol = _get_user_rol(request.user)
    try:
        config = SiteConfig.objects.get(clave="NEXTCLOUD_FINAL_BASE")
        nextcloud_base = config.link_para_rol(rol)
    except SiteConfig.DoesNotExist:
        nextcloud_base = getattr(settings, "NEXTCLOUD_FINAL_BASE", "")
    return render(request, "docs/final.html", {
        "titulo_pagina": "Docs. Finales",
        "nextcloud_base": nextcloud_base,
    })


@login_required
def seguimiento_view(request):
    """Tablero de seguimiento de completitud de documentos del ITO."""
    guard = _guard_seccion(request, "acceso_seguimiento")
    if guard:
        return guard
    empresas = company_loader.get_all()
    permitidas = _empresas_permitidas(request.user)
    if permitidas is not None:
        empresas = [e for e in empresas if e.nombre in permitidas]
    return render(request, "docs/seguimiento.html", {
        "titulo_pagina": "Seguimiento",
        "empresas": empresas,
        "es_admin": _es_admin(request.user),
        "es_coordinador": _es_coordinador(request.user),
        "es_tk_redline": _es_tk_redline(request.user),
        "es_superuser": request.user.is_superuser,
        "roles_leyenda": [(sigla, lbl, ROL_COLORES.get(sigla, "#6b7280"))
                          for _, lbl, sigla in DocumentoEsperado.ROLES],
    })


@login_required
def api_seguimiento(request):
    """GET: estado de completitud de documentos del ITO para (empresa, sitio)."""
    denied = _gate_api(request.user, "acceso_seguimiento")
    if denied:
        return denied
    empresa = request.GET.get("empresa", "").strip()
    sitio = request.GET.get("sitio", "").strip()
    if not empresa or not sitio:
        return JsonResponse({"error": "Faltan 'empresa' y/o 'sitio'.", "documentos": []}, status=400)
    permitidos = _sitios_permitidos(request.user, empresa)
    if permitidos is not None and sitio not in permitidos:
        return JsonResponse({"error": "No tienes acceso a este sitio.", "documentos": []}, status=403)
    forzar = request.GET.get("refresh") in ("1", "true")
    try:
        return JsonResponse(seguimiento.estado_sitio(empresa, sitio, forzar=forzar))
    except Exception as e:
        return JsonResponse({"error": str(e), "documentos": []}, status=500)


@login_required
def api_carpetas20(request):
    """GET (superuser): carpetas raíz /20* (constructora) para el selector de refresh."""
    if not request.user.is_superuser:
        return JsonResponse({"carpetas": []})
    try:
        return JsonResponse({"carpetas": seguimiento.roots_constructora(forzar=True)})
    except Exception:
        return JsonResponse({"carpetas": []})


@login_required
def refrescar_carpeta(request):
    """POST (superuser): re-escanea SOLO la carpeta /20* indicada para el sitio actual
    (las demás carpetas salen de la caché por carpeta). Devuelve el estado actualizado."""
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido."}, status=405)
    if not request.user.is_superuser:
        return JsonResponse({"error": "No autorizado."}, status=403)
    empresa = request.POST.get("empresa", "").strip()
    sitio = request.POST.get("sitio", "").strip()
    carpeta = request.POST.get("carpeta", "").strip()
    if not (empresa and sitio and carpeta):
        return JsonResponse({"error": "Faltan datos."}, status=400)
    try:
        return JsonResponse(seguimiento.estado_sitio(empresa, sitio, forzar_root=carpeta))
    except Exception as e:
        return JsonResponse({"error": str(e), "documentos": []}, status=500)


@login_required
def actualizar_estructura(request):
    """POST (superuser): guarda la estructura mostrada en la plantilla asignada (en su lugar,
    compartida; sin re-escanear carpetas ni crear copias por sitio) y devuelve el estado del
    sitio recalculado + un resumen."""
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido."}, status=405)
    if not request.user.is_superuser:
        return JsonResponse({"error": "No autorizado."}, status=403)
    empresa = request.POST.get("empresa", "").strip()
    sitio = request.POST.get("sitio", "").strip()
    if not (empresa and sitio):
        return JsonResponse({"error": "Faltan 'empresa' y/o 'sitio'."}, status=400)
    try:
        resumen = seguimiento.guardar_estructura(empresa, sitio)
        estado = seguimiento.estado_sitio(empresa, sitio, forzar=True)
        return JsonResponse({"resumen": resumen, **estado})
    except Exception as e:
        return JsonResponse({"error": str(e), "documentos": []}, status=500)


# Límites de subida. El ``content_type`` del cliente no es de fiar, así que validamos
# por extensión (whitelist) + tamaño antes de enviar nada a Nextcloud.
MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB por archivo
EXT_DOCUMENTO = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff",
    ".dwg", ".dxf", ".zip", ".rar", ".7z", ".kmz", ".kml",
}
EXT_IMAGEN = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".bmp", ".tif", ".tiff"}
EXT_VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".mpg", ".mpeg"}


def _validar_subida(archivo, extensiones, etiqueta):
    """Valida tamaño y extensión de un ``UploadedFile``. Devuelve un mensaje de error
    (str) o ``None`` si es válido."""
    if archivo.size and archivo.size > MAX_UPLOAD_BYTES:
        tope = MAX_UPLOAD_BYTES // (1024 * 1024)
        return f"El archivo «{archivo.name}» supera el límite de {tope} MB."
    ext = os.path.splitext(archivo.name or "")[1].lower()
    if ext not in extensiones:
        return f"Tipo de archivo no permitido para {etiqueta}: «{ext or archivo.name}»."
    return None


@login_required
def subir_archivo(request):
    """POST multipart (solo administrador): sube un archivo para un documento al área ITO.
    Campos: empresa, sitio, doc_id, file."""
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido."}, status=405)
    if not _es_admin(request.user):
        return JsonResponse({"error": "No autorizado."}, status=403)
    empresa = request.POST.get("empresa", "").strip()
    sitio = request.POST.get("sitio", "").strip()
    doc_id = request.POST.get("doc_id", "").strip()
    archivos = request.FILES.getlist("file")
    if not (empresa and sitio and doc_id and archivos):
        return JsonResponse({"error": "Faltan datos o archivo."}, status=400)
    if (denegado := _denegar_sitio(request.user, empresa, sitio)):
        return denegado
    for archivo in archivos:
        if (err := _validar_subida(archivo, EXT_DOCUMENTO, "documentos")):
            return JsonResponse({"error": err}, status=400)
    doc = get_object_or_404(DocumentoEsperado, pk=doc_id)
    nombres = request.POST.getlist("nombre")  # nombre final por archivo (front)
    subidos = []
    try:
        for i, archivo in enumerate(archivos):
            nombre = nombres[i] if i < len(nombres) and nombres[i].strip() else archivo.name
            destino = seguimiento.subir_documento(
                empresa, sitio, doc, archivo.read(), nombre,
                getattr(archivo, "content_type", None), usuario=request.user)
            subidos.append({"path": destino, "nombre": destino.rsplit("/", 1)[-1]})
    except Exception as e:
        return JsonResponse({"error": f"No se pudo cargar: {e}"}, status=500)
    return JsonResponse({"ok": True, "subidos": len(subidos), "archivos": subidos,
                         "roles": seguimiento.roles_estado(empresa, sitio, doc)})


@login_required
def subir_multimedia(request):
    """POST multipart (admin): sube imágenes/videos a la carpeta del sitio en el área ITO.
    Campos: empresa, sitio, tipo ('imagenes'|'videos'), file (1+). Devuelve el estado."""
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido."}, status=405)
    if not _es_admin(request.user):
        return JsonResponse({"error": "No autorizado."}, status=403)
    empresa = request.POST.get("empresa", "").strip()
    sitio = request.POST.get("sitio", "").strip()
    tipo = request.POST.get("tipo", "").strip()
    archivos = request.FILES.getlist("file")
    if not (empresa and sitio and tipo in ("imagenes", "videos") and archivos):
        return JsonResponse({"error": "Faltan datos o archivo."}, status=400)
    if (denegado := _denegar_sitio(request.user, empresa, sitio)):
        return denegado
    permitidas = EXT_IMAGEN if tipo == "imagenes" else EXT_VIDEO
    for archivo in archivos:
        if (err := _validar_subida(archivo, permitidas, "multimedia")):
            return JsonResponse({"error": err}, status=400)
    try:
        for archivo in archivos:
            seguimiento.subir_multimedia(sitio, tipo, archivo.read(), archivo.name,
                                         getattr(archivo, "content_type", None))
    except Exception as e:
        return JsonResponse({"error": f"No se pudo cargar: {e}"}, status=500)
    seguimiento.invalidar_cache(empresa, sitio)
    return JsonResponse(seguimiento.estado_sitio(empresa, sitio))


@login_required
def confirmar(request):
    """POST JSON (solo administrador): alterna la confirmación de un rol para un documento.
    Body: {empresa, sitio, doc_id, rol}."""
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido."}, status=405)
    if not _es_admin(request.user):
        return JsonResponse({"error": "No autorizado."}, status=403)
    try:
        data = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"error": "JSON inválido."}, status=400)
    empresa = (data.get("empresa") or "").strip()
    sitio = (data.get("sitio") or "").strip()
    doc_id = data.get("doc_id")
    rol = (data.get("rol") or "").strip()
    roles_validos = {c for c, _, _ in DocumentoEsperado.ROLES}
    if not (empresa and sitio and doc_id and rol in roles_validos):
        return JsonResponse({"error": "Datos inválidos."}, status=400)
    if (denegado := _denegar_sitio(request.user, empresa, sitio)):
        return denegado
    doc = get_object_or_404(DocumentoEsperado, pk=doc_id)
    # Solo las acciones de revisión se confirman a mano; el resto va por subida.
    if getattr(doc, rol, "") not in ACCIONES_REVISION:
        return JsonResponse({"error": "Ese rol se confirma al cargar el archivo, no manualmente."}, status=400)
    existente = ConfirmacionDocumento.objects.filter(
        empresa=empresa, sitio=sitio, documento=doc, rol=rol).first()
    if existente:
        existente.delete()
        seguimiento.invalidar_datos(empresa, sitio)
        return JsonResponse({"confirmado": False})
    c = ConfirmacionDocumento.objects.create(
        empresa=empresa, sitio=sitio, documento=doc, rol=rol, usuario=request.user)
    # Conforme y observación son excluyentes: confirmar limpia la observación de ese rol.
    ObservacionDocumento.objects.filter(
        empresa=empresa, sitio=sitio, documento=doc, rol=rol).delete()
    seguimiento.invalidar_datos(empresa, sitio)
    return JsonResponse({"confirmado": True,
                         "usuario": request.user.get_username(),
                         "fecha": seguimiento._format_fecha(c.fecha)})


@login_required
def observar(request):
    """POST JSON (administrador/revisor): marca un documento como **no conforme** con una
    nota; queda ⚠ hasta que se corrija. Body: {empresa, sitio, doc_id, rol, texto}."""
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido."}, status=405)
    if not _es_admin(request.user):
        return JsonResponse({"error": "No autorizado."}, status=403)
    try:
        data = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"error": "JSON inválido."}, status=400)
    empresa = (data.get("empresa") or "").strip()
    sitio = (data.get("sitio") or "").strip()
    doc_id = data.get("doc_id")
    rol = (data.get("rol") or "").strip()
    texto = (data.get("texto") or "").strip()
    roles_validos = {c for c, _, _ in DocumentoEsperado.ROLES}
    if not (empresa and sitio and doc_id and rol in roles_validos and texto):
        return JsonResponse({"error": "Datos inválidos (falta la nota)."}, status=400)
    if (denegado := _denegar_sitio(request.user, empresa, sitio)):
        return denegado
    doc = get_object_or_404(DocumentoEsperado, pk=doc_id)
    existente = ObservacionDocumento.objects.filter(
        empresa=empresa, sitio=sitio, documento=doc, rol=rol).first()
    # El autor siempre puede editar su propia observación. Si no, TK Redline (o superuser)
    # puede observar cualquier documento; el resto, solo donde su rol revisa.
    es_autor = bool(existente and existente.usuario_id == request.user.id)
    es_obs_general = rol == "rol_tk_redline" and _es_tk_redline(request.user)
    if not es_autor and not es_obs_general and getattr(doc, rol, "") not in ACCIONES_REVISION:
        return JsonResponse({"error": "Solo los roles de revisión pueden observar."}, status=400)
    o = ObservacionDocumento.objects.update_or_create(
        empresa=empresa, sitio=sitio, documento=doc, rol=rol,
        defaults={"usuario": request.user, "texto": texto})[0]
    # No conforme y conforme son excluyentes: observar quita la confirmación de ese rol.
    ConfirmacionDocumento.objects.filter(
        empresa=empresa, sitio=sitio, documento=doc, rol=rol).delete()
    seguimiento.invalidar_datos(empresa, sitio)
    return JsonResponse({"ok": True, "usuario": request.user.get_username(),
                         "fecha": seguimiento._format_fecha(o.fecha)})


@login_required
def quitar_observacion(request):
    """POST JSON (**solo superusuario**): borra definitivamente la observación de un rol.
    Body: {empresa, sitio, doc_id, rol}."""
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido."}, status=405)
    if not request.user.is_superuser:
        return JsonResponse({"error": "Solo un superusuario puede borrar observaciones."}, status=403)
    try:
        data = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"error": "JSON inválido."}, status=400)
    empresa = (data.get("empresa") or "").strip()
    sitio = (data.get("sitio") or "").strip()
    doc_id = data.get("doc_id")
    rol = (data.get("rol") or "").strip()
    if not (empresa and sitio and doc_id and rol):
        return JsonResponse({"error": "Datos inválidos."}, status=400)
    ObservacionDocumento.objects.filter(
        empresa=empresa, sitio=sitio, documento_id=doc_id, rol=rol).delete()
    seguimiento.invalidar_datos(empresa, sitio)
    return JsonResponse({"ok": True})


@login_required
def enmendar_observacion(request):
    """POST JSON: **solo el autor** de la observación la marca como enmendada (✓ verde) o
    lo deshace. Body: {empresa, sitio, doc_id, rol, enmendada}."""
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido."}, status=405)
    try:
        data = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"error": "JSON inválido."}, status=400)
    empresa = (data.get("empresa") or "").strip()
    sitio = (data.get("sitio") or "").strip()
    doc_id = data.get("doc_id")
    rol = (data.get("rol") or "").strip()
    if not (empresa and sitio and doc_id and rol):
        return JsonResponse({"error": "Datos inválidos."}, status=400)
    if (denegado := _denegar_sitio(request.user, empresa, sitio)):
        return denegado
    o = ObservacionDocumento.objects.filter(
        empresa=empresa, sitio=sitio, documento_id=doc_id, rol=rol).first()
    if not o:
        return JsonResponse({"error": "No existe la observación."}, status=404)
    if o.usuario_id != request.user.id:
        return JsonResponse({"error": "Solo quien dejó la observación puede marcarla como enmendada."}, status=403)
    enmendada = bool(data.get("enmendada", True))
    # .update() evita que ``auto_now`` mueva la fecha original de la observación.
    ObservacionDocumento.objects.filter(pk=o.pk).update(enmendada=enmendada)
    seguimiento.invalidar_datos(empresa, sitio)
    return JsonResponse({"ok": True, "enmendada": enmendada})


@login_required
def marcar_necesario(request):
    """POST JSON (solo superuser): marca un documento como necesario/no-necesario para
    el sitio. Body: {empresa, sitio, doc_id, necesario}."""
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido."}, status=405)
    if not request.user.is_superuser:
        return JsonResponse({"error": "No autorizado."}, status=403)
    try:
        data = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"error": "JSON inválido."}, status=400)
    empresa = (data.get("empresa") or "").strip()
    sitio = (data.get("sitio") or "").strip()
    doc_id = data.get("doc_id")
    necesario = bool(data.get("necesario"))
    if not (empresa and sitio and doc_id):
        return JsonResponse({"error": "Datos inválidos."}, status=400)
    doc = get_object_or_404(DocumentoEsperado, pk=doc_id)
    if necesario:
        DocumentoNoNecesario.objects.filter(empresa=empresa, sitio=sitio, documento=doc).delete()
    else:
        DocumentoNoNecesario.objects.get_or_create(empresa=empresa, sitio=sitio, documento=doc)
    seguimiento.invalidar_datos(empresa, sitio)
    return JsonResponse({"ok": True, "necesario": necesario})


@login_required
def asignar_archivo(request):
    """POST JSON (solo administrador): asigna manualmente un archivo a un documento.
    Body: {empresa, sitio, path, doc_id}."""
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido."}, status=405)
    if not _es_admin(request.user):
        return JsonResponse({"error": "No autorizado."}, status=403)
    try:
        data = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"error": "JSON inválido."}, status=400)
    empresa = (data.get("empresa") or "").strip()
    sitio = (data.get("sitio") or "").strip()
    path = data.get("path") or ""
    doc_id = data.get("doc_id")
    if not (empresa and sitio and doc_id and path.startswith("/20")):
        return JsonResponse({"error": "Datos inválidos."}, status=400)
    if (denegado := _denegar_sitio(request.user, empresa, sitio)):
        return denegado
    doc = get_object_or_404(DocumentoEsperado, pk=doc_id)
    AsignacionArchivo.objects.update_or_create(
        empresa=empresa, sitio=sitio, path=path,
        defaults={"documento": doc, "usuario": request.user})
    seguimiento.invalidar_datos(empresa, sitio)
    return JsonResponse({"ok": True, "doc_id": doc.id})


def _parse_eliminacion(request):
    """Valida el body común de las vistas de eliminación. Devuelve (empresa, sitio, path) o
    una ``JsonResponse`` de error."""
    try:
        data = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"error": "JSON inválido."}, status=400)
    empresa = (data.get("empresa") or "").strip()
    sitio = (data.get("sitio") or "").strip()
    path = data.get("path") or ""
    if not path.startswith("/20") or not (empresa and sitio):
        return JsonResponse({"error": "Datos inválidos."}, status=400)
    if (denegado := _denegar_sitio(request.user, empresa, sitio)):
        return denegado
    return empresa, sitio, path


@login_required
def eliminar_archivo(request):
    """POST JSON (administrador): NO borra; **marca** el archivo como pendiente de borrado
    (X). El borrado real lo acepta un Coordinador/superusuario. Body: {empresa, sitio, path}."""
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido."}, status=405)
    if not _es_admin(request.user):
        return JsonResponse({"error": "No autorizado."}, status=403)
    parsed = _parse_eliminacion(request)
    if isinstance(parsed, JsonResponse):
        return parsed
    empresa, sitio, path = parsed
    EliminacionPendiente.objects.update_or_create(
        empresa=empresa, sitio=sitio, path=path, defaults={"usuario": request.user})
    seguimiento.invalidar_datos(empresa, sitio)
    return JsonResponse({"ok": True, "pendiente": True})


@login_required
def aceptar_eliminacion(request):
    """POST JSON (Coordinador/superusuario): acepta la marca y **borra** el archivo de
    Nextcloud. Body: {empresa, sitio, path}."""
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido."}, status=405)
    if not _es_coordinador(request.user):
        return JsonResponse({"error": "Solo el Coordinador o un superusuario puede aceptar borrados."}, status=403)
    parsed = _parse_eliminacion(request)
    if isinstance(parsed, JsonResponse):
        return parsed
    empresa, sitio, path = parsed
    try:
        nextcloud.delete(path)
    except Exception as e:
        return JsonResponse({"error": f"No se pudo eliminar: {e}"}, status=500)
    EliminacionPendiente.objects.filter(empresa=empresa, sitio=sitio, path=path).delete()
    seguimiento.limpiar_autoconfirmaciones(empresa, sitio, path)
    seguimiento.invalidar_cache(empresa, sitio)
    return JsonResponse({"ok": True, "eliminado": True})


@login_required
def rechazar_eliminacion(request):
    """POST JSON (Coordinador/superusuario): quita la marca de borrado (el archivo se queda).
    Body: {empresa, sitio, path}."""
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido."}, status=405)
    if not _es_coordinador(request.user):
        return JsonResponse({"error": "No autorizado."}, status=403)
    parsed = _parse_eliminacion(request)
    if isinstance(parsed, JsonResponse):
        return parsed
    empresa, sitio, path = parsed
    EliminacionPendiente.objects.filter(empresa=empresa, sitio=sitio, path=path).delete()
    seguimiento.invalidar_datos(empresa, sitio)
    return JsonResponse({"ok": True, "pendiente": False})


@login_required
def ocultar_archivo(request):
    """POST JSON (administrador): **oculta** (soft-delete reversible) una o varias imágenes de
    una galería. NO borra de Nextcloud; solo deja de mostrarlas. Un admin las restaura con
    ``restaurar_archivo``. Body: {empresa, sitio, paths: [...]} (acepta también ``path`` único)."""
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido."}, status=405)
    if not _es_admin(request.user):
        return JsonResponse({"error": "No autorizado."}, status=403)
    try:
        data = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"error": "JSON inválido."}, status=400)
    empresa = (data.get("empresa") or "").strip()
    sitio = (data.get("sitio") or "").strip()
    paths = data.get("paths") or ([data["path"]] if data.get("path") else [])
    paths = [p for p in paths if isinstance(p, str) and p.startswith("/20")]
    if not (empresa and sitio and paths):
        return JsonResponse({"error": "Datos inválidos."}, status=400)
    if (denegado := _denegar_sitio(request.user, empresa, sitio)):
        return denegado
    for p in paths:
        ArchivoOculto.objects.update_or_create(
            empresa=empresa, sitio=sitio, path=p, defaults={"usuario": request.user})
    seguimiento.invalidar_datos(empresa, sitio)
    return JsonResponse({"ok": True, "ocultos": len(paths)})


@login_required
def restaurar_archivo(request):
    """POST JSON (administrador): restaura una imagen oculta (quita el soft-delete).
    Body: {empresa, sitio, path}."""
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido."}, status=405)
    if not _es_admin(request.user):
        return JsonResponse({"error": "No autorizado."}, status=403)
    parsed = _parse_eliminacion(request)
    if isinstance(parsed, JsonResponse):
        return parsed
    empresa, sitio, path = parsed
    ArchivoOculto.objects.filter(empresa=empresa, sitio=sitio, path=path).delete()
    seguimiento.invalidar_datos(empresa, sitio)
    return JsonResponse({"ok": True, "oculto": False})


@login_required
def descargar_archivo(request):
    """GET ?path= : proxy de descarga de un archivo de Nextcloud (para ver/abrir).
    Solo se permiten rutas bajo el área ITO o bajo carpetas de empresa (que empiecen con '/20').
    Exige acceso a alguna sección de documentos (Contratista/Seguimiento); un visitante sin
    secciones no descarga. El control fino por sitio se aplica en las vistas que listan/asignan."""
    denied = _gate_api(request.user, "acceso_contratista", "acceso_seguimiento")
    if denied:
        return denied
    path = request.GET.get("path", "")
    # Rechaza traversal: la ruta normalizada debe seguir bajo '/20*'.
    if ".." in path or not os.path.normpath(path).startswith("/20"):
        raise Http404("Ruta no permitida.")
    try:
        contenido, ctype = nextcloud.download(path)
    except Exception:
        raise Http404("No se pudo descargar el archivo.")
    nombre = path.rsplit("/", 1)[-1]
    resp = HttpResponse(contenido, content_type=ctype)
    resp["Content-Disposition"] = f'inline; filename="{nombre}"'
    return resp


def _buscar_template(codigo, archivos):
    """Elige, entre ``[(nombre, mtime)]``, el archivo de template que mejor calza
    con ``codigo``. Prioriza: stem exacto > nombre empieza con código > código
    empieza con stem. Devuelve el nombre o None."""
    code = codigo.strip().lower()
    exacto = empieza = contiene = None
    for nombre, _ in archivos:
        nl = nombre.lower()
        stem = nl.rsplit(".", 1)[0]
        if stem == code or nl == code:
            return nombre
        if empieza is None and nl.startswith(code):
            empieza = nombre
        if contiene is None and code.startswith(stem):
            contiene = nombre
    return exacto or empieza or contiene


@login_required
def descargar_template(request, pk):
    """Descarga el template de un documento esperado, **únicamente** desde la carpeta
    de plantillas en /20-ITO_SEGUIMIENTO/00-PLANTILLAS (búsqueda recursiva por código)."""
    denied = _gate_api(request.user, "acceso_contratista", "acceso_seguimiento")
    if denied:
        return denied
    doc = get_object_or_404(DocumentoEsperado, pk=pk)
    if not doc.codigo:
        raise Http404("El documento no tiene template asociado.")
    try:
        items = [it for it in nextcloud.tree(seguimiento.TEMPLATES_PATH, max_depth=4)
                 if not it["es_dir"]]
    except Exception:
        raise Http404("No se pudo acceder a la carpeta de plantillas.")
    nombre = _buscar_template(doc.codigo, [(it["nombre"], 0) for it in items])
    if not nombre:
        raise Http404("No se encontró el template del documento.")
    match = next(it for it in items if it["nombre"] == nombre)
    contenido, ctype = nextcloud.download(match["path"])
    resp = HttpResponse(contenido, content_type=ctype)
    resp["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return resp


@login_required
def api_sitios(request):
    """GET: retorna lista de sitios (carpetas) para la empresa indicada.
    Con ``?generados=1`` solo devuelve los sitios ya generados por la app (con carpeta
    en el área ITO); lo usa la asignación de Accesos del Panel."""
    # Compartido por Docs. Contratista y Seguimiento (y el Panel como superuser).
    denied = _gate_api(request.user, "acceso_contratista", "acceso_seguimiento")
    if denied:
        return denied
    empresa = request.GET.get("empresa", "")
    emp = company_loader.get_by_nombre(empresa)
    if not emp:
        return JsonResponse({"sitios": []})
    root_path = emp.root_path()
    permitidos = _sitios_permitidos(request.user, empresa)
    solo_generados = request.GET.get("generados") in ("1", "true")
    try:
        raiz_items = [i for i in _fetch_items(root_path) if i.get("type") == "folder"]
        sitios = sorted(_parse_name(item["path"]) for item in raiz_items)
        if permitidos is not None:
            sitios = [s for s in sitios if s in permitidos]
        if solo_generados:
            generados = seguimiento.sitios_generados()
            sitios = [s for s in sitios if s in generados]
        return JsonResponse({"sitios": sitios})
    except Exception:
        return JsonResponse({"sitios": []})


def _fetch_carpetas(empresa_codigo, structure_only=False):
    """Obtiene carpetas para una empresa desde el webhook.
    structure_only=True solo trae nombres de subcarpetas."""
    emp = company_loader.get_by_nombre(empresa_codigo)
    if not emp:
        return [], "Empresa no configurada."
    root_path = emp.root_path()
    carpetas = []
    error = None
    try:
        raiz_items = [i for i in _fetch_items(root_path) if i.get("type") == "folder"]
        items_config = [
            {"path": item["path"], "nombre_carpeta": _parse_name(item["path"])}
            for item in raiz_items
        ]

        def get_carpeta(item):
            nombre_carpeta = item["nombre_carpeta"]
            root_folder_path = f"{root_path}/{nombre_carpeta}"
            subfolders = []
            if structure_only:
                try:
                    items = _fetch_items(root_folder_path)
                    subfolders = [
                        {"nombre": _parse_name(i["path"]), "archivos": {}}
                        for i in items
                        if i.get("type") == "folder"
                    ]
                    subfolders.sort(key=lambda s: s["nombre"])
                except Exception:
                    pass
            else:
                try:
                    deep = _fetch_deep(root_folder_path)
                    subfolders = _parse_subfolders(deep)
                except Exception:
                    pass
                if not subfolders:
                    try:
                        items = _fetch_items(root_folder_path)
                        subfolders = [
                            {"nombre": _parse_name(i["path"]), "archivos": {}}
                            for i in items
                            if i.get("type") == "folder"
                        ]
                        subfolders.sort(key=lambda s: s["nombre"])
                    except Exception:
                        pass
            return {"nombre": nombre_carpeta, "subfolders": subfolders}

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(get_carpeta, item) for item in items_config]
            carpetas = [f.result() for f in as_completed(futures)]
        carpetas.sort(key=lambda c: c["nombre"])
    except requests.exceptions.ConnectionError:
        error = "No se pudo conectar al servidor."
    except requests.exceptions.Timeout:
        error = "La solicitud tardó demasiado. Intenta de nuevo."
    except requests.exceptions.HTTPError as e:
        error = f"Error del servidor: {e}"
    except Exception as e:
        error = str(e) or "Error inesperado."
    return carpetas, error


@login_required
def api_carpetas(request):
    """GET: retorna carpetas. structure_only=1 solo trae estructura (sin archivos)."""
    denied = _gate_api(request.user, "acceso_contratista")
    if denied:
        return denied
    primera = company_loader.get_first()
    empresa = request.GET.get("empresa", primera.nombre if primera else "")
    structure_only = request.GET.get("structure_only") in ("1", "true", "yes")

    # Caché de estructura: comparar timestamp del root de la empresa
    if structure_only:
        emp = company_loader.get_by_nombre(empresa)
        ts = _get_folder_lastmod(emp.root_path()) if emp else None
        try:
            entry = EstructuraCache.objects.get(empresa=empresa)
            if ts is not None and entry.ultima_actualizacion_ts == ts:
                return JsonResponse({"carpetas": entry.datos})
        except EstructuraCache.DoesNotExist:
            pass

        carpetas, error = _fetch_carpetas(empresa, structure_only=True)
        if error:
            return JsonResponse({"error": error, "carpetas": []}, status=500)
        if carpetas:
            EstructuraCache.objects.update_or_create(
                empresa=empresa,
                defaults={"ultima_actualizacion_ts": ts, "datos": carpetas},
            )
        return JsonResponse({"carpetas": carpetas})

    carpetas, error = _fetch_carpetas(empresa, structure_only=False)
    if error:
        return JsonResponse({"error": error, "carpetas": []}, status=500)
    return JsonResponse({"carpetas": carpetas})


def _count_files_in_folder(path):
    """Cuenta archivos por extensión en una carpeta (recursivo y paralelo) usando el endpoint básico."""
    conteo = Counter()
    try:
        items = _fetch_items(path)
        sub_paths = []
        for item in items:
            if item.get("type") == "file":
                name = item.get("name") or item.get("basename") or _parse_name(item.get("path", ""))
                if name and "." in name:
                    ext = name.rsplit(".", 1)[-1].lower()
                    conteo[ext] += 1
            elif item.get("type") == "folder":
                sub_name = _parse_name(item.get("path", ""))
                if sub_name:
                    sub_paths.append(f"{path}/{sub_name}")
        if sub_paths:
            with ThreadPoolExecutor(max_workers=6) as ex:
                for sub_conteo in ex.map(_count_files_in_folder, sub_paths):
                    conteo.update(sub_conteo)
        return dict(conteo)
    except Exception:
        return {}


@login_required
def api_carpetas_archivos(request):
    """GET: retorna subfolders con archivos para los sitios indicados.
    Params: empresa, carpetas (nombres separados por coma).
    Respuesta: {"Site1": [{"nombre": "SubA", "archivos": {"pdf": 2}}, ...], "Site2": [...]}
    Si nc-tekon-deep falla, usa nc-tekon para contar archivos por subcarpeta.
    """
    denied = _gate_api(request.user, "acceso_contratista")
    if denied:
        return denied
    empresa = request.GET.get("empresa", "")
    emp = company_loader.get_by_nombre(empresa)
    if not emp:
        return JsonResponse({"error": "Empresa no configurada."}, status=400)
    root_path = emp.root_path()
    carpetas_param = request.GET.get("carpetas", "")
    nombres_sitios = [s.strip() for s in carpetas_param.split(",") if s.strip()]
    resultado = {}
    ultima_actualizacion = {}
    try:
        for nombre in nombres_sitios:
            root_folder_path = f"{root_path}/{nombre}"

            # Comparar timestamp de Nextcloud con el cacheado
            ts = _get_folder_lastmod(root_folder_path)
            try:
                entry = SitioCache.objects.get(empresa=emp.nombre, sitio=nombre)
                if ts is not None and entry.ultima_actualizacion_ts == ts:
                    resultado[nombre] = entry.datos
                    if entry.ultima_actualizacion:
                        ultima_actualizacion[nombre] = entry.ultima_actualizacion
                    continue
            except SitioCache.DoesNotExist:
                pass

            # Caché ausente o desactualizado — re-fetchear
            subfolders = []
            try:
                deep = _fetch_deep(root_folder_path)
                subfolders = _parse_subfolders(deep)
            except Exception:
                pass
            if not subfolders:
                try:
                    items = _fetch_items(root_folder_path)
                    sub_items = [i for i in items if i.get("type") == "folder"]
                    if sub_items:

                        def get_sub_archivos(item):
                            sub_name = _parse_name(item["path"])
                            sub_path = f"{root_folder_path}/{sub_name}"
                            return {"nombre": sub_name, "archivos": _count_files_in_folder(sub_path)}

                        with ThreadPoolExecutor(max_workers=6) as ex:
                            subfolders = list(ex.map(get_sub_archivos, sub_items))
                        subfolders.sort(key=lambda s: s["nombre"])
                except Exception:
                    pass
            subs_sin_archivos = [s for s in subfolders if not s.get("archivos")]
            if subs_sin_archivos:
                def enrich_sub(sub, rfp=root_folder_path):
                    sub_path = f"{rfp}/{sub['nombre']}"
                    archivos = _count_files_in_folder(sub_path)
                    return {**sub, "archivos": archivos} if archivos else sub
                with ThreadPoolExecutor(max_workers=6) as ex:
                    enriched = {s["nombre"]: s for s in ex.map(enrich_sub, subs_sin_archivos)}
                subfolders = [enriched.get(s["nombre"], s) for s in subfolders]

            ultima_str = _format_lastmod(ts) if ts else ""
            if subfolders:  # solo cachear si hay datos reales
                SitioCache.objects.update_or_create(
                    empresa=emp.nombre,
                    sitio=nombre,
                    defaults={
                        "ultima_actualizacion_ts": ts,
                        "ultima_actualizacion": ultima_str,
                        "datos": subfolders,
                    }
                )
            resultado[nombre] = subfolders
            if ultima_str:
                ultima_actualizacion[nombre] = ultima_str
        return JsonResponse({**resultado, "ultima_actualizacion": ultima_actualizacion})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def api_final_tree(request):
    """GET: retorna árbol de proyectos en FINAL_ROOT_PATH.
    ?structure_only=1 → solo nombres de carpetas, sin conteo de archivos (rápido).
    """
    denied = _gate_api(request.user, "acceso_finales")
    if denied:
        return denied
    structure_only = request.GET.get("structure_only") in ("1", "true", "yes")
    try:
        children = _build_tree(FINAL_ROOT_PATH, structure_only=structure_only)
        return JsonResponse({"nombre": "20-PTI SP", "children": children})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def api_final_archivos(request):
    """GET: retorna árbol con conteo de archivos para los proyectos indicados.
    Params: proyectos (nombres separados por coma)
    Respuesta: {"Proyecto1": {"archivos": {...}, "children": [...]}, ...}
    """
    denied = _gate_api(request.user, "acceso_finales")
    if denied:
        return denied
    proyectos_param = request.GET.get("proyectos", "")
    nombres = [s.strip() for s in proyectos_param.split(",") if s.strip()]

    def get_proyecto(nombre):
        path = f"{FINAL_ROOT_PATH}/{nombre}"

        # Comparar timestamp de Nextcloud con el cacheado
        ts = _get_folder_lastmod(path)
        try:
            entry = ProyectoFinalCache.objects.get(nombre=nombre)
            if ts is not None and entry.ultima_actualizacion_ts == ts:
                return nombre, {**entry.datos, "ultima_actualizacion": entry.ultima_actualizacion}
        except ProyectoFinalCache.DoesNotExist:
            pass

        # Sin caché o timestamp distinto: re-fetchear
        children = _build_tree(path, max_depth=2)
        total: dict = {}
        for child in children:
            for ext, count in child.get("archivos", {}).items():
                total[ext] = total.get(ext, 0) + count
        ultima = _format_lastmod(ts) if ts else None
        data = {"archivos": total, "children": children}

        if children:  # solo cachear si hay datos reales
            ProyectoFinalCache.objects.update_or_create(
                nombre=nombre,
                defaults={
                    "ultima_actualizacion_ts": ts,
                    "ultima_actualizacion": ultima or "",
                    "datos": data,
                }
            )
        return nombre, {**data, "ultima_actualizacion": ultima}

    resultado = {}
    try:
        with ThreadPoolExecutor(max_workers=4) as ex:
            for nombre, data in ex.map(lambda n: get_proyecto(n), nombres):
                resultado[nombre] = data
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    return JsonResponse(resultado)
