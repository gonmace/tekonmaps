from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import EmpresaLink, EstructuraCache, ProyectoFinalCache, SiteConfig, SitioCache, UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name = "Perfil"
    fields = ("rol",)


class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    list_display = ("clave", "link_admin", "link_visitante", "descripcion")
    fields = ("clave", "link_admin", "link_visitante", "descripcion")


@admin.register(EmpresaLink)
class EmpresaLinkAdmin(admin.ModelAdmin):
    list_display = ("nombre", "link_admin", "link_visitante")
    fields = ("nombre", "link_admin", "link_visitante")


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
