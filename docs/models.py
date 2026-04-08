from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    ROL_CHOICES = [
        ("administrador", "Administrador"),
        ("visitante", "Visitante"),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    rol = models.CharField(max_length=20, choices=ROL_CHOICES, default="visitante")

    class Meta:
        verbose_name = "Perfil de usuario"
        verbose_name_plural = "Perfiles de usuario"

    def __str__(self):
        return f"{self.user.username} ({self.get_rol_display()})"


class EmpresaLink(models.Model):
    """Links de Nextcloud por empresa (admin y visitante)."""
    nombre = models.CharField(
        max_length=100, unique=True,
        help_text="Código de empresa tal como aparece en companies.json (ej: AJ, MER)."
    )
    link_admin = models.URLField(
        blank=True,
        help_text="URL del share de Nextcloud con permisos de edición (Administrador)."
    )
    link_visitante = models.URLField(
        blank=True,
        help_text="URL del share de Nextcloud de solo lectura (Visitante)."
    )

    class Meta:
        verbose_name = "Links Nextcloud Empresa"
        verbose_name_plural = "Links Nextcloud Empresas"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    def link_para_rol(self, rol):
        if rol == "administrador" and self.link_admin:
            return self.link_admin
        return self.link_visitante


class SiteConfig(models.Model):
    """Links de Nextcloud para Docs. Finales (admin y visitante)."""
    clave = models.CharField(max_length=100, unique=True)
    link_admin = models.URLField(
        blank=True,
        help_text="URL del share de Nextcloud con permisos de edición (Administrador)."
    )
    link_visitante = models.URLField(
        blank=True,
        help_text="URL del share de Nextcloud de solo lectura (Visitante)."
    )
    descripcion = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Docs Finales"
        verbose_name_plural = "Docs Finales"
        ordering = ["clave"]

    def __str__(self):
        return self.clave

    def link_para_rol(self, rol):
        if rol == "administrador" and self.link_admin:
            return self.link_admin
        return self.link_visitante


class EstructuraCache(models.Model):
    """Caché de la estructura (nombres de carpetas) de cada empresa en Docs. Contratista."""
    empresa = models.CharField(max_length=100, unique=True)
    ultima_actualizacion_ts = models.FloatField(null=True, blank=True)
    datos = models.JSONField(help_text="Lista de carpetas con subfolders vacíos.")
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Caché Estructura"
        verbose_name_plural = "Caché Estructuras"

    def __str__(self):
        return f"Estructura {self.empresa}"


class SitioCache(models.Model):
    """Caché del árbol de subcarpetas/archivos de cada sitio en Docs. Contratista."""
    empresa = models.CharField(max_length=100)
    sitio = models.CharField(max_length=200)
    ultima_actualizacion_ts = models.FloatField(
        null=True, blank=True,
        help_text="Timestamp Unix de la última modificación en Nextcloud."
    )
    ultima_actualizacion = models.CharField(
        max_length=50, blank=True,
        help_text="Fecha formateada para mostrar (ej: 14 nov 2025)."
    )
    datos = models.JSONField(
        help_text="Lista de subcarpetas con conteo de archivos."
    )
    fetched_at = models.DateTimeField(
        auto_now=True,
        help_text="Cuándo se actualizó este caché por última vez."
    )

    class Meta:
        unique_together = [("empresa", "sitio")]
        verbose_name = "Caché Sitio"
        verbose_name_plural = "Caché Sitios"
        ordering = ["empresa", "sitio"]

    def __str__(self):
        return f"{self.empresa} / {self.sitio} ({self.ultima_actualizacion or 'sin fecha'})"


class ProyectoFinalCache(models.Model):
    """Caché del árbol de archivos de cada proyecto en 20-PTI SP."""
    nombre = models.CharField(max_length=200, unique=True)
    ultima_actualizacion_ts = models.FloatField(
        null=True, blank=True,
        help_text="Timestamp Unix de la última modificación en Nextcloud."
    )
    ultima_actualizacion = models.CharField(
        max_length=50, blank=True,
        help_text="Fecha formateada para mostrar (ej: 14 nov 2025)."
    )
    datos = models.JSONField(
        help_text="Árbol de carpetas con conteo de archivos."
    )
    fetched_at = models.DateTimeField(
        auto_now=True,
        help_text="Cuándo se actualizó este caché por última vez."
    )

    class Meta:
        verbose_name = "Caché Proyecto Final"
        verbose_name_plural = "Caché Proyectos Finales"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.ultima_actualizacion or 'sin fecha'})"
