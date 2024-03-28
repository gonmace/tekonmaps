from django.db import models
from django.utils.text import slugify
from django.utils import timezone

class Galeria(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    slug = models.SlugField(max_length=10, unique=True, blank=True)

    def save(self, *args, **kwargs):
        self.slug = slugify(self.nombre)[:10]
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre} - {self.descripcion}"
        

class Imagen(models.Model):
    imagen = models.ImageField(upload_to='imagenes/')
    galeria = models.ForeignKey(Galeria, on_delete=models.CASCADE, related_name='imagenes')
    descripcion = models.TextField(blank=True, null=True)
    fecha_carga = models.DateField(default=timezone.now)

    def __str__(self):
        return f"{self.galeria.nombre} - {self.fecha_carga}"

