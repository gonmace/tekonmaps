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
        return self.carpeta_nextcloud

    def root_path(self):
        return f"/{self.carpeta_nextcloud}"

    def link_para_rol(self, rol):
        if rol == "administrador" and self.link_admin:
            return self.link_admin
        return self.link_visitante


def _load_db_links():
    """Lee links admin/visitante desde EmpresaLink en la BD."""
    try:
        from .models import EmpresaLink
        return {e.nombre: (e.link_admin, e.link_visitante) for e in EmpresaLink.objects.all()}
    except Exception:
        return {}


def get_all():
    with open(CONFIG_PATH) as f:
        data = json.load(f)
    db_links = _load_db_links()
    companies = []
    for item in data:
        # Ignorar link_nextcloud del JSON (legacy), usar BD
        c = Company(
            nombre=item["nombre"],
            carpeta_nextcloud=item["carpeta_nextcloud"],
            orden=item.get("orden", 0),
        )
        if c.nombre in db_links:
            c.link_admin, c.link_visitante = db_links[c.nombre]
        companies.append(c)
    return sorted(companies, key=lambda c: (c.orden, c.nombre))


def get_first():
    companies = get_all()
    return companies[0] if companies else None


def get_by_nombre(nombre):
    for c in get_all():
        if c.nombre == nombre:
            return c
    return get_first()
