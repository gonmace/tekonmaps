# Generated manually - DocEmpresa model and DocCarpeta FK to DocEmpresa

from django.db import migrations, models
import django.db.models.deletion


def crear_empresas_iniciales(apps, schema_editor):
    DocEmpresa = apps.get_model("docs", "DocEmpresa")
    for codigo, nombre in [("AJ", "20 AJ"), ("MER", "20 MER"), ("GH", "20 GH")]:
        DocEmpresa.objects.get_or_create(codigo=codigo, defaults={"nombre_display": nombre, "prefijo_path": "20"})


def migrar_carpetas_empresa(apps, schema_editor):
    DocCarpeta = apps.get_model("docs", "DocCarpeta")
    DocEmpresa = apps.get_model("docs", "DocEmpresa")
    for carpeta in DocCarpeta.objects.all():
        try:
            emp = DocEmpresa.objects.get(codigo=carpeta.empresa_old)
            carpeta.empresa = emp
            carpeta.save()
        except DocEmpresa.DoesNotExist:
            pass


def reverse_migrar(apps, schema_editor):
    DocCarpeta = apps.get_model("docs", "DocCarpeta")
    for carpeta in DocCarpeta.objects.select_related("empresa"):
        carpeta.empresa_old = carpeta.empresa.codigo if carpeta.empresa else "AJ"
        carpeta.save()


class Migration(migrations.Migration):

    dependencies = [
        ("docs", "0001_add_doccarpeta"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocEmpresa",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codigo", models.CharField(help_text="Código de la empresa (ej: AJ, MER). Se usa en la URL.", max_length=20, unique=True)),
                ("nombre_display", models.CharField(help_text="Nombre a mostrar (ej: 20 AJ, 20 MER)", max_length=100)),
                ("prefijo_path", models.CharField(default="20", help_text="Prefijo del path en Nextcloud. Path = /{prefijo} {codigo}", max_length=50)),
                ("orden", models.PositiveIntegerField(default=0)),
            ],
            options={
                "verbose_name": "Empresa",
                "verbose_name_plural": "Empresas",
                "ordering": ["orden", "codigo"],
            },
        ),
        migrations.RunPython(crear_empresas_iniciales, migrations.RunPython.noop),
        migrations.RenameField(model_name="doccarpeta", old_name="empresa", new_name="empresa_old"),
        migrations.AddField(
            model_name="doccarpeta",
            name="empresa",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name="carpetas", to="docs.docempresa"),
        ),
        migrations.RunPython(migrar_carpetas_empresa, reverse_migrar),
        migrations.RemoveField(model_name="doccarpeta", name="empresa_old"),
        migrations.AlterField(
            model_name="doccarpeta",
            name="empresa",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="carpetas", to="docs.docempresa"),
        ),
    ]
