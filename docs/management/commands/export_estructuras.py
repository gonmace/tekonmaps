"""Exporta la estructura del ITO (plantilla default) de la BD al fixture JSON.

Inverso de ``seed_documentos``: vuelca los documentos esperados de la plantilla
default a ``fixtures/documentos_ito.json`` en el mismo formato que ``seed`` lee.
Úsalo tras editar la estructura en el Panel para versionar el cambio en git:

    python manage.py export_estructuras

Después: ``git add docs/fixtures/documentos_ito.json && git commit``. En el deploy,
``seed_documentos`` (en el entrypoint) reconstruye la BD del VPS desde este JSON.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand

from docs.models import DocumentoEsperado, PlantillaEstructura

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "documentos_ito.json"

# Roles tal cual los nombra el modelo (evita divergencia con seed/el modelo).
ROLES = [campo for campo, _, _ in DocumentoEsperado.ROLES]


class Command(BaseCommand):
    help = "Exporta los documentos esperados del ITO (plantilla default) a fixtures/documentos_ito.json."

    def handle(self, *args, **options):
        plantilla = PlantillaEstructura.get_default()
        rows = []
        for d in DocumentoEsperado.objects.filter(plantilla=plantilla).order_by("orden", "id"):
            row = {
                "etapa": d.etapa,
                "carpeta": d.carpeta,
                "nombre": d.nombre,
                "codigo": d.codigo,
                "tipo_esperado": d.tipo_esperado,
                "obligatorio": d.obligatorio,
                "orden": d.orden,
                "activo": d.activo,
            }
            for r in ROLES:
                row[r] = getattr(d, r)
            rows.append(row)

        FIXTURE.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self.stdout.write(self.style.SUCCESS(
            f"Estructura exportada: {len(rows)} documentos → {FIXTURE.name}"
        ))
