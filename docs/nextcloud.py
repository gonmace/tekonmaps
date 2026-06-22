"""Cliente WebDAV para Nextcloud (acceso directo, reemplaza los webhooks n8n).

Lee la configuración de ``settings`` (NEXTCLOUD_BASE_URL / NEXTCLOUD_USER /
NEXTCLOUD_APP_PASSWORD), que provienen de ``.env`` vía python-decouple.

Operaciones soportadas:
  - Lectura: PROPFIND → ``list_folder``, ``list_files``, ``tree``, ``folder_lastmod``.
  - Escritura controlada: ``mkcol`` / ``ensure_tree`` (solo crean carpetas, p. ej. la
    estructura de seguimiento). Nunca se hace PUT/DELETE/MOVE: el cliente no modifica
    ni borra archivos existentes.

Las rutas (``path``) son relativas a la raíz de archivos del usuario, p. ej.
``"/20 AJ/Sitio 1"``. Cada segmento se codifica para URL automáticamente.
"""
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from urllib.parse import quote, unquote, urlsplit
import xml.etree.ElementTree as ET

import requests
from django.conf import settings

_DAV = "{DAV:}"

_PROPFIND_BODY = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<d:propfind xmlns:d="DAV:">'
    '<d:prop>'
    '<d:getlastmodified/>'
    '<d:getcontentlength/>'
    '<d:resourcetype/>'
    '</d:prop>'
    '</d:propfind>'
)


class NextcloudNotConfigured(RuntimeError):
    """Faltan credenciales de Nextcloud en el entorno."""


def is_configured():
    return bool(_base_url() and settings.NEXTCLOUD_USER and settings.NEXTCLOUD_APP_PASSWORD)


def _base_url():
    return (settings.NEXTCLOUD_BASE_URL or "").rstrip("/")


def _auth():
    return (settings.NEXTCLOUD_USER, settings.NEXTCLOUD_APP_PASSWORD)


def _norm(path):
    """Normaliza a '/a/b' (sin barra final, con barra inicial)."""
    return "/" + path.strip("/")


def _url(path):
    """URL absoluta para una ruta relativa a la raíz del usuario."""
    if not is_configured():
        raise NextcloudNotConfigured(
            "Configura NEXTCLOUD_BASE_URL, NEXTCLOUD_USER y NEXTCLOUD_APP_PASSWORD en .env."
        )
    segments = [quote(seg) for seg in path.strip("/").split("/") if seg]
    suffix = "/".join(segments)
    return f"{_base_url()}/{suffix}" if suffix else f"{_base_url()}/"


def _dav_prefix():
    """Prefijo de ruta del DAV, ej. '/remote.php/dav/files/svc-seguimiento'."""
    return urlsplit(_base_url()).path.rstrip("/")


def _parse_http_date(s):
    try:
        return parsedate_to_datetime(s).timestamp()
    except (TypeError, ValueError):
        return None


def _parse_multistatus(content, base_path):
    """Convierte la respuesta XML 'multistatus' en una lista de items, omitiendo
    la propia carpeta consultada."""
    root = ET.fromstring(content)
    prefix = _dav_prefix()
    base_rel = _norm(base_path)
    items = []
    for resp in root.findall(f"{_DAV}response"):
        href_el = resp.find(f"{_DAV}href")
        if href_el is None or not href_el.text:
            continue
        rel = unquote(urlsplit(href_el.text).path)
        if prefix and rel.startswith(prefix):
            rel = rel[len(prefix):]
        rel = _norm(rel)
        if rel == base_rel:  # la carpeta misma
            continue
        es_dir = False
        mtime = None
        size = None
        for propstat in resp.findall(f"{_DAV}propstat"):
            status = propstat.find(f"{_DAV}status")
            if status is not None and "200" not in (status.text or ""):
                continue
            prop = propstat.find(f"{_DAV}prop")
            if prop is None:
                continue
            rtype = prop.find(f"{_DAV}resourcetype")
            if rtype is not None and rtype.find(f"{_DAV}collection") is not None:
                es_dir = True
            glm = prop.find(f"{_DAV}getlastmodified")
            if glm is not None and glm.text:
                mtime = _parse_http_date(glm.text)
            gcl = prop.find(f"{_DAV}getcontentlength")
            if gcl is not None and gcl.text:
                try:
                    size = int(gcl.text)
                except ValueError:
                    size = None
        items.append({
            "path": rel,
            "nombre": rel.split("/")[-1],
            "es_dir": es_dir,
            "mtime": mtime,
            "size": size,
        })
    return items


def _propfind(path, depth):
    resp = requests.request(
        "PROPFIND", _url(path), auth=_auth(),
        headers={"Depth": str(depth), "Content-Type": "application/xml"},
        data=_PROPFIND_BODY, timeout=30,
    )
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    return _parse_multistatus(resp.content, path)


# ── Lectura ──────────────────────────────────────────────────────────────────
def list_folder(path):
    """Items directos (carpetas y archivos) de ``path`` (Depth 1)."""
    return _propfind(path, 1)


def list_files(path):
    """Lista ``[(nombre, mtime)]`` de los archivos (no carpetas) directos de ``path``."""
    return [(i["nombre"], i["mtime"]) for i in _propfind(path, 1) if not i["es_dir"]]


def list_subfolders(path):
    """Nombres de las subcarpetas directas de ``path`` (ordenados)."""
    return sorted(i["nombre"] for i in _propfind(path, 1) if i["es_dir"])


def folder_lastmod(path):
    """Mayor mtime entre los items directos de ``path`` (None si vacío/no existe)."""
    try:
        ts = [i["mtime"] for i in _propfind(path, 1) if i["mtime"] is not None]
        return max(ts) if ts else None
    except Exception:
        return None


def _safe_propfind(path):
    try:
        return _propfind(path, 1)
    except Exception:
        return []


def tree(path, max_depth=4):
    """Recorre recursivamente (Depth 1 en paralelo) y devuelve una lista plana de
    todos los items descendientes. Evita Depth:infinity, que puede estar deshabilitado
    en Nextcloud.

    El primer PROPFIND (la raíz) puede lanzar excepción (config/red) para permitir
    distinguir un fallo real de una carpeta vacía; los errores en niveles profundos
    se ignoran."""
    out = []
    items0 = _propfind(_norm(path), 1)  # propaga error de config/red

    def walk(parent_items, depth):
        subdirs = []
        for it in parent_items:
            out.append(it)
            if it["es_dir"]:
                subdirs.append(it["path"])
        if subdirs and depth < max_depth:
            with ThreadPoolExecutor(max_workers=6) as ex:
                children = list(ex.map(_safe_propfind, subdirs))
            for child_items in children:
                walk(child_items, depth + 1)

    walk(items0, 1)
    return out


def download(path):
    """Descarga un archivo (WebDAV GET). Devuelve ``(content_bytes, content_type)``.
    Lanza ``requests.HTTPError`` si no existe o falla."""
    resp = requests.get(_url(path), auth=_auth(), timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


def upload(path, contenido, content_type="application/octet-stream"):
    """Sube ``contenido`` (bytes) a ``path`` (WebDAV PUT). El padre debe existir.
    Devuelve el código HTTP (201 creado · 204 sobrescrito)."""
    resp = requests.put(_url(path), auth=_auth(), data=contenido,
                        headers={"Content-Type": content_type}, timeout=120)
    if resp.status_code in (201, 204):
        return resp.status_code
    resp.raise_for_status()
    return resp.status_code


def delete(path):
    """Elimina un archivo (WebDAV DELETE). Devuelve el código HTTP (204 ok · 404 no existía)."""
    resp = requests.request("DELETE", _url(path), auth=_auth(), timeout=60)
    if resp.status_code in (204, 200, 404):
        return resp.status_code
    resp.raise_for_status()
    return resp.status_code


# ── Escritura controlada (solo creación de carpetas) ─────────────────────────
def mkcol(path):
    """Crea una carpeta. Idempotente: ignora 405 (ya existe)."""
    resp = requests.request("MKCOL", _url(path), auth=_auth(), timeout=30)
    if resp.status_code in (201, 405):  # 201 creada · 405 ya existía
        return True
    resp.raise_for_status()
    return True


def ensure_tree(path):
    """Crea ``path`` y todas sus carpetas intermedias."""
    acc = ""
    for part in [p for p in path.strip("/").split("/") if p]:
        acc = f"{acc}/{part}"
        mkcol(acc)
