from django.db import models
import os

class ITO(models.Model):
    nombre = models.CharField("Nombre", max_length=25, null=True)
    mobil = models.CharField("Movil", max_length=11, blank=True, null=True)
    correo = models.CharField("email", max_length=30, blank=True, null=True)
    rut = models.CharField("RUT", max_length=11, blank=True, null=True)    
    class Meta:
        verbose_name = "ITO"
        verbose_name_plural = "ITOs"
    
    def __str__(self):
        return self.nombre


ALTURA_CHOICES = [
    (24, '24'),
    (42, '42'),
    (48, '48'),
]

CONTRATISTA_CHOICES = [
    ('MER', 'MER'),
    ('AJ', 'AJ'),
]

ESTADO_CHOICES = [
    ('ASG', 'Asignado',),
    ('EJE', 'Ejecución'),
    ('TER', 'Terminado'),
    ('PTG', 'Postergado'),
    ('CAN', 'Cancelado'),
]

class Sitio(models.Model):
    cod = models.CharField("Codigo Sitio", max_length=10,  null=True)
    comuna = models.CharField("Comuna", max_length=30, blank=True)
    altura = models.IntegerField("Altura", choices=ALTURA_CHOICES, default=42)
    contratista = models.CharField("Contratista", max_length=120, choices=CONTRATISTA_CHOICES, default='MER')
    estado = models.CharField("Estado", max_length=10, choices=ESTADO_CHOICES, default='EJE')
    lat = models.FloatField("Latitud", max_length=11, blank=True, null=True)
    lon = models.FloatField("Longitud", max_length=11, blank=True, null=True)
    ito = models.ForeignKey(ITO, on_delete=models.CASCADE, null=True)
    hormigonado = models.BooleanField("Hor.", default=False)
    montado = models.BooleanField("Mon.", default=False)
    empalmeE = models.BooleanField("Ele.", default=False)
    descripcion = models.TextField("Descripción", null=True, blank=True)
    avance = models.IntegerField("%", default=0)
    fechaFin = models.CharField("Fecha", max_length=10, blank=True, null=True)
    class Meta:
        verbose_name = "Sitio"
        verbose_name_plural = "Sitios"
  
import os

from django.core.files.storage import FileSystemStorage

class OverwriteStorage(FileSystemStorage):
    def get_available_name(self, name, max_length=None):
        # Eliminar el archivo existente si ya existe
        if self.exists(name):
            os.remove(os.path.join(self.location, name))
        return name

class PdfFile(models.Model):
    title = models.CharField(max_length=100, blank=True, editable=False)
    pdf = models.FileField(upload_to='pdfs/', storage=OverwriteStorage())

    def save(self, *args, **kwargs):
        # Si el archivo PDF está presente y el título no está establecido
        if self.pdf and not self.title:
            # Establecer el título como el nombre del archivo sin la extensión
            self.title = os.path.splitext(os.path.basename(self.pdf.name))[0]
        super(PdfFile, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Eliminar el archivo de su ubicación de almacenamiento
        if self.pdf:
            storage, path = self.pdf.storage, self.pdf.path
            super(PdfFile, self).delete(*args, **kwargs)  # Eliminar el objeto antes del archivo
            storage.delete(path)  # Eliminar el archivo
        else:
            super(PdfFile, self).delete(*args, **kwargs)
        
    def __str__(self):
        return self.title