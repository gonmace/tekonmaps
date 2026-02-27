from django.contrib import admin
from .models import DocEmpresa


@admin.register(DocEmpresa)
class DocEmpresaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "carpeta_nextcloud", "link_nextcloud", "orden")
    search_fields = ("nombre", "carpeta_nextcloud")
    ordering = ("orden", "nombre")
