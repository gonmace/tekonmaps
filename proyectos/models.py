from django.conf import settings
from django.db import models

ESTADO_PROYECTO = [
    ("ASG", "Asignado"),
    ("ING", "Ingeniería"),
    ("EJE", "Ejecución"),
    ("TER", "Terminado"),
    ("PTG", "Postergado"),
    ("CAN", "Cancelado"),
]
ETAPAS = [
    ("ING", "Ingeniería"),
    ("CON", "Construcción"),
]
ESTADO_ETAPA = [
    ("PEN", "Pendiente"),
    ("CUR", "En curso"),
    ("TER", "Terminada"),
    ("PTG", "Postergada"),
    ("CAN", "Cancelada"),
]
PRIORIDAD = [("A", "Alta"), ("N", "Normal")]
# Carpeta de cada etapa bajo /20-ITO_SEGUIMIENTO/<sitio>/06_PROYECTO/
CARPETA_ETAPA = {"ING": "Ingenieria", "CON": "Construccion"}

USER = settings.AUTH_USER_MODEL


class Proyecto(models.Model):
    """Seguimiento de un sitio: estado general + 2 etapas (se crean al abrirlo)."""
    empresa = models.CharField(max_length=100)
    sitio = models.CharField(max_length=255)
    estado = models.CharField(max_length=3, choices=ESTADO_PROYECTO, default="ASG")
    # Solo los proyectos habilitados (check, lo marca el superusuario) aparecen en Seguimiento.
    activo = models.BooleanField("En seguimiento", default=False)
    # Ubicación en el mapa (se fija desde la página; null = sin ubicar).
    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)
    actualizado_por = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL,
                                        related_name="+")
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("empresa", "sitio")
        verbose_name = "Proyecto"

    def __str__(self):
        return f"{self.empresa} / {self.sitio}"


class Etapa(models.Model):
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name="etapas")
    etapa = models.CharField(max_length=3, choices=ETAPAS)
    estado = models.CharField(max_length=3, choices=ESTADO_ETAPA, default="PEN")
    actualizado_por = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL,
                                        related_name="+")
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("proyecto", "etapa")
        ordering = ["id"]

    def __str__(self):
        return f"{self.proyecto} · {self.get_etapa_display()}"


class Pendiente(models.Model):
    """Actividad por hacer (p. ej. «visita el próximo martes»)."""
    etapa = models.ForeignKey(Etapa, on_delete=models.CASCADE, related_name="pendientes")
    titulo = models.CharField(max_length=200)
    fecha = models.DateField(null=True, blank=True)
    # Hora opcional (solo con fecha). Sin hora el evento del calendario es de día completo.
    hora = models.TimeField(null=True, blank=True)
    # Responsable: un usuario (FK) o un nombre escrito a mano (``responsable``). Si hay
    # usuario, manda; ``responsable`` queda como respaldo del nombre al momento de asignar.
    responsable = models.CharField(max_length=100, blank=True)
    responsable_user = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL,
                                         related_name="+")
    prioridad = models.CharField(max_length=1, choices=PRIORIDAD, default="N")
    hecho = models.BooleanField(default=False)
    hecho_en = models.DateTimeField(null=True, blank=True)
    # True si el pendiente tiene su evento en el calendario de Nextcloud.
    en_calendario = models.BooleanField(default=False)
    creado_por = models.ForeignKey(USER, null=True, on_delete=models.SET_NULL, related_name="+")
    creado = models.DateTimeField(auto_now_add=True)
    # Borrado lógico: el registro se conserva (recuperable desde el admin) pero no se muestra.
    eliminado_en = models.DateTimeField(null=True, blank=True, db_index=True)
    eliminado_por = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name="+")

    class Meta:
        ordering = ["hecho", "prioridad", "fecha", "id"]


class Imagen(models.Model):
    """Imagen de una etapa; el archivo vive en Nextcloud (``path``)."""
    etapa = models.ForeignKey(Etapa, on_delete=models.CASCADE, related_name="imagenes")
    path = models.CharField(max_length=500)
    descripcion = models.CharField(max_length=200, blank=True)
    subido_por = models.ForeignKey(USER, null=True, on_delete=models.SET_NULL, related_name="+")
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-id"]


class Nota(models.Model):
    """Bitácora de la etapa."""
    etapa = models.ForeignKey(Etapa, on_delete=models.CASCADE, related_name="notas")
    texto = models.TextField()
    usuario = models.ForeignKey(USER, null=True, on_delete=models.SET_NULL, related_name="+")
    fecha = models.DateTimeField(auto_now_add=True)
    # Borrado lógico (ver Pendiente).
    eliminado_en = models.DateTimeField(null=True, blank=True, db_index=True)
    eliminado_por = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name="+")

    class Meta:
        ordering = ["-fecha", "-id"]


class Actividad(models.Model):
    """Registro automático de lo que ocurre en un proyecto (quién, qué, cuándo)."""
    TIPOS = [
        ("estado", "Cambio de estado"), ("ubicacion", "Ubicación"), ("itos", "ITOs"),
        ("seguimiento", "Seguimiento"),
        ("pend_crear", "Pendiente creado"), ("pend_editar", "Pendiente editado"),
        ("pend_hecho", "Pendiente completado"), ("pend_reabrir", "Pendiente reabierto"),
        ("pend_eliminar", "Pendiente eliminado"), ("pend_restaurar", "Pendiente restaurado"),
        ("nota_crear", "Nota creada"), ("nota_eliminar", "Nota eliminada"),
        ("nota_restaurar", "Nota restaurada"),
        ("img_subir", "Imagen subida"), ("img_eliminar", "Imagen eliminada"),
    ]
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name="actividades")
    etapa = models.ForeignKey(Etapa, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="+")
    usuario = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="+")
    tipo = models.CharField(max_length=20, choices=TIPOS)
    detalle = models.CharField(max_length=300, blank=True)
    creado = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-creado", "-id"]
        verbose_name_plural = "Actividad"

    def __str__(self):
        return f"{self.proyecto} · {self.get_tipo_display()}"
