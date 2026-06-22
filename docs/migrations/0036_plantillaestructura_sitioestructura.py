from django.db import migrations, models
import django.db.models.deletion


def crear_default(apps, schema_editor):
    """Crea la plantilla default 'Estructura base' y le asigna todos los
    DocumentoEsperado existentes (la lista global actual)."""
    Plantilla = apps.get_model('docs', 'PlantillaEstructura')
    Documento = apps.get_model('docs', 'DocumentoEsperado')
    default = Plantilla.objects.filter(es_default=True).first()
    if default is None:
        default = Plantilla.objects.create(nombre='Estructura base', es_default=True)
    Documento.objects.filter(plantilla__isnull=True).update(plantilla=default)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('docs', '0035_delete_archivoito'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlantillaEstructura',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=120, unique=True)),
                ('descripcion', models.CharField(blank=True, max_length=255)),
                ('es_default', models.BooleanField(default=False, help_text='Plantilla usada por los sitios sin asignación explícita. Solo una.')),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('actualizado', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Plantilla de estructura',
                'verbose_name_plural': 'Plantillas de estructura',
                'ordering': ['-es_default', 'nombre'],
            },
        ),
        migrations.AddField(
            model_name='documentoesperado',
            name='plantilla',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='documentos', to='docs.plantillaestructura'),
        ),
        migrations.RunPython(crear_default, noop),
        migrations.AlterField(
            model_name='documentoesperado',
            name='plantilla',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documentos', to='docs.plantillaestructura'),
        ),
        migrations.AlterUniqueTogether(
            name='documentoesperado',
            unique_together={('plantilla', 'etapa', 'nombre')},
        ),
        migrations.CreateModel(
            name='SitioEstructura',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('empresa', models.CharField(max_length=100)),
                ('sitio', models.CharField(max_length=200)),
                ('plantilla', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sitios', to='docs.plantillaestructura')),
            ],
            options={
                'verbose_name': 'Estructura por sitio',
                'verbose_name_plural': 'Estructuras por sitio',
                'ordering': ['empresa', 'sitio'],
                'unique_together': {('empresa', 'sitio')},
            },
        ),
    ]
