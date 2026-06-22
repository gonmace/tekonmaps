from django.db import migrations, models

ROLES = ["rol_buscador", "rol_tk_redline", "rol_constructor", "rol_ito",
         "rol_ito_hse", "rol_esp_electrico", "rol_coordinador"]

CHOICES = [('ELABORAR', 'Elaborar'), ('REVISAR', 'Revisar'),
           ('FIRMAR', 'Firmar'), ('PRESENTAR', 'Presentar')]


def verificar_a_revisar(apps, schema_editor):
    """Las acciones válidas pasan a ser solo ELABORAR/REVISAR/FIRMAR/PRESENTAR.
    VERIFICAR se consolida en REVISAR; CONSOLIDAR se deja vacío (sin acción)."""
    DocumentoEsperado = apps.get_model("docs", "DocumentoEsperado")
    for campo in ROLES:
        DocumentoEsperado.objects.filter(**{campo: "VERIFICAR"}).update(**{campo: "REVISAR"})
        DocumentoEsperado.objects.filter(**{campo: "CONSOLIDAR"}).update(**{campo: ""})


class Migration(migrations.Migration):

    dependencies = [
        ('docs', '0028_alter_userprofile_rol_ito'),
    ]

    operations = [
        migrations.RunPython(verificar_a_revisar, migrations.RunPython.noop),
        migrations.AlterField(model_name='documentoesperado', name='rol_buscador',
                              field=models.CharField(blank=True, choices=CHOICES, max_length=12)),
        migrations.AlterField(model_name='documentoesperado', name='rol_tk_redline',
                              field=models.CharField(blank=True, choices=CHOICES, max_length=12)),
        migrations.AlterField(model_name='documentoesperado', name='rol_constructor',
                              field=models.CharField(blank=True, choices=CHOICES, max_length=12)),
        migrations.AlterField(model_name='documentoesperado', name='rol_ito',
                              field=models.CharField(blank=True, choices=CHOICES, max_length=12)),
        migrations.AlterField(model_name='documentoesperado', name='rol_ito_hse',
                              field=models.CharField(blank=True, choices=CHOICES, max_length=12)),
        migrations.AlterField(model_name='documentoesperado', name='rol_esp_electrico',
                              field=models.CharField(blank=True, choices=CHOICES, max_length=12)),
        migrations.AlterField(model_name='documentoesperado', name='rol_coordinador',
                              field=models.CharField(blank=True, choices=CHOICES, max_length=12)),
    ]
