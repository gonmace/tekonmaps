# Generated manually - DocEmpresa: nombre, carpeta_nextcloud, orden (reemplaza codigo)

from django.db import migrations, models


def migrar_codigo_a_nombre_carpeta(apps, schema_editor):
    """Migra codigo a nombre y carpeta_nextcloud."""
    DocEmpresa = apps.get_model("docs", "DocEmpresa")
    for emp in DocEmpresa.objects.all():
        emp.nombre = emp.codigo
        emp.carpeta_nextcloud = emp.codigo
        emp.save()


def reverse_migrar(apps, schema_editor):
    """Revierte: codigo = nombre."""
    DocEmpresa = apps.get_model("docs", "DocEmpresa")
    for emp in DocEmpresa.objects.all():
        emp.codigo = emp.nombre
        emp.save()


class Migration(migrations.Migration):

    dependencies = [
        ("docs", "0006_delete_doccarpeta"),
    ]

    operations = [
        migrations.AddField(
            model_name="docempresa",
            name="nombre",
            field=models.CharField(help_text="Nombre de la empresa (ej: 20 AJ, 20 MER). Se usa como identificador.", max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="docempresa",
            name="carpeta_nextcloud",
            field=models.CharField(help_text="Nombre de la carpeta en Nextcloud (ej: 20 AJ). Path = /{carpeta_nextcloud}", max_length=255, null=True),
        ),
        migrations.RunPython(migrar_codigo_a_nombre_carpeta, reverse_migrar),
        migrations.RemoveField(
            model_name="docempresa",
            name="codigo",
        ),
        migrations.AlterField(
            model_name="docempresa",
            name="nombre",
            field=models.CharField(help_text="Nombre de la empresa (ej: 20 AJ, 20 MER). Se usa como identificador.", max_length=100, unique=True),
        ),
        migrations.AlterField(
            model_name="docempresa",
            name="carpeta_nextcloud",
            field=models.CharField(help_text="Nombre de la carpeta en Nextcloud (ej: 20 AJ). Path = /{carpeta_nextcloud}", max_length=255),
        ),
    ]
