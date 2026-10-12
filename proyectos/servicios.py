"""Lógica de negocio del seguimiento de proyectos (sin HTTP)."""
import re
import time
import unicodedata

from django.db import transaction

from docs import nextcloud, seguimiento
from docs.models import AccesoSitio

from .models import (CARPETA_ETAPA, ETAPAS, ESTADO_ETAPA, ESTADO_PROYECTO, Actividad, Etapa,
                     Proyecto)

EXT_IMAGEN = {"jpg", "jpeg", "png", "gif", "webp", "heic"}
MAX_IMAGEN = 15 * 1024 * 1024
_ESTADOS_ETAPA = {c for c, _ in ESTADO_ETAPA}
_ESTADOS_PROYECTO = {c for c, _ in ESTADO_PROYECTO}


class ReglaEtapa(ValueError):
    """Cambio de estado no permitido (mensaje apto para mostrar al usuario)."""


# Palabras que identifican la carpeta de cada etapa dentro de la carpeta del sitio
# (el nombre real varía: «01 INGENIERIA», «1-INGENIERIA», «Ingeniería de detalle»…).
PALABRAS_ETAPA = {
    "ING": ("INGENIERIA",),
    "CON": ("CONSTRUCCION",),
    "CIE": ("CIERRE", "DOCUMENTACION"),
}


def _sin_acentos(txt):
    return "".join(c for c in unicodedata.normalize("NFKD", txt) if not unicodedata.combining(c)).upper()


_PALABRA_ING = re.compile(r"(?<![A-Z0-9])ING(?![A-Z0-9])")   # «00 ING», «ING-DETALLE»


def carpetas_de_etapa(nombres, etapa):
    """Nombres (de ``nombres``) que corresponden a la etapa: contienen su palabra clave,
    sin importar mayúsculas, acentos ni prefijo numérico."""
    claves = PALABRAS_ETAPA.get(etapa, ())
    out = []
    for n in nombres:
        norm = _sin_acentos(n)
        if not (any(k in norm for k in claves)
                or (etapa == "ING" and _PALABRA_ING.search(norm))):
            continue
        # «DOCUMENTACION» solo cuenta para Cierre si no es de otra etapa.
        if etapa == "CIE" and "CIERRE" not in norm and \
                any(k in norm for o in ("ING", "CON") for k in PALABRAS_ETAPA[o]):
            continue
        out.append(n)
    return sorted(out)


# Carpetas que contienen fotos: «FOTOGRAFIAS», «1 FOTOS», «Imágenes», «REG FOTOGRAFICOS»…
_CLAVES_FOTOS = ("FOTO", "IMAGEN", "IMG", "PHOTO", "PICTURE", "REGISTRO", "REG ")
EXT_IMG_VISTA = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "heic", "tif", "tiff"}


def es_carpeta_fotos(nombre):
    norm = _sin_acentos(nombre) + " "
    return any(k in norm for k in _CLAVES_FOTOS)


def es_imagen(nombre):
    return nombre.rsplit(".", 1)[-1].lower() in EXT_IMG_VISTA if "." in nombre else False


def imagenes_de_carpetas_fotos(items, base):
    """De los ``items`` de una etapa (rutas absolutas bajo ``base``) devuelve los archivos
    de imagen que viven dentro de alguna carpeta de fotos."""
    prefijo = base.rstrip("/") + "/"
    out = []
    for it in items:
        if it["es_dir"] or not es_imagen(it["nombre"]) or not it["path"].startswith(prefijo):
            continue
        rel = it["path"][len(prefijo):].split("/")
        # Segmentos intermedios (sin el nombre de archivo ni la carpeta raíz de la etapa).
        if any(es_carpeta_fotos(seg) for seg in rel[1:-1]):
            out.append(it)
    return out


# Roles que se pueden asignar como ITO (Inspector Técnico) de un sitio. Coordinador y
# TK Redline ven todos los sitios sin asignación.
ROLES_ITO = ("rol_ito", "rol_ito_hse")


def nombre_usuario(u):
    return (u.get_full_name() or u.first_name or u.username).strip()


def responsable_nombre(p):
    """Nombre a mostrar del responsable de un pendiente (usuario o texto libre)."""
    if p.responsable_user_id and p.responsable_user:
        return nombre_usuario(p.responsable_user)
    return p.responsable


def registrar(proyecto, tipo, detalle="", usuario=None, etapa=None):
    """Anota una entrada en la actividad del proyecto (nunca interrumpe la operación)."""
    try:
        Actividad.objects.create(proyecto=proyecto, tipo=tipo, detalle=(detalle or "")[:300],
                                 usuario=usuario if getattr(usuario, "pk", None) else None,
                                 etapa=etapa)
    except Exception:
        pass


def responsables_posibles(empresa, sitio):
    """Usuarios que se pueden elegir como responsable de un pendiente del sitio: los ITO
    asignados más los roles que ven todos los sitios (Coordinador, TK Redline)."""
    from django.contrib.auth.models import User
    from django.db.models import Q
    from docs.models import ROLES_TODO_SITIO
    asignados = AccesoSitio.objects.filter(empresa=empresa, sitio=sitio).values_list("user_id", flat=True)
    return (User.objects.filter(is_active=True, is_superuser=False)
            .filter(Q(pk__in=asignados) | Q(profile__rol__in=ROLES_TODO_SITIO))
            .order_by("first_name", "username").distinct())


def itos_asignados(empresa, sitio):
    """Usuarios activos con acceso asignado (``AccesoSitio``) al sitio."""
    from django.contrib.auth.models import User
    ids = AccesoSitio.objects.filter(empresa=empresa, sitio=sitio).values_list("user_id", flat=True)
    return User.objects.filter(pk__in=ids, is_active=True).order_by("first_name", "username")


def candidatos_ito():
    """Usuarios activos con rol ITO / ITO HSE (asignables a un sitio)."""
    from django.contrib.auth.models import User
    return (User.objects.filter(is_active=True, is_superuser=False, profile__rol__in=ROLES_ITO)
            .order_by("first_name", "username"))


def asignar_itos(empresa, sitio, ids):
    """Deja asignados al sitio exactamente los ITO de ``ids`` (entre los candidatos). No toca
    las asignaciones de usuarios con otros roles."""
    candidatos = {u.pk for u in candidatos_ito()}
    quiere = {int(i) for i in ids if int(i) in candidatos}
    actuales = set(AccesoSitio.objects.filter(empresa=empresa, sitio=sitio, user_id__in=candidatos)
                   .values_list("user_id", flat=True))
    for uid in quiere - actuales:
        AccesoSitio.objects.get_or_create(user_id=uid, empresa=empresa, sitio=sitio)
    AccesoSitio.objects.filter(empresa=empresa, sitio=sitio,
                               user_id__in=actuales - quiere).delete()
    return quiere


def obtener_proyecto(empresa, sitio):
    """Devuelve el proyecto del sitio, creándolo junto con sus etapas si no existe."""
    with transaction.atomic():
        proyecto, _ = Proyecto.objects.get_or_create(empresa=empresa, sitio=sitio)
        for codigo, _lbl in ETAPAS:
            Etapa.objects.get_or_create(proyecto=proyecto, etapa=codigo)
    return proyecto


def cambiar_estado_proyecto(proyecto, estado, user):
    if estado not in _ESTADOS_PROYECTO:
        raise ReglaEtapa("Estado inválido.")
    proyecto.estado = estado
    proyecto.actualizado_por = user
    proyecto.save()


def fijar_ubicacion(proyecto, lat, lon, user):
    """Guarda la ubicación del proyecto. ``lat``/``lon`` ``None`` la borra."""
    if lat is None and lon is None:
        proyecto.lat = proyecto.lon = None
    else:
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            raise ReglaEtapa("Coordenadas inválidas.")
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ReglaEtapa("Coordenadas fuera de rango.")
        proyecto.lat, proyecto.lon = round(lat, 6), round(lon, 6)
    proyecto.actualizado_por = user
    proyecto.save()


def cambiar_estado_etapa(etapa, estado, user):
    """Cambia el estado de una etapa. Regla: Ingeniería no puede estar «En curso» a la
    vez que Construcción."""
    if estado not in _ESTADOS_ETAPA:
        raise ReglaEtapa("Estado inválido.")
    if estado == "CUR":
        otras = (Etapa.objects.filter(proyecto=etapa.proyecto, estado="CUR",
                                      etapa__in=[c for c, _ in ETAPAS]).exclude(pk=etapa.pk))
        if etapa.etapa == "ING" and otras.exists():
            raise ReglaEtapa("Ingeniería no puede estar en curso mientras "
                             "Construcción esté en curso.")
        if etapa.etapa != "ING" and otras.filter(etapa="ING").exists():
            raise ReglaEtapa("Construcción no puede estar en curso mientras "
                             "Ingeniería esté en curso.")
    etapa.estado = estado
    etapa.actualizado_por = user
    etapa.save()


def _nombre_seguro(nombre):
    base = seguimiento._sanitize_archivo(nombre)
    return re.sub(r"[^\w.\- ()]", "_", base)


def subir_imagen(proyecto, etapa, contenido, filename, content_type=None):
    """Sube la imagen a ``<sitio>/06_PROYECTO/<Etapa>/`` en Nextcloud. Devuelve la ruta."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in EXT_IMAGEN:
        raise ValueError("Solo se permiten imágenes (jpg, png, gif, webp, heic).")
    if len(contenido) > MAX_IMAGEN:
        raise ValueError("La imagen supera los 15 MB.")
    base = f"{seguimiento.ito_path(proyecto.sitio)}/06_PROYECTO/{CARPETA_ETAPA[etapa.etapa]}"
    nextcloud.ensure_tree(base)
    destino = f"{base}/{int(time.time())}_{_nombre_seguro(filename)}"
    nextcloud.upload(destino, contenido, content_type or "application/octet-stream")
    return destino
