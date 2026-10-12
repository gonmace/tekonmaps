from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import (
    AccesoSitio,
    AsignacionArchivo,
    CarpetaRaiz,
    ConfirmacionDocumento,
    CopiaRenombrada,
    DocumentoNoNecesario,
    DocumentoEsperado,
    EstructuraCache,
    NextcloudConfig,
    PlantillaEstructura,
    ProyectoFinalCache,
    SeguimientoCache,
    SiteConfig,
    SitioCache,
    SitioEstructura,
    SitioSincronizado,
    UserProfile,
)


@admin.register(AsignacionArchivo)
class AsignacionArchivoAdmin(admin.ModelAdmin):
    list_display = ("empresa", "sitio", "path", "documento", "usuario", "fecha")
    list_filter = ("empresa",)
    search_fields = ("sitio", "path")


@admin.register(DocumentoNoNecesario)
class DocumentoNoNecesarioAdmin(admin.ModelAdmin):
    list_display = ("empresa", "sitio", "documento")
    list_filter = ("empresa",)
    search_fields = ("sitio",)


@admin.register(ConfirmacionDocumento)
class ConfirmacionDocumentoAdmin(admin.ModelAdmin):
    list_display = ("empresa", "sitio", "documento", "rol", "usuario", "fecha")
    list_filter = ("empresa", "rol")
    search_fields = ("sitio",)
    ordering = ("sitio", "documento", "rol")


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name = "Perfil"
    fields = ("rol", "acceso_contratista", "acceso_finales", "acceso_proyectos")


class AccesoSitioInline(admin.TabularInline):
    model = AccesoSitio
    extra = 0
    verbose_name = "Acceso a sitio"
    verbose_name_plural = "Accesos a sitios"


@admin.register(AccesoSitio)
class AccesoSitioAdmin(admin.ModelAdmin):
    list_display = ("user", "empresa", "sitio")
    list_filter = ("empresa",)
    search_fields = ("user__username", "user__email", "sitio")
    ordering = ("user", "empresa", "sitio")


class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline, AccesoSitioInline]


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    list_display = ("clave", "link_admin", "link_visitante", "descripcion")
    fields = ("clave", "link_admin", "link_visitante", "descripcion")


@admin.register(CarpetaRaiz)
class CarpetaRaizAdmin(admin.ModelAdmin):
    list_display = ("carpeta", "codigo", "escanear", "es_contratista", "orden")
    list_editable = ("escanear", "es_contratista", "orden")
    search_fields = ("carpeta", "codigo")


@admin.register(NextcloudConfig)
class NextcloudConfigAdmin(admin.ModelAdmin):
    list_display = ("base_url", "usuario", "actualizado")


@admin.register(SitioSincronizado)
class SitioSincronizadoAdmin(admin.ModelAdmin):
    list_display = ("empresa", "sitio", "usuario", "fecha")
    list_filter = ("empresa",)
    search_fields = ("sitio",)


@admin.register(CopiaRenombrada)
class CopiaRenombradaAdmin(admin.ModelAdmin):
    list_display = ("empresa", "sitio", "path_original", "path_copia", "usuario", "fecha")
    list_filter = ("empresa",)
    search_fields = ("sitio", "path_original", "path_copia")


@admin.register(EstructuraCache)
class EstructuraCacheAdmin(admin.ModelAdmin):
    list_display = ("empresa", "fetched_at")
    readonly_fields = ("empresa", "datos", "fetched_at")
    ordering = ("empresa",)


@admin.register(SitioCache)
class SitioCacheAdmin(admin.ModelAdmin):
    list_display = ("empresa", "sitio", "ultima_actualizacion", "fetched_at")
    readonly_fields = ("empresa", "sitio", "ultima_actualizacion_ts", "ultima_actualizacion", "datos", "fetched_at")
    list_filter = ("empresa",)
    ordering = ("empresa", "sitio")


@admin.register(ProyectoFinalCache)
class ProyectoFinalCacheAdmin(admin.ModelAdmin):
    list_display = ("nombre", "ultima_actualizacion", "fetched_at")
    readonly_fields = ("nombre", "ultima_actualizacion_ts", "ultima_actualizacion", "datos", "fetched_at")
    ordering = ("nombre",)


@admin.register(PlantillaEstructura)
class PlantillaEstructuraAdmin(admin.ModelAdmin):
    list_display = ("nombre", "es_default", "descripcion", "actualizado")
    list_filter = ("es_default",)
    search_fields = ("nombre", "descripcion")


@admin.register(SitioEstructura)
class SitioEstructuraAdmin(admin.ModelAdmin):
    list_display = ("empresa", "sitio", "plantilla")
    list_filter = ("empresa", "plantilla")
    search_fields = ("empresa", "sitio")
    ordering = ("empresa", "sitio")


@admin.register(DocumentoEsperado)
class DocumentoEsperadoAdmin(admin.ModelAdmin):
    list_display = ("plantilla", "etapa", "carpeta", "orden", "nombre", "rol_ito",
                    "rol_ito_hse", "obligatorio", "activo")
    list_filter = ("plantilla", "etapa", "carpeta", "obligatorio", "activo")
    list_editable = ("orden", "obligatorio", "activo")
    search_fields = ("nombre", "codigo", "carpeta")
    ordering = ("etapa", "orden")


@admin.register(SeguimientoCache)
class SeguimientoCacheAdmin(admin.ModelAdmin):
    list_display = ("sitio", "fetched_at")
    readonly_fields = ("sitio", "ultima_actualizacion_ts", "datos", "fetched_at")
    ordering = ("sitio",)
