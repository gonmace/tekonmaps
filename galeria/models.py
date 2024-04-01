from django.db import models
from django.utils.text import slugify
from django.utils import timezone
from main.models import Sitio
from django.conf import settings
 # Importa el modelo User

class Galeria(models.Model):
    sitio = models.OneToOneField(Sitio, on_delete=models.CASCADE, editable=False)
    entel_id = models.CharField(max_length=10, editable=False)
    nombre = models.CharField(max_length=100, blank=True)
    descripcion = models.TextField(blank=True)
    slug = models.SlugField(max_length=10, unique=True, blank=True)

    def save(self, *args, **kwargs):
        self.slug = slugify(self.sitio)[:10]
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sitio}_{self.entel_id} - {self.nombre} "
        
class Imagen(models.Model):
    galeria = models.ForeignKey(Galeria, on_delete=models.CASCADE, related_name='imagenes')
    imagen = models.ImageField(upload_to='imagenes/')
    descripcion = models.CharField(max_length=52, blank=True, null=True) 
    fecha_carga = models.DateField(default=timezone.now)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='imagenes_subidas')

    def __str__(self):
        return f"{self.galeria.sitio} - {self.fecha_carga}"


class Comentario(models.Model):
    galeria = models.ForeignKey(Galeria, on_delete=models.CASCADE, related_name='comentario')
    comentario = models.TextField(blank=True, null=True)
    fecha_carga = models.DateField(default=timezone.now)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='comentarios_subidas')

    def __str__(self):
        return f"{self.galeria.sitio} - {self.comentario}"
