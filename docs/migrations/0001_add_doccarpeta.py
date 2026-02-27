# Generated manually for DocCarpeta model

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="DocCarpeta",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("empresa", models.CharField(choices=[("AJ", "20 AJ"), ("MER", "20 MER"), ("GH", "20 GH")], max_length=10)),
                ("nombre_carpeta", models.CharField(help_text="Nombre de la carpeta en Nextcloud (ruta)", max_length=255)),
                ("nombre_display", models.CharField(help_text="Nombre a mostrar en la interfaz", max_length=255)),
                ("orden", models.PositiveIntegerField(default=0)),
            ],
            options={
                "verbose_name": "Carpeta de documentación",
                "verbose_name_plural": "Carpetas de documentación",
                "ordering": ["empresa", "orden", "nombre_carpeta"],
            },
        ),
    ]
