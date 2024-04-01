from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Sitio, Galeria

@receiver(post_save, sender=Sitio)
def crear_o_actualizar_galeria(sender, instance, **kwargs):
    # Construye la descripción completa usando los campos relevantes de Sitio
    descripcion_completa = f"{instance.altura} {instance.contratista}"
    
    # Intenta obtener la Galeria asociada al Sitio actual, o crea una nueva si no existe
    galeria, creada = Galeria.objects.get_or_create(
        sitio=instance,  # Aquí 'nombre' es una instancia de Sitio
        defaults={
            'descripcion': descripcion_completa,
            'entel_id': instance.entel_id,
            'nombre': instance.nombre
        }
    )
    
    if not creada:
        # Si la Galeria ya existía, actualiza los campos necesarios
        galeria.descripcion = descripcion_completa
        galeria.entel_id = instance.entel_id  # Asegura que entel_id se actualice
        galeria.nombre = instance.nombre
        galeria.save()  # Guarda los cambios en la Galeria
