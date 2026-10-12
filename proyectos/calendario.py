"""Sincroniza los pendientes con fecha al calendario de Nextcloud (CalDAV).

Un pendiente con fecha = un evento en el calendario configurado (de **día completo**, o
de 1 hora a la hora indicada si el pendiente la tiene)
(``NEXTCLOUD_CALENDAR``: nombre visible o identificador; por defecto «Seguimiento»).
El UID del evento se deriva de la clave del pendiente, así que crear/actualizar es un
PUT idempotente y borrar es un DELETE. Todas las funciones lanzan excepción si
Nextcloud falla: quien llama decide si eso interrumpe o solo avisa.
"""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, unquote, urlsplit

import requests
from django.conf import settings
from django.core.cache import cache

from docs import nextcloud

TIMEOUT = 15
DURACION = timedelta(hours=1)   # eventos con hora
_NS_PROPFIND = (
    '<?xml version="1.0"?><d:propfind xmlns:d="DAV:" '
    'xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:displayname/>'
    '<d:resourcetype/><c:supported-calendar-component-set/></d:prop></d:propfind>'
)


class CalendarioNoDisponible(RuntimeError):
    """No hay calendario configurado o no se encontró en Nextcloud."""


def habilitado():
    return bool(getattr(settings, "NEXTCLOUD_CALENDAR", "").strip()) and nextcloud.is_configured()


def _dav():
    """``(raíz del servidor, usuario DAV)`` a partir de la URL base de archivos."""
    u = urlsplit(nextcloud._base_url())
    corte = u.path.find("/remote.php")
    raiz = f"{u.scheme}://{u.netloc}{u.path[:corte] if corte >= 0 else ''}"
    return raiz, u.path.rstrip("/").split("/")[-1]


def _buscar_calendario(nombre):
    """URL absoluta de la colección CalDAV cuyo nombre visible (o id) es ``nombre``."""
    raiz, usuario = _dav()
    home = f"{raiz}/remote.php/dav/calendars/{usuario}/"
    r = requests.request("PROPFIND", home, data=_NS_PROPFIND, auth=nextcloud._auth(),
                         headers={"Depth": "1", "Content-Type": "application/xml"},
                         timeout=TIMEOUT)
    r.raise_for_status()
    candidatos = []
    for blk in re.findall(r"<d:response>.*?</d:response>", r.text, re.S):
        href = re.search(r"<d:href>(.*?)</d:href>", blk)
        if not href or "calendar" not in blk.split("resourcetype", 1)[-1]:
            continue
        if "VEVENT" not in blk:
            continue
        dn = re.search(r"<d:displayname>(.*?)</d:displayname>", blk)
        candidatos.append((unquote(href.group(1)), (dn.group(1) if dn else "").strip()))
    obj = nombre.strip().lower()
    for prefijo in (lambda h, d: d.lower() == obj or h.rstrip("/").split("/")[-1].lower() == obj,
                    lambda h, d: d.lower().startswith(obj)):
        for href, disp in candidatos:
            if prefijo(href, disp):
                return f"{raiz}{href}".rstrip("/")
    raise CalendarioNoDisponible(f"No se encontró el calendario «{nombre}» en Nextcloud.")


def _url_calendario():
    nombre = settings.NEXTCLOUD_CALENDAR.strip()
    if not nombre:
        raise CalendarioNoDisponible("Calendario no configurado.")
    key = "proy:caldav:" + nombre.lower()
    url = cache.get(key)
    if not url:
        url = _buscar_calendario(nombre)
        cache.set(key, url, 3600)
    return url


# ── ICS ──────────────────────────────────────────────────────────────────────
def _esc(txt):
    return (str(txt).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\n").replace("\n", "\\n"))


def _fold(linea):
    """Pliega a 75 octetos (RFC 5545), sin cortar caracteres multibyte."""
    out, cur = [], ""
    for ch in linea:
        if len((cur + ch).encode("utf-8")) > (75 if not out else 74):
            out.append(cur)
            cur = ch
        else:
            cur += ch
    out.append(cur)
    return "\r\n ".join(out)


def uid(pendiente):
    return f"pendiente-{pendiente.pk}@pti.tekon-rl.cl"


def construir_ics(pendiente, ahora=None):
    etapa = pendiente.etapa
    proyecto = etapa.proyecto
    ahora = ahora or datetime.now(timezone.utc)
    ini = pendiente.fecha
    if pendiente.hora:
        # Hora «flotante» (sin zona): se ve la misma hora en cualquier calendario. Dura
        # 1 hora (puede cruzar la medianoche).
        desde = datetime.combine(ini, pendiente.hora)
        hasta = desde + DURACION
        fechas = [f"DTSTART:{desde.strftime('%Y%m%dT%H%M%S')}",
                  f"DTEND:{hasta.strftime('%Y%m%dT%H%M%S')}"]
    else:
        fin = ini + timedelta(days=1)
        fechas = [f"DTSTART;VALUE=DATE:{ini.strftime('%Y%m%d')}",
                  f"DTEND;VALUE=DATE:{fin.strftime('%Y%m%d')}"]
    titulo = f"{'✓ ' if pendiente.hecho else ''}{pendiente.titulo} · {etapa.get_etapa_display()}"
    desc = [f"Sitio: {proyecto.sitio}", f"Empresa: {proyecto.empresa}",
            f"Etapa: {etapa.get_etapa_display()}"]
    if pendiente.responsable:
        desc.append(f"Responsable: {pendiente.responsable}")
    if pendiente.hecho:
        desc.append("Estado: hecho")
    lineas = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Tk Redline//Seguimiento//ES",
        "CALSCALE:GREGORIAN", "BEGIN:VEVENT",
        f"UID:{uid(pendiente)}",
        f"DTSTAMP:{ahora.strftime('%Y%m%dT%H%M%SZ')}",
        *fechas,
        f"SUMMARY:{_esc(titulo)}",
        f"DESCRIPTION:{_esc(chr(10).join(desc))}",
        f"LOCATION:{_esc(proyecto.sitio)}",
        "STATUS:CONFIRMED",
        "TRANSP:TRANSPARENT",
        "END:VEVENT", "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(l) for l in lineas) + "\r\n"


def _url_evento(pendiente):
    return f"{_url_calendario()}/pendiente-{pendiente.pk}.ics"


# ── Operaciones ──────────────────────────────────────────────────────────────
def guardar_evento(pendiente):
    """Crea o actualiza el evento del pendiente (requiere ``fecha``)."""
    r = requests.put(_url_evento(pendiente), data=construir_ics(pendiente).encode("utf-8"),
                     auth=nextcloud._auth(), timeout=TIMEOUT,
                     headers={"Content-Type": "text/calendar; charset=utf-8"})
    if r.status_code not in (201, 204):
        r.raise_for_status()


def borrar_evento(pendiente):
    r = requests.delete(_url_evento(pendiente), auth=nextcloud._auth(), timeout=TIMEOUT)
    if r.status_code not in (200, 204, 404):
        r.raise_for_status()


def sincronizar(pendiente):
    """Deja el calendario acorde al pendiente. Devuelve ``True`` si hay evento tras la
    llamada. Sin fecha → no hay evento (se borra el anterior si existía)."""
    if not habilitado():
        return False
    if pendiente.fecha:
        guardar_evento(pendiente)
        return True
    if pendiente.en_calendario:
        borrar_evento(pendiente)
    return False
