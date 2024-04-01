# serializers.py
from rest_framework import serializers
from .models import Sitio

class SitioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sitio
        fields = ['sitio', 'entel_id', 'altura', 'contratista', 'lat', 'lon', 'ito', 'avance_estado', 'avance_excavacion', 'avance_hormigonado', 'avance_montado', 'avance_empalmeE', 'avance_porcentaje', 'avance_fechaFin']
