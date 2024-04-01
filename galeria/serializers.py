from rest_framework import serializers
from .models import Galeria, Imagen

class ImagenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Imagen
        # fields = ['imagen', 'descripcion', 'fecha_carga']
        fields = ['imagen', 'fecha_carga']

class GaleriaSerializer(serializers.ModelSerializer):
    imagenes = ImagenSerializer(many=True, read_only=True)
    
    class Meta:
        model = Galeria
        fields = ['sitio', 'entel_id', 'nombre', 'slug', 'imagenes']

    def get_ultima_imagen(self, obj):
        ultima_imagen = obj.imagenes.last()
        if ultima_imagen:
            return ImagenSerializer(ultima_imagen).data
        return None