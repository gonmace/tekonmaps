"""Empresas (carpetas de contratista) del sistema.

Fuente: el modelo :class:`docs.models.CarpetaRaiz` (carpetas con ``es_contratista=True``
y ``escanear=True``, administradas en el Panel → Nextcloud). ``companies.json`` queda
solo como semilla de la migración 0044 y como fallback si la BD aún no está migrada.
"""
import json
from pathlib import Path
from dataclasses import dataclass

CONFIG_PATH = Path(__file__).resolve().parent.parent / "companies.json"


@dataclass
class Company:
    nombre: str
    carpeta_nextcloud: str
    link_nextcloud: str = ""
    orden: int = 0
    link_admin: str = ""
    link_visitante: str = ""

    @property
    def nombre_display(self):
        # Código limpio (ej. "AJ"); la nomenclatura cruda ("20 AJ") se ve en el Panel.
        return self.nombre

    def root_path(self):
        return f"/{self.carpeta_nextcloud}"

    def link_para_rol(self, rol):
        if rol != "visitante" and self.link_admin:
            return self.link_admin
        return self.link_visitante


def _get_all_desde_json():
    """Fallback legacy: lee companies.json (solo si la BD no está migrada)."""
    try:
        with open(CONFIG_PATH) as f:
            data = json.load(f)
    except OSError:
        return []
    return [Company(nombre=item["nombre"],
                    carpeta_nextcloud=item["carpeta_nextcloud"],
                    orden=item.get("orden", 0))
            for item in data]


def get_all():
    try:
        from .models import CarpetaRaiz
        filas = list(CarpetaRaiz.objects.filter(es_contratista=True, escanear=True))
    except Exception:
        return sorted(_get_all_desde_json(), key=lambda c: (c.orden, c.nombre))
    companies = [Company(
        nombre=f.codigo or f.carpeta,
        carpeta_nextcloud=f.carpeta,
        orden=f.orden,
        link_admin=f.link_admin,
        link_visitante=f.link_visitante,
    ) for f in filas]
    return sorted(companies, key=lambda c: (c.orden, c.nombre))


def get_first():
    companies = get_all()
    return companies[0] if companies else None


def get_by_nombre(nombre):
    for c in get_all():
        if c.nombre == nombre:
            return c
    return get_first()
