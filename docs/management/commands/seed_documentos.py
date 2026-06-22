"""Carga/actualiza los documentos esperados del ITO desde el fixture JSON
(exportado una vez de ESTRUCTURA DOCUMENTOS.xlsx)."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand

from docs.models import DocumentoEsperado, PlantillaEstructura

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "documentos_ito.json"


class Command(BaseCommand):
    help = "Carga los documentos esperados del ITO desde fixtures/documentos_ito.json."

    ROLES = ["rol_buscador", "rol_tk_redline", "rol_constructor",
             "rol_ito", "rol_ito_hse", "rol_esp_electrico", "rol_coordinador"]

    def handle(self, *args, **options):
        # La lista maestra del xlsx siempre puebla la plantilla default.
        plantilla = PlantillaEstructura.get_default()
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        creados = actualizados = 0
        claves = set()
        for row in data:
            claves.add((row["etapa"], row["nombre"]))
            defaults = {
                "carpeta": row.get("carpeta", ""),
                "codigo": row.get("codigo", ""),
                "tipo_esperado": row.get("tipo_esperado", ""),
                "obligatorio": row.get("obligatorio", True),
                "orden": row.get("orden", 0),
                "activo": row.get("activo", True),
            }
            for r in self.ROLES:
                defaults[r] = row.get(r, "")
            _, created = DocumentoEsperado.objects.update_or_create(
                plantilla=plantilla,
                etapa=row["etapa"],
                nombre=row["nombre"],
                defaults=defaults,
            )
            if created:
                creados += 1
            else:
                actualizados += 1

        # Poda: borra documentos (de la default) que ya no están en el fixture.
        borrados = 0
        for d in DocumentoEsperado.objects.filter(plantilla=plantilla):
            if (d.etapa, d.nombre) not in claves:
                d.delete()
                borrados += 1

        self.stdout.write(self.style.SUCCESS(
            f"Documentos ITO: {creados} creados, {actualizados} actualizados, "
            f"{borrados} borrados ({len(data)} en el fixture)."
        ))
