# Generated manually - Remove nombre_display from DocCarpeta (se usa nombre_carpeta y empresa)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("docs", "0003_remove_docempresa_nombre_display"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="doccarpeta",
            name="nombre_display",
        ),
    ]
