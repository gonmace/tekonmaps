from django.db import migrations

ROLES = ["rol_buscador", "rol_tk_redline", "rol_constructor", "rol_ito",
         "rol_ito_hse", "rol_esp_electrico", "rol_coordinador"]


def firma_a_firmar(apps, schema_editor):
    DocumentoEsperado = apps.get_model("docs", "DocumentoEsperado")
    for campo in ROLES:
        DocumentoEsperado.objects.filter(**{campo: "FIRMA"}).update(**{campo: "FIRMAR"})


class Migration(migrations.Migration):

    dependencies = [
        ('docs', '0026_alter_documentoesperado_rol_buscador_and_more'),
    ]

    operations = [
        migrations.RunPython(firma_a_firmar, migrations.RunPython.noop),
    ]
