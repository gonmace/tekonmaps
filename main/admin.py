
from import_export import resources,fields
from import_export.admin import ImportExportModelAdmin
from import_export.widgets import ForeignKeyWidget
from django.contrib import admin
from .models import Sitio, Avance
from django.utils.dateformat import format


class SitiosResource(resources.ModelResource):
    sitio = fields.Field(column_name='PTI Cell ID',attribute='sitio')
    entel_id = fields.Field(column_name='Entel ID', attribute='entel_id')
    nombre = fields.Field(column_name='Name Site', attribute='nombre')
    altura = fields.Field(column_name='ESA Height (Mdto)', attribute='altura')
    contratista = fields.Field(column_name='Partner CW', attribute='contratista')
    lat = fields.Field(column_name='LAT', attribute='lat')
    lon = fields.Field(column_name='LON', attribute='lon')
    ito = fields.Field(column_name='ITO', attribute='ito')
    
    class Meta:
        model = Sitio
        fields = ()
        export_order = (
            'sitio',
            'entel_id',
            'nombre',
            'altura',
            'contratista',
            'lat',
            'lon',
            'ito',
        )
        import_id_fields = ('sitio',)

@admin.register(Sitio)
class SitioAdmin(ImportExportModelAdmin):
    resource_class = SitiosResource
    list_display = (
        'sitio',
        'entel_id',
        'nombre',
        'altura',
        'contratista',
        'ito',
    )
    list_editable = ('ito',)
    list_display_links = ('sitio', )

# admin.site.register(Avance)

class AvanceResource(resources.ModelResource):
    sitio = fields.Field(
        column_name='PTI Cell ID',
        attribute='sitio',
        widget=ForeignKeyWidget(Sitio, 'sitio'))  
    estado = fields.Field(column_name='Estado', attribute='estado')
    
    excavacion = fields.Field(column_name='EJEC. EXCAVACION', attribute='excavacion')
    hormigonado = fields.Field(column_name='EJEC. HORMIGONADO', attribute='hormigonado')
    montado = fields.Field(column_name='EJEC.IZADO DE TORRE', attribute='montado')
    empalmeE = fields.Field(column_name='EJEC.L.E.PROV', attribute='empalmeE')

    porcentaje = fields.Field(column_name='Status PROY', attribute='porcentaje')
    fechaFin = fields.Field(column_name='PROG.CIERRE PERIMETRAL Y OBRAS ADICIONALES', attribute='fechaFin')
    comentario = fields.Field(column_name='ESTADO ACTUAL', attribute='comentario')
    
    class Meta:
        model = Avance
        fields = ()
        export_order = (
            'sitio',
            'estado',
            'excavacion',
            'hormigonado',
            'montado',
            'empalmeE',
            'porcentaje',
            'fechaFin',
            'comentario',
        )
        import_id_fields = ('sitio',)
        
@admin.register(Avance)
class AvanceAdmin(ImportExportModelAdmin):
    resource_class = AvanceResource
    list_display = (
        'sitio',
        'display_entel_id',
        'display_nombre',
        'estado',
        'formato_excavacion',
        'formato_hormigonado',
        'formato_montado',
        'formato_empalmeE',
        'porcentaje',
        'formato_fechaFinal',
        'comentario',
    )
    list_editable = (
        'estado',
        'porcentaje',
        'comentario',
    )
    list_display_links = ('sitio', )
    
    def display_entel_id(self, obj):
        # Accede al campo entel_id del modelo Sitio relacionado
        return obj.sitio.entel_id
    display_entel_id.short_description = 'Entel ID' 
    
    def display_nombre(self, obj):
        # Accede al campo entel_id del modelo Sitio relacionado
        return obj.sitio.nombre
    display_entel_id.short_description = 'Nombre' 

    def formato_excavacion(self, obj):
        return self.formato_fecha(obj.excavacion)
    formato_excavacion.short_description = 'Excavación'  # Establece el título de la columna

    def formato_hormigonado(self, obj):
        return self.formato_fecha(obj.hormigonado)
    formato_hormigonado.short_description = 'Hormigonado'

    def formato_montado(self, obj):
        return self.formato_fecha(obj.montado)
    formato_montado.short_description = 'Montado'

    def formato_empalmeE(self, obj):
        return self.formato_fecha(obj.empalmeE)
    formato_empalmeE.short_description = 'Empalme Eléc.'
    
    def formato_fechaFinal(self, obj):
        return self.formato_fecha(obj.fechaFin)
    formato_fechaFinal.short_description = 'Fecha Final'

    def formato_fecha(self, fecha):
        if fecha:
            return format(fecha, 'd/m/Y')  # Formatea la fecha como dd/mm/YY
        return '---'
