from django.db import models

ALTURA_CHOICES = [
    (24, '24'),
    (42, '42'),
    (48, '48'),
]

CONTRATISTA_CHOICES = [
    ('MER', 'MER'),
    ('AJ', 'AJ'),
]

class Sitio(models.Model):
    sitio = models.CharField("Codigo Sitio", max_length=10,  null=True)
    entel_id = models.CharField(max_length=10)
    nombre = models.CharField(max_length=100, blank=True)
    altura = models.IntegerField("Altura", choices=ALTURA_CHOICES, default=42)
    contratista = models.CharField("Contratista", max_length=120, choices=CONTRATISTA_CHOICES, default='MER')
    lat = models.FloatField("Latitud", max_length=11, blank=True, null=True)
    lon = models.FloatField("Longitud", max_length=11, blank=True, null=True)
    ito = models.CharField("ITO", max_length=12)
             
    class Meta:
        verbose_name = "Proyecto"
        verbose_name_plural = "Proyectos"
    
    def __str__(self):
        return f"{self.sitio}"

ESTADO_CHOICES = [
    ('ASG', 'Asignado',),
    ('EJE', 'Ejecución'),
    ('TER', 'Terminado'),
    ('PTG', 'Postergado'),
    ('CAN', 'Cancelado'),
]

class Avance(models.Model):
    sitio = models.OneToOneField(Sitio, on_delete=models.CASCADE)
    estado = models.CharField("Estado", max_length=10, choices=ESTADO_CHOICES, default='EJE')
    excavacion = models.DateField("Exc.", null=True, blank=True)
    hormigonado = models.DateField("Hor.", null=True, blank=True)
    montado = models.DateField("Mon.", null=True, blank=True)
    empalmeE = models.DateField("Ele.", null=True, blank=True)
    porcentaje = models.FloatField("Porcentaje", default=0.0)
    fechaFin = models.DateField("Fecha Fin", blank=True, null=True)
    comentario = models.TextField("Comentarios", blank=True, null=True)
    class Meta:
        verbose_name = "Avance"
        verbose_name_plural = "Avance Proyectos"
        
    def __str__(self):
        return f"{self.sitio}"


