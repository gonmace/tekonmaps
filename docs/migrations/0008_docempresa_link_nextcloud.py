# Generated manually - Add link_nextcloud to DocEmpresa

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("docs", "0007_docempresa_nombre_carpeta_nextcloud"),
    ]

    operations = [
        migrations.AddField(
            model_name="docempresa",
            name="link_nextcloud",
            field=models.URLField(blank=True, help_text="Enlace directo a la carpeta en Nextcloud (opcional).", max_length=500),
        ),
    ]
