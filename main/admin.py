
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from django.db import models

from django.contrib import admin
from .models import Sitio, ITO
from .models import PdfFile

class SitioResource(resources.ModelResource):
    fields = (
        'cod',
        'comuna',
        'altura',
        'contratista',
        'estado',
        'lat',
        'lon',
        'hormigonado',
        'montado',
        'empalmeE',
        'ito',
        'descripcion',
        'avance',
        'fechaFin',      
    )
    class Meta:
        model = Sitio

@admin.register(Sitio)
class SitioAdmin(ImportExportModelAdmin):
    resource_class = SitioResource
    list_display = (
        'cod',
        'comuna',
        'altura',
        'contratista',
        'estado',
        'hormigonado',
        'montado',
        'empalmeE',
        'avance',
        'fechaFin',
        'descripcion',
        'ito', 
   
    )
    list_editable = (
        'estado', 'ito', 'hormigonado', 'montado', 'empalmeE', 'avance', 'fechaFin', 'descripcion'
    )
    list_display_links = ('cod', )


class ITOResource(resources.ModelResource):
    fields = (
        'nombre',
        'mobil',
        'correo',
        'rut', 
    )
    class Meta:
        model = ITO

@admin.register(ITO)
class ITOAdmin(ImportExportModelAdmin):
    resource_class = ITOResource
    list_display = (
        'nombre',
        'mobil',
        'correo',
        'rut',
    )
    list_editable = (
        'mobil', 'correo', 'rut'
    )
    list_display_links = ('nombre', )



@admin.register(PdfFile)
class PdfFileAdmin(admin.ModelAdmin):
    list_display = ('title', 'pdf',)
