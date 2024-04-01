from django.contrib import admin
from .models import Galeria, Imagen, Comentario
from django.utils.html import format_html


admin.site.register(Galeria)

class ImageAdmin(admin.ModelAdmin):
    list_display = ('galeria','pic_tag',  'fecha_carga',  'descripcion', )
    list_editable = ('descripcion', 'fecha_carga',)
    search_fields = ('galeria__sitio', 'fecha_carga')

    def pic_tag(self, obj):
        return format_html('<img src="{}" style="max-height: 100px;">'.format(obj.imagen.url))

    pic_tag.short_description = 'Imagen'

admin.site.register(Imagen, ImageAdmin)

admin.site.register(Comentario)