from django.contrib import admin

from .models import Etapa, Imagen, Nota, Pendiente, Proyecto


class EtapaInline(admin.TabularInline):
    model = Etapa
    extra = 0


@admin.register(Proyecto)
class ProyectoAdmin(admin.ModelAdmin):
    list_display = ("empresa", "sitio", "estado", "actualizado")
    list_filter = ("empresa", "estado")
    search_fields = ("sitio",)
    inlines = [EtapaInline]


@admin.register(Pendiente)
class PendienteAdmin(admin.ModelAdmin):
    list_display = ("titulo", "etapa", "fecha", "hecho", "eliminado_en")
    list_filter = ("hecho", ("eliminado_en", admin.EmptyFieldListFilter))


@admin.register(Nota)
class NotaAdmin(admin.ModelAdmin):
    list_display = ("texto", "etapa", "usuario", "fecha", "eliminado_en")
    list_filter = (("eliminado_en", admin.EmptyFieldListFilter),)


admin.site.register([Imagen])
