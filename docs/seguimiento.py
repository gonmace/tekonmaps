"""Seguimiento de completitud de documentos del ITO.

La detección **no duplica** archivos: lee directamente dos fuentes y las une:

  - Carpeta del **constructor** ``/<20 EMPRESA>/<sitio>`` → documentos del constructor.
  - **Área ITO** ``/20-ITO_SEGUIMIENTO/<sitio>`` (plana) → donde la app sube, vía el botón
    "Subir", los documentos de la supervisión (ITO/Buscador/HSE/Eléctrico/TK).

Cada archivo se asigna al documento esperado de mayor ``score_match`` (por código/acrónimo),
sin importar en qué carpeta esté. Un documento está **presente** si tiene ≥1 archivo asignado;
**falta** si no. Los archivos que no calzan con ningún documento van a **inesperados**.
Además, cada rol responsable tiene una **confirmación** (``ConfirmacionDocumento``).
"""
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone as dt_timezone

from django.core.cache import cache as _cache
from django.db import IntegrityError, transaction
from django.utils import timezone as djtz

from . import company_loader, nextcloud
from .models import (
    ACCIONES_REVISION, ArchivoOculto, AsignacionArchivo, ConfirmacionDocumento,
    DocumentoEsperado, DocumentoNoNecesario, EliminacionPendiente,
    ObservacionDocumento, ROL_COLORES,
    SeguimientoCache, plantilla_de_sitio,
)


def _docs_de_sitio(empresa, sitio):
    """Documentos activos de la plantilla asignada al sitio (o la default)."""
    return list(DocumentoEsperado.objects.filter(
        plantilla=plantilla_de_sitio(empresa, sitio), activo=True))


def _plantilla_info(empresa, sitio):
    """Resumen de la plantilla en uso por el sitio: {id, nombre, es_propia}.
    ``es_propia`` = plantilla dedicada (no default y usada solo por este sitio)."""
    p = plantilla_de_sitio(empresa, sitio)
    es_propia = (not p.es_default
                 and p.sitios.count() == 1
                 and p.sitios.filter(empresa=empresa, sitio=sitio).exists())
    return {"id": p.id, "nombre": p.nombre, "es_propia": es_propia}


def _ext(nombre):
    i = nombre.rfind(".")
    return nombre[i + 1:].upper() if i > 0 else ""


# Multimedia: se clasifican por extensión en sus secciones (Imágenes / Videos), como enlaces.
IMG_EXTS = {"JPG", "JPEG", "PNG", "GIF", "HEIC", "HEIF", "WEBP", "BMP", "TIFF", "TIF", "SVG"}
VID_EXTS = {"MP4", "MOV", "AVI", "MKV", "WEBM", "M4V", "MPG", "MPEG", "3GP", "WMV", "FLV"}
# Etapa (dentro del área ITO del sitio) bajo la cual viven las carpetas multimedia.
MEDIA_ETAPA = "05_SEGUIMIENTO"
# Subcarpetas (dentro de ``<sitio>/05_SEGUIMIENTO``) donde el ITO/cualquiera sube multimedia.
MULTIMEDIA_DIRS = {"imagenes": "Imágenes", "videos": "Videos"}

ROOT_ITO = "/20-ITO_SEGUIMIENTO"
# Carpeta única (dentro del área ITO) donde viven los templates descargables.
TEMPLATES_PATH = f"{ROOT_ITO}/00-PLANTILLAS"


def asegurar_carpeta_templates():
    """Crea (idempotente) la carpeta de plantillas. Devuelve su ruta."""
    nextcloud.ensure_tree(TEMPLATES_PATH)
    return TEMPLATES_PATH

_MESES_ES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
_FORBIDDEN_FS = re.compile(r'[\\/<>:"|?*]+')


def _format_lastmod(ts):
    if not ts:
        return ""
    try:
        # ts es epoch (UTC); se muestra en la zona local activa (cookie del navegador).
        dt = djtz.localtime(datetime.fromtimestamp(ts, tz=dt_timezone.utc))
        return f"{dt.day:02d} {_MESES_ES[dt.month - 1]} {dt.year}"
    except (ValueError, TypeError, OSError, IndexError):
        return ""


def _format_fecha(dt):
    if not dt:
        return ""
    if djtz.is_aware(dt):
        dt = djtz.localtime(dt)
    return f"{dt.day:02d} {_MESES_ES[dt.month - 1]} {dt.year}"


def ito_path(sitio):
    """Carpeta del área ITO (donde la app sube los documentos de supervisión)."""
    return f"{ROOT_ITO}/{sitio}"


# Alias retrocompatible.
sitio_path = ito_path


def media_base(sitio):
    """Carpeta base de multimedia del sitio: ``<sitio>/05_SEGUIMIENTO`` en el área ITO."""
    return f"{ito_path(sitio)}/{MEDIA_ETAPA}"


def _codigo_sitio(sitio):
    """Extrae el código de sitio del nombre, ej. 'CL-AN-1300 (ZA380) …' → 'CL-AN-1300'."""
    m = re.match(r"\s*(CL-[A-Za-z]{2}-\d+)", sitio)
    return m.group(1) if m else ""


def sitios_generados(forzar=False):
    """Nombres de los sitios **ya generados** por la app: subcarpetas directas del área
    ITO (``/20-ITO_SEGUIMIENTO/``), que nacen al subir el primer documento de un sitio.
    Devuelve un set (cacheado, TTL 5 min). Set vacío si falla/no existe el área."""
    if not forzar:
        cached = _cache.get("seg:sitios_generados")
        if cached is not None:
            return cached
    try:
        nombres = set(nextcloud.list_subfolders(ROOT_ITO))
    except Exception:
        return set()
    _cache.set("seg:sitios_generados", nombres, 300)
    return nombres


def listar_sitios():
    """Enumera los sitios desde las carpetas de empresa actuales (solo lectura).
    Devuelve [{'empresa': str, 'sitio': str}] ordenado por empresa y sitio."""
    out = []
    for emp in company_loader.get_all():
        try:
            for nombre in nextcloud.list_subfolders(emp.root_path()):
                out.append({"empresa": emp.nombre, "sitio": nombre})
        except Exception:
            continue
    return out


# ── Estado del sitio ─────────────────────────────────────────────────────────
def _roles(d, confs, obs=None):
    """Roles activos del documento con su estado de confirmación y observación.
    ``confs``: {campo_rol → {usuario, fecha}}. ``obs``: {campo_rol → {usuario, texto, fecha}}
    (revisor **no conforme**). ``modo`` = 'revision' (check manual con modal) o 'produccion'
    (se auto-confirma al subir)."""
    obs = obs or {}
    out = []
    for campo, lbl, sigla in DocumentoEsperado.ROLES:
        accion = getattr(d, campo)
        if accion:
            c = confs.get(campo)
            o = obs.get(campo)
            out.append({
                "rol": campo, "label": lbl, "sigla": sigla, "accion": accion,
                "color": ROL_COLORES.get(sigla, "#6b7280"),
                "modo": "revision" if accion in ACCIONES_REVISION else "produccion",
                "es_constructor": campo == "rol_constructor",
                "confirmado": bool(c),
                "usuario": c["usuario"] if c else "",
                "fecha": c["fecha"] if c else "",
                "observacion": o["texto"] if o else "",
                "obs_usuario": o["usuario"] if o else "",
                "obs_fecha": o["fecha"] if o else "",
                "obs_enmendada": o["enmendada"] if o else False,
            })
    return out


# Etiqueta y sigla por campo de rol (para observaciones de roles que no son revisores
# activos del documento, p. ej. una observación general de TK Redline).
_ROL_META = {campo: (lbl, sigla) for campo, lbl, sigla in DocumentoEsperado.ROLES}


def _obs_lista(obs):
    """Lista plana de observaciones del documento (de **cualquier** rol, sea o no revisor
    activo), para el panel desplegable central. ``obs``: {campo_rol → {usuario, texto,
    fecha, enmendada}}."""
    out = []
    for campo, o in (obs or {}).items():
        lbl, sigla = _ROL_META.get(campo, (campo, (campo[:3] or "?").upper()))
        out.append({
            "rol": campo, "label": lbl, "sigla": sigla,
            "color": ROL_COLORES.get(sigla, "#6b7280"),
            "observacion": o["texto"], "obs_usuario": o["usuario"],
            "obs_fecha": o["fecha"], "obs_enmendada": o["enmendada"],
        })
    out.sort(key=lambda x: x["sigla"])
    return out


def _doc_dict(d, estado, fecha, archivos, roles, necesario=True, obs=None):
    observaciones = _obs_lista(obs)
    return {
        "id": d.id, "etapa": d.etapa, "etapa_display": d.get_etapa_display(),
        "carpeta": d.carpeta, "nombre": d.nombre, "codigo": d.codigo, "orden": d.orden,
        "tipo_esperado": d.tipo_esperado, "necesario": necesario,
        "galeria": d.galeria,
        "roles": roles, "estado": estado, "fecha": fecha, "archivos": archivos,
        "observaciones": observaciones,
        "tiene_warning": any(not o["obs_enmendada"] for o in observaciones),
    }


def _confirmaciones(empresa, sitio):
    """{doc_id → {campo_rol → {usuario, fecha}}} para el sitio."""
    out = {}
    qs = ConfirmacionDocumento.objects.filter(empresa=empresa, sitio=sitio).select_related("usuario")
    for c in qs:
        out.setdefault(c.documento_id, {})[c.rol] = {
            "usuario": c.usuario.get_username() if c.usuario else "",
            "fecha": _format_fecha(c.fecha),
        }
    return out


def _observaciones(empresa, sitio):
    """{doc_id → {campo_rol → {usuario, texto, fecha}}}: observaciones de 'no conforme'."""
    out = {}
    qs = ObservacionDocumento.objects.filter(empresa=empresa, sitio=sitio).select_related("usuario")
    for o in qs:
        out.setdefault(o.documento_id, {})[o.rol] = {
            "usuario": o.usuario.get_username() if o.usuario else "",
            "texto": o.texto,
            "fecha": _format_fecha(o.fecha),
            "enmendada": o.enmendada,
        }
    return out


def roles_estado(empresa, sitio, doc):
    """Estado actual de los roles del documento (confirmaciones + observaciones), para que el
    front refresque la fila tras una subida sin reconsultar Nextcloud."""
    conf = _confirmaciones(empresa, sitio).get(doc.id, {})
    obs = _observaciones(empresa, sitio).get(doc.id, {})
    return _roles(doc, conf, obs)


def _estado_vacio(empresa, sitio, docs, conf_map, error=""):
    documentos, agregados = [], {}
    for d in docs:
        documentos.append(_doc_dict(d, "falta", "", [], _roles(d, conf_map.get(d.id, {}))))
        ag = agregados.setdefault(d.etapa, {
            "etapa_display": d.get_etapa_display(), "total": 0, "presentes": 0})
        ag["total"] += 1
    return {
        "sitio": sitio, "empresa": empresa, "documentos": documentos, "agregados": agregados,
        "inesperados": [], "total": len(documentos),
        "presentes": 0, "plantilla": _plantilla_info(empresa, sitio), "error": error,
    }


def _archivos_de(base):
    """Lista de archivos (no dirs) bajo ``base`` o None si hubo error de red."""
    try:
        items = nextcloud.tree(base, max_depth=5)
    except Exception:
        return None
    return [{"path": it["path"], "nombre": it["nombre"],
             "fecha": _format_lastmod(it["mtime"]), "mtime": it["mtime"] or 0,
             "base": base}
            for it in items if not it["es_dir"]]


def roots_constructora(forzar=False):
    """Carpetas raíz que empiezan con '20' (posibles carpetas de constructora), excepto
    el área ITO (``ROOT_ITO``). Se descubren dinámicamente desde Nextcloud y se cachean
    (TTL 10 min). ``forzar`` re-descubre (p. ej. al crear una empresa nueva como
    ``/20-PROSANGES``)."""
    if not forzar:
        roots = _cache.get("seg:roots20")
        if roots is not None:
            return roots
    # Nombre canónico del área ITO (sin sufijo ' (N)'): NUNCA se escanea como
    # constructora (se lee aparte). Excluye también duplicados '… (2)'.
    ito_name = ROOT_ITO.lstrip("/")
    try:
        items = [(it["path"], it["nombre"]) for it in nextcloud.list_folder("/")
                 if it["es_dir"] and it["nombre"].startswith("20")]
    except Exception:
        return []
    # Dedup de montajes duplicados de Nextcloud ('20 AJ (2)' es el mismo contenido que
    # '20 AJ'): se prefiere el nombre sin sufijo ' (N)' para no contar dos veces los archivos.
    canon = {}
    for path, name in items:
        base = re.sub(r"\s*\(\d+\)$", "", name)
        if base == ito_name:  # área ITO y sus duplicados → nunca como constructora
            continue
        if base not in canon or name == base:
            canon[base] = path
    roots = sorted(canon.values())
    _cache.set("seg:roots20", roots, 600)
    return roots


def _ck_cons(root, code, sitio):
    # Clave segura (root/código llevan espacios y '/').
    h = hashlib.md5(f"{root}|{code or sitio}".encode("utf-8")).hexdigest()
    return f"seg:cons:{h}"


# ── Fast-path: firma por carpeta de sitio ────────────────────────────────────
# Si la fecha de la carpeta del sitio (dentro de cada root /20* + el área ITO) no
# cambió, se sirve el `datos` cacheado sin re-listar roots ni re-asignar. El TTL
# fuerza un re-descubrimiento periódico (p. ej. si el sitio aparece en un root nuevo).
FASTPATH_TTL = 21600  # 6 h (la detección de cambios la da la fecha, no el TTL)


def _fp_key(cache_key):
    h = hashlib.md5(cache_key.encode("utf-8")).hexdigest()
    return f"seg:fp:{h}"


def _set_fp(cache_key, paths, firma, archivos):
    """Guarda/renueva la entrada del fast-path (renueva el TTL en cada uso)."""
    _cache.set(_fp_key(cache_key),
               {"paths": paths, "firma": firma, "archivos": archivos}, FASTPATH_TTL)


def _firma_actual(paths):
    """{path: folder_lastmod(path)} en paralelo (la 'fecha' de cada carpeta de sitio)."""
    if not paths:
        return {}
    with ThreadPoolExecutor(max_workers=min(8, len(paths))) as ex:
        vals = list(ex.map(nextcloud.folder_lastmod, paths))
    return dict(zip(paths, vals))


def _firma_paths(fuentes, listados, sitio):
    """Carpetas a vigilar: la subcarpeta del sitio dentro de cada root (la que matchea el
    código), el root mismo si hay archivos sueltos con el código, y la carpeta del sitio en
    el área ITO."""
    paths = set()
    for (root, _c), lst in zip(fuentes, listados):
        if not lst:
            continue
        for it in lst["subdirs"]:
            paths.add(it["path"])
        if lst["sueltos"]:
            paths.add(root)
    paths.add(ito_path(sitio))
    return sorted(paths)


def _firma_root_sitio(root, code, sitio):
    """**Fase 1 (barata, paralelizable)**: lista ``root`` (Depth 1, un solo PROPFIND) y arma
    ``{"firma": float, "subdirs": [...], "sueltos": [...]}`` con las subcarpetas/archivos del
    sitio y el max-mtime (la *firma*). NO hace escaneo profundo (eso usa su propio pool de
    hilos y no debe anidarse). Con ``code``: coincidencia por contenido; sin ``code``:
    nombre exacto del sitio. Devuelve ``None`` si falló la red en ``root``."""
    try:
        items = nextcloud.list_folder(root)
    except Exception:
        return None
    cl = (code or sitio).lower()
    subdirs, sueltos, firma = [], [], 0.0
    for it in items:
        nombre = it["nombre"]
        if it["es_dir"]:
            if (cl in nombre.lower()) if code else (nombre == sitio):
                subdirs.append(it)
                firma = max(firma, it["mtime"] or 0)
        elif code and cl in nombre.lower():  # archivo suelto en la raíz con el código
            sueltos.append(it)
            firma = max(firma, it["mtime"] or 0)
    return {"firma": firma, "subdirs": subdirs, "sueltos": sueltos}


def _resolver_archivos_root(root, code, sitio, listado, forzar=False):
    """**Fase 2 (secuencial)**: dado el ``listado`` de :func:`_firma_root_sitio`, devuelve los
    archivos del sitio en ``root`` reutilizando el escaneo profundo cacheado si la firma no
    cambió, o re-escaneando a fondo si cambió (o ``forzar``). Secuencial a propósito: el
    escaneo profundo (``nextcloud.tree``) ya paraleliza internamente.

    Nunca **envenena** la caché: si un escaneo profundo falla (red/tiempo), devuelve el último
    resultado bueno y NO sobrescribe. ``listado is None`` → error de red en el Depth 1."""
    key = _ck_cons(root, code, sitio)
    cached = _cache.get(key)
    if listado is None:
        return cached.get("archivos") if isinstance(cached, dict) else None
    firma = listado["firma"]
    if not forzar and isinstance(cached, dict) and cached.get("firma") == firma:
        return cached["archivos"]            # nada cambió → reutiliza el escaneo profundo
    archivos, fallo = [], False
    for it in listado["subdirs"]:
        r = _archivos_de(it["path"])
        if r is None:
            fallo = True
        else:
            archivos.extend(r)
    for it in listado["sueltos"]:
        archivos.append({"path": it["path"], "nombre": it["nombre"],
                         "fecha": _format_lastmod(it["mtime"]), "mtime": it["mtime"] or 0,
                         "base": root})
    if fallo:
        if isinstance(cached, dict):
            return cached["archivos"]
        return archivos or None
    _cache.set(key, {"firma": firma, "archivos": archivos}, 86400)  # invalida por firma, no por tiempo
    return archivos


def _ensamblar_datos(empresa, sitio, archivos, ito_base):
    """Construye ``datos`` (asignación + agregados + multimedia/inesperados) a partir de la
    lista ``archivos`` ya escaneada y el estado **actual de la BD** (documentos,
    confirmaciones, necesario, asignaciones). **No lee Nextcloud**: se reutiliza cuando solo
    cambió la BD (editar documento, confirmar, marcar necesario). Devuelve ``(datos, max_ts)``."""
    docs = _docs_de_sitio(empresa, sitio)
    conf_map = _confirmaciones(empresa, sitio)
    obs_map = _observaciones(empresa, sitio)
    pendientes = set(EliminacionPendiente.objects.filter(
        empresa=empresa, sitio=sitio).values_list("path", flat=True))
    ocultos = set(ArchivoOculto.objects.filter(
        empresa=empresa, sitio=sitio).values_list("path", flat=True))
    for a in archivos:  # origen del archivo: del constructor o subido por TKR (área ITO)
        a["origen"] = "ito" if a["base"] == ito_base else "constructor"

    # Asignación, por prioridad:
    #  1. Asignación registrada en BD (la crea la subida del ITO y la asignación manual).
    #  2. Por nombre → documento de mayor score_match.
    #  3. Por carpeta (solo área ITO): archivos dentro de la carpeta contenedora de un
    #     documento que no calzan por nombre se le asignan igual (p. ej. las fotos del
    #     "Registro fotográfico", que viven en ``05_SEGUIMIENTO/Imágenes``).
    #  4. Multimedia suelta (imagen/video) que no calzó por nada → al documento que representa
    #     ``05_SEGUIMIENTO/Imágenes`` (o ``/Videos``), **viva donde viva** (incluida la carpeta
    #     de constructora), para que se liste bajo él en vez de quedar oculta.
    ids_activos = {d.id for d in docs}
    asig_manual = {
        p: did for p, did in AsignacionArchivo.objects.filter(
            empresa=empresa, sitio=sitio).values_list("path", "documento_id")
        if did in ids_activos
    }
    # Carpeta contenedora → documento, solo cuando es única (sin ambigüedad).
    por_carpeta = {}
    for d in docs:
        por_carpeta.setdefault(d.carpeta_contenedora(), []).append(d)
    carpeta_unica = {c: ds[0].id for c, ds in por_carpeta.items() if len(ds) == 1}
    # Documentos de las carpetas multimedia del sitio (si existen en la plantilla).
    media_img_doc = carpeta_unica.get(f"{MEDIA_ETAPA}/{MULTIMEDIA_DIRS['imagenes']}")
    media_vid_doc = carpeta_unica.get(f"{MEDIA_ETAPA}/{MULTIMEDIA_DIRS['videos']}")
    ito_prefix = ito_base + "/"
    asignados, matched_paths = {}, set()
    for a in archivos:
        doc_id = asig_manual.get(a["path"])
        if doc_id is None:
            mejor, mejor_s = None, 0
            for d in docs:
                s = d.score_match(a["nombre"])
                if s > mejor_s:
                    mejor, mejor_s = d, s
            doc_id = mejor.id if mejor else None
        if doc_id is None and a["path"].startswith(ito_prefix):
            rel = a["path"][len(ito_prefix):]
            contenedora = rel.rsplit("/", 1)[0] if "/" in rel else ""
            doc_id = carpeta_unica.get(contenedora)
        if doc_id is None:  # multimedia suelta → documento Imágenes/Videos del sitio
            e = _ext(a["nombre"])
            if e in IMG_EXTS:
                doc_id = media_img_doc
            elif e in VID_EXTS:
                doc_id = media_vid_doc
        if doc_id is not None:
            asignados.setdefault(doc_id, []).append(a)
            matched_paths.add(a["path"])

    no_nec = set(DocumentoNoNecesario.objects.filter(
        empresa=empresa, sitio=sitio).values_list("documento_id", flat=True))

    documentos, agregados = [], {}
    max_ts = None
    for d in docs:
        necesario = d.id not in no_nec
        asig = sorted(asignados.get(d.id, []), key=lambda a: a["nombre"].lower())
        presente = d.tipo_ok([_ext(a["nombre"]) for a in asig])
        fecha_ts = max((a["mtime"] for a in asig), default=None)
        if fecha_ts and (max_ts is None or fecha_ts > max_ts):
            max_ts = fecha_ts
        documentos.append(_doc_dict(
            d, "presente" if presente else "falta", _format_lastmod(fecha_ts),
            [{"nombre": a["nombre"], "fecha": a["fecha"], "path": a["path"],
              "origen": a["origen"], "pendiente_eliminar": a["path"] in pendientes,
              "oculto": a["path"] in ocultos, "asignado": a["path"] in asig_manual}
             for a in asig],
            _roles(d, conf_map.get(d.id, {}), obs_map.get(d.id, {})), necesario=necesario,
            obs=obs_map.get(d.id, {}),
        ))
        ag = agregados.setdefault(d.etapa, {
            "etapa_display": d.get_etapa_display(), "total": 0, "presentes": 0})
        # Los documentos "no necesarios" no cuentan en la completitud.
        if necesario:
            ag["total"] += 1
            if presente:
                ag["presentes"] += 1

    # Inesperados: archivos del área que no calzan con ningún documento. Las imágenes/videos
    # se asignan al documento Imágenes/Videos del sitio (ver prioridad 4) y salen bajo él; solo
    # se omiten aquí si la plantilla NO tiene ese documento (para no saturar la lista).
    inesperados = []
    for a in archivos:
        if a["path"] in matched_paths:
            continue
        e = _ext(a["nombre"])
        if e in IMG_EXTS or e in VID_EXTS:  # multimedia sin documento Imágenes/Videos → no se lista
            continue
        base = a["base"]
        rel = a["path"][len(base) + 1:] if a["path"].startswith(base + "/") else a["path"]
        inesperados.append({"carpeta": rel.rsplit("/", 1)[0] if "/" in rel else "",
                            "nombre": a["nombre"], "fecha": a["fecha"], "origen": a["origen"],
                            "path": a["path"]})
    inesperados.sort(key=lambda x: (x["carpeta"].lower(), x["nombre"].lower()))

    datos = {
        "sitio": sitio, "empresa": empresa,
        "carpeta_ito": ito_base,
        "documentos": documentos, "agregados": agregados, "inesperados": inesperados,
        "total": sum(1 for x in documentos if x["necesario"]),
        "presentes": sum(1 for x in documentos if x["necesario"] and x["estado"] == "presente"),
        "plantilla": _plantilla_info(empresa, sitio),
        "error": "",
    }
    return datos, max_ts


def estado_sitio(empresa, sitio, forzar=False, forzar_root=None):
    """Completitud de un sitio: agrega los archivos de constructora desde **todas las
    carpetas /20\\*** (salvo el área ITO) cuya subcarpeta coincide con el código del sitio,
    más el área ITO. Cachea por (empresa, sitio); ante fallo de red usa el último snapshot.

    **Fast-path por timestamp:** se guarda la *fecha* (mtime) de la carpeta del sitio dentro de
    cada root + el área ITO, junto con la lista ``archivos`` escaneada. Si esas fechas no
    cambiaron, se **reconstruye** ``datos`` desde los ``archivos`` cacheados y el estado actual
    de la BD — **sin leer Nextcloud a fondo** — así los cambios de BD (editar documento,
    confirmar, marcar necesario) se reflejan al instante. ``forzar=True`` (``?refresh=1``)
    re-escanea todo; ``forzar_root='/20 X'`` re-escanea SOLO esa carpeta."""
    cache_key = f"{empresa}/{sitio}"
    ito_base = ito_path(sitio)
    configurado = nextcloud.is_configured()

    # Fast-path: la fecha de las carpetas del sitio no cambió → reusar `archivos` cacheados y
    # reconstruir `datos` desde la BD actual (sin escaneo profundo de Nextcloud).
    if configurado and not forzar and forzar_root is None:
        fp = _cache.get(_fp_key(cache_key))
        if fp and fp.get("archivos") is not None:
            actual = _firma_actual(fp["paths"])
            if actual == fp["firma"]:
                # Renueva el TTL del fp en cada uso → un sitio activo no se "enfría".
                _set_fp(cache_key, fp["paths"], actual, fp["archivos"])
                datos, max_ts = _ensamblar_datos(empresa, sitio, fp["archivos"], ito_base)
                SeguimientoCache.objects.update_or_create(
                    sitio=cache_key, defaults={"ultima_actualizacion_ts": max_ts, "datos": datos})
                return datos

    if not configurado:
        docs = _docs_de_sitio(empresa, sitio)
        conf_map = _confirmaciones(empresa, sitio)
        return _estado_vacio(empresa, sitio, docs, conf_map, error="Nextcloud no está configurado.")

    _asegurar_carpetas_media(sitio)  # crea Imágenes/Videos (idempotente, guardado por caché)

    code = _codigo_sitio(sitio)
    # Fuentes: cada carpeta /20* (por código de sitio) + el área ITO (match exacto, code=None).
    # La invalidación por mtime evita re-escanear lo que no cambió.
    fuentes = [(root, code) for root in roots_constructora(forzar=forzar)] + [(ROOT_ITO, None)]
    # Fase 1 (PARALELA, barata): lista Depth-1 cada fuente para leer mtimes (PROPFINDs simples,
    # no anidan el pool de ``nextcloud.tree``).
    with ThreadPoolExecutor(max_workers=min(8, len(fuentes))) as ex:
        listados = list(ex.map(lambda f: _firma_root_sitio(f[0], f[1], sitio), fuentes))
    # Fase 2 (SECUENCIAL): escaneo profundo solo de las fuentes cuya firma cambió.
    resultados = [
        _resolver_archivos_root(root, c, sitio, lst, forzar=(forzar or forzar_root == root))
        for (root, c), lst in zip(fuentes, listados)
    ]
    if all(r is None for r in resultados):  # toda la red falló
        try:
            return SeguimientoCache.objects.get(sitio=cache_key).datos
        except SeguimientoCache.DoesNotExist:
            docs = _docs_de_sitio(empresa, sitio)
            conf_map = _confirmaciones(empresa, sitio)
            return _estado_vacio(empresa, sitio, docs, conf_map, error="No se pudo conectar a Nextcloud.")

    archivos = [a for r in resultados if r for a in r]
    datos, max_ts = _ensamblar_datos(empresa, sitio, archivos, ito_base)
    SeguimientoCache.objects.update_or_create(
        sitio=cache_key, defaults={"ultima_actualizacion_ts": max_ts, "datos": datos})
    # Guarda firma + `archivos` para el fast-path. Resiliente: basta con que la carga produjera
    # resultado; `_firma_paths` ya omite las fuentes que fallaron (un root flaky no bloquea el fp).
    fpaths = _firma_paths(fuentes, listados, sitio)
    _set_fp(cache_key, fpaths, _firma_actual(fpaths), archivos)
    return datos


def invalidar_cache(empresa, sitio):
    """Invalidación total (cambió **Nextcloud**: subida/eliminación de archivo): borra el
    `datos` cacheado y la firma/archivos del fast-path → la próxima carga re-escanea."""
    cache_key = f"{empresa}/{sitio}"
    SeguimientoCache.objects.filter(sitio=cache_key).delete()
    _cache.delete(_fp_key(cache_key))


def invalidar_datos(empresa, sitio):
    """Invalidación ligera (cambió **solo la BD**: confirmar/necesario/asignar): borra el
    `datos` cacheado pero **conserva** la firma/archivos del fast-path, para que la próxima
    carga reconstruya `datos` desde lo escaneado sin volver a leer Nextcloud."""
    SeguimientoCache.objects.filter(sitio=f"{empresa}/{sitio}").delete()


# ── Guardar la estructura mostrada en la plantilla asignada (en su lugar) ─────
def guardar_estructura(empresa, sitio):
    """Guarda la estructura **que se ve** (los documentos de la plantilla asignada, con tus
    ediciones) en la **plantilla asignada, en su lugar**. NO re-escanea carpetas de Nextcloud y
    NO crea copias por sitio: como la estructura que ves ya vive en esa plantilla, la deja tal
    cual y la **comparte** — todos los sitios que usan la misma plantilla quedan iguales. Solo
    refresca la marca de tiempo e invalida la caché. Devuelve un resumen
    ``{plantilla, id, total, es_default, n_sitios}``."""
    target = plantilla_de_sitio(empresa, sitio)
    target.save(update_fields=["actualizado"])  # toca la marca de tiempo (auto_now)
    total = target.documentos.filter(activo=True).count()
    invalidar_cache(empresa, sitio)
    return {"plantilla": target.nombre, "id": target.id, "total": total,
            "es_default": target.es_default, "n_sitios": target.sitios.count()}


# ── Subida de documentos de supervisión al área ITO ──────────────────────────
def _sanitize_archivo(nombre):
    nombre = _FORBIDDEN_FS.sub("-", str(nombre))
    return re.sub(r"\s+", " ", nombre).strip(" .")[:200] or "documento"


def _asegurar_carpetas_media(sitio):
    """Crea (idempotente) las carpetas Imágenes/Videos del sitio en el área ITO, para que el
    ITO o cualquiera pueda subir ahí. Guardado por caché (una vez por ventana) para no repetir
    MKCOL en cada carga."""
    key = "seg:mediadirs:" + hashlib.md5(sitio.encode("utf-8")).hexdigest()
    if _cache.get(key):
        return
    try:
        for carpeta in MULTIMEDIA_DIRS.values():
            nextcloud.ensure_tree(f"{media_base(sitio)}/{carpeta}")
        _cache.set(key, True, 3600)
    except Exception:
        pass


def subir_multimedia(sitio, tipo, contenido, filename, content_type=None):
    """Sube una imagen/video a ``/20-ITO_SEGUIMIENTO/<sitio>/<Imágenes|Videos>``.
    ``tipo`` ∈ {'imagenes','videos'}. Devuelve la ruta destino."""
    carpeta = MULTIMEDIA_DIRS.get(tipo)
    if not carpeta:
        raise ValueError("Tipo de multimedia inválido.")
    base = f"{media_base(sitio)}/{carpeta}"
    nextcloud.ensure_tree(base)
    destino = f"{base}/{_sanitize_archivo(filename)}"
    nextcloud.upload(destino, contenido, content_type or "application/octet-stream")
    return destino


def subir_documento(empresa, sitio, doc, contenido, filename, content_type=None,
                    usuario=None):
    """Sube ``contenido`` a la **carpeta de la etapa** del documento en el área ITO
    (``etapa/[CARPETA]``, sin crear subcarpeta por documento), conservando el nombre
    ``filename``. Registra la **asignación** del archivo al documento en la BD (así
    queda asociado sin depender del nombre). Si ``usuario`` tiene un rol ITO en el
    documento (producción **o** revisión), auto-confirma ese rol. Devuelve la ruta
    destino."""
    base = f"{ito_path(sitio)}/{doc.carpeta_contenedora()}"
    nextcloud.ensure_tree(base)
    destino = f"{base}/{_sanitize_archivo(filename)}"
    nextcloud.upload(destino, contenido, content_type or "application/octet-stream")
    AsignacionArchivo.objects.update_or_create(
        empresa=empresa, sitio=sitio, path=destino,
        defaults={"documento": doc, "usuario": usuario})
    # Hay archivo nuevo → la revisión debe rehacerse sobre lo cargado: se reinician
    # las confirmaciones de revisión y se limpian las observaciones (el ⚠ ya se corrigió).
    for c in ConfirmacionDocumento.objects.filter(empresa=empresa, sitio=sitio, documento=doc):
        if getattr(doc, c.rol, "") in ACCIONES_REVISION:
            c.delete()
    ObservacionDocumento.objects.filter(empresa=empresa, sitio=sitio, documento=doc).delete()
    _autoconfirmar(empresa, sitio, doc, usuario)
    invalidar_cache(empresa, sitio)
    return destino


def nombre_sugerido(doc, sitio, filename):
    """Nombre sugerido para el Panel/front: el código del documento con el código de
    sitio real. Vacío si el documento no tiene código."""
    if not doc.codigo:
        return ""
    code = _codigo_sitio(sitio)
    ext = "." + filename.rsplit(".", 1)[1] if "." in filename else ""
    base = doc.codigo.replace("CL-XX-0000", code) if code else doc.codigo
    return f"{base}{ext}"


def renombrar_archivo(empresa, sitio, path, nuevo_nombre):
    """Renombra un archivo **en su misma carpeta** de Nextcloud (típicamente al nombre que
    dicta la plantilla) y re-apunta los registros de BD que lo referencian por ``path``
    (asignación manual, eliminación pendiente, archivo oculto), para que el archivo conserve
    su documento y sus marcas. No toca confirmaciones ni observaciones (el contenido no
    cambió). Devuelve la ruta nueva. Lanza :class:`nextcloud.DestinoExiste` si ya hay un
    archivo con ese nombre."""
    nombre = _sanitize_archivo(nuevo_nombre)
    carpeta = path.rsplit("/", 1)[0]
    destino = f"{carpeta}/{nombre}"
    if destino == path:
        return path
    nextcloud.move(path, destino)
    for model in (AsignacionArchivo, EliminacionPendiente, ArchivoOculto):
        try:
            with transaction.atomic():
                model.objects.filter(empresa=empresa, sitio=sitio, path=path).update(path=destino)
        except IntegrityError:  # ya había una fila para el destino → basta quitar la vieja
            model.objects.filter(empresa=empresa, sitio=sitio, path=path).delete()
    invalidar_cache(empresa, sitio)
    return destino


def limpiar_autoconfirmaciones(empresa, sitio, path):
    """Al borrar un archivo: quita su asignación y, si el documento queda sin archivos
    asignados, limpia las confirmaciones de roles de **producción** (auto-confirmadas
    al subir). Las de revisión (manuales) se conservan."""
    asig = AsignacionArchivo.objects.filter(empresa=empresa, sitio=sitio, path=path).first()
    if not asig:
        return
    doc = asig.documento
    asig.delete()
    if AsignacionArchivo.objects.filter(empresa=empresa, sitio=sitio, documento=doc).exists():
        return  # aún quedan archivos asignados a este documento
    for c in ConfirmacionDocumento.objects.filter(empresa=empresa, sitio=sitio, documento=doc):
        if getattr(doc, c.rol, "") not in ACCIONES_REVISION:
            c.delete()


def _autoconfirmar(empresa, sitio, doc, usuario):
    """Al subir, confirma el rol del usuario que sube, sea cual sea su acción:
    producción **o revisión** (REVISAR/FIRMAR). Es decir, subir el archivo cuenta
    como que ese rol hizo su parte (su botón de revisión/firma queda confirmado).
    Se llama después de reiniciar las confirmaciones de revisión del documento, así
    que solo sobrevive la del rol que acaba de subir."""
    rol = getattr(getattr(usuario, "profile", None), "rol", "") if usuario else ""
    if not rol or rol == "visitante":
        return
    accion = getattr(doc, rol, "")
    if accion:
        ConfirmacionDocumento.objects.update_or_create(
            empresa=empresa, sitio=sitio, documento=doc, rol=rol,
            defaults={"usuario": usuario})
