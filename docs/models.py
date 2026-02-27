from django.db import models


class DocEmpresa(models.Model):
    """Empresa configurable desde el admin."""
    nombre = models.CharField(
        max_length=100,
        unique=True,
        help_text="Nombre de la empresa (ej: 20 AJ, 20 MER). Se usa como identificador.",
    )
    carpeta_nextcloud = models.CharField(
        max_length=255,
        help_text="Nombre de la carpeta en Nextcloud (ej: 20 AJ). Path = /{carpeta_nextcloud}",
    )
    link_nextcloud = models.URLField(
        max_length=500,
        blank=True,
        help_text="Enlace directo a la carpeta en Nextcloud (opcional).",
    )
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["orden", "nombre"]
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"

    def __str__(self):
        return self.nombre

    @property
    def nombre_display(self):
        """Nombre a mostrar."""
        return self.nombre

    def root_path(self):
        """Path raíz en Nextcloud: /20 AJ, /20 MER, etc."""
        return f"/{self.carpeta_nextcloud}"


