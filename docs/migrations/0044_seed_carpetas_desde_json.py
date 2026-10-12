"""Siembra CarpetaRaiz desde companies.json (las empresas existentes pasan a la BD
como carpetas escaneadas y de contratista) y copia los links de EmpresaLink."""
import json
from pathlib import Path

from django.db import migrations

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "companies.json"


def sembrar(apps, schema_editor):
    CarpetaRaiz = apps.get_model("docs", "CarpetaRaiz")
    EmpresaLink = apps.get_model("docs", "EmpresaLink")
    if not CONFIG_PATH.exists():
        return
    with open(CONFIG_PATH) as f:
        data = json.load(f)
    links = {e.nombre: (e.link_admin, e.link_visitante) for e in EmpresaLink.objects.all()}
    for item in data:
        codigo = item.get("nombre", "")
        link_admin, link_visitante = links.get(codigo, ("", ""))
        CarpetaRaiz.objects.get_or_create(
            carpeta=item["carpeta_nextcloud"],
            defaults={
                "codigo": codigo,
                "orden": item.get("orden", 0),
                "escanear": True,
                "es_contratista": True,
                "link_admin": link_admin,
                "link_visitante": link_visitante,
            },
        )


def revertir(apps, schema_editor):
    CarpetaRaiz = apps.get_model("docs", "CarpetaRaiz")
    if not CONFIG_PATH.exists():
        return
    with open(CONFIG_PATH) as f:
        data = json.load(f)
    CarpetaRaiz.objects.filter(
        carpeta__in=[item["carpeta_nextcloud"] for item in data]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("docs", "0043_carpetaraiz_nextcloudconfig_copiarenombrada"),
    ]

    operations = [
        migrations.RunPython(sembrar, revertir),
    ]
