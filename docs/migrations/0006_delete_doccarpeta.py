# Generated manually - Remove DocCarpeta model (solo existe DocEmpresa)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("docs", "0005_remove_docempresa_prefijo_path"),
    ]

    operations = [
        migrations.DeleteModel(
            name="DocCarpeta",
        ),
    ]
