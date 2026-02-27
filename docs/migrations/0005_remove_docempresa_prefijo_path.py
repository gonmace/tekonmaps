# Generated manually - Remove prefijo_path from DocEmpresa (path = /{codigo})

from django.db import migrations, models


def actualizar_codigo_path(apps, schema_editor):
    """Actualiza codigo para incluir el path completo (20 AJ, 20 MER, etc.)."""
    DocEmpresa = apps.get_model("docs", "DocEmpresa")
    mapeo = {"AJ": "20 AJ", "MER": "20 MER", "GH": "20 GH"}
    for emp in DocEmpresa.objects.all():
        nuevo = mapeo.get(emp.codigo, emp.codigo)
        if nuevo != emp.codigo:
            emp.codigo = nuevo
            emp.save()


def reverse_actualizar(apps, schema_editor):
    """Revierte codigo a solo el sufijo (AJ, MER, GH)."""
    DocEmpresa = apps.get_model("docs", "DocEmpresa")
    mapeo = {"20 AJ": "AJ", "20 MER": "MER", "20 GH": "GH"}
    for emp in DocEmpresa.objects.all():
        nuevo = mapeo.get(emp.codigo, emp.codigo.split()[-1] if emp.codigo else emp.codigo)
        if nuevo:
            emp.codigo = nuevo
            emp.save()


class Migration(migrations.Migration):

    dependencies = [
        ("docs", "0004_remove_doccarpeta_nombre_display"),
    ]

    operations = [
        migrations.AlterField(
            model_name="docempresa",
            name="codigo",
            field=models.CharField(help_text="Código/nombre de la empresa (ej: 20 AJ, 20 MER). Se usa como path en Nextcloud.", max_length=100, unique=True),
        ),
        migrations.RunPython(actualizar_codigo_path, reverse_actualizar),
        migrations.RemoveField(
            model_name="docempresa",
            name="prefijo_path",
        ),
    ]
