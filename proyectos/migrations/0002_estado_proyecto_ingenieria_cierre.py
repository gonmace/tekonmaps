from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('proyectos', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='proyecto',
            name='estado',
            field=models.CharField(choices=[('ASG', 'Asignado'), ('ING', 'Ingeniería'), ('EJE', 'Ejecución'), ('CIE', 'Cierre'), ('TER', 'Terminado'), ('PTG', 'Postergado'), ('CAN', 'Cancelado')], default='ASG', max_length=3),
        ),
    ]
