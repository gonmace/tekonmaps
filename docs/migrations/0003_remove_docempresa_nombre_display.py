# Generated manually - Remove nombre_display from DocEmpresa (derived from prefijo_path + codigo)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("docs", "0002_docempresa_and_alter_doccarpeta"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="docempresa",
            name="nombre_display",
        ),
    ]
