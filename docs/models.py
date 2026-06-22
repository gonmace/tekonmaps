import re

from django.contrib.auth.models import User
from django.db import models


_FORBIDDEN_FS = re.compile(r'[\\/<>:"|?*]+')


def _sanitize_segment(name):
    """Sanea un nombre para usarlo como carpeta en Nextcloud/WebDAV."""
    name = _FORBIDDEN_FS.sub("-", str(name))
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:120] or "documento"


def _norm_key(s):
    """Clave normalizada (solo alfanuméricos en minúscula) para comparar nombres."""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _acronimo(texto):
    """Acrónimo inicial de un nombre/código de documento, quitando el prefijo de
    sitio ``CL-XX-0000``. Ej. ``CL-XX-0000-COC_...`` → ``COC``; ``PR-O&M-Report`` →
    ``PR-O&M``; ``WRC_Acta...`` → ``WRC``."""
    rest = re.sub(r"^\s*CL-XX-0000\s*[-_ ]?\s*", "", str(texto), flags=re.I).strip()
    m = re.match(r"[A-Za-z0-9]+(?:[-&][A-Za-z0-9]+)*", rest)
    return m.group(0) if m else ""


def _codigo_a_regex(codigo):
    """Convierte un código de template (col. DOCUMENTO) en un patrón regex que
    tolera la parte variable del nombre real del archivo: el placeholder ``XX`` y
    los números (``CL-XX-0000`` → ``CL-ML-1345``), y revisiones (``Rev.02``).
    Devuelve el patrón o None si no se puede compilar.

    Se tokeniza el código en tramos fijos (texto literal, escapado) y variables
    (``XX`` → letras/dígitos; dígitos → ``\\d+``; espacios → ``\\s+``)."""
    partes = []
    for tok in re.findall(r"XX|\d+|\s+|[^XX\d\s]+|X", codigo):
        if tok == "XX":
            partes.append(r"[A-Za-z0-9]{1,6}")
        elif tok.isdigit():
            partes.append(r"\d+")
        elif tok.isspace():
            partes.append(r"\s+")
        else:
            partes.append(re.escape(tok))
    esc = "".join(partes)
    try:
        re.compile(esc)
    except re.error:
        return None
    return esc


# Roles ITO (campo de DocumentoEsperado) → etiqueta. Usado por UserProfile.rol_ito
# y por DocumentoEsperado.ROLES (que además lleva la sigla).
ROL_ITO_CHOICES = [
    ("rol_buscador", "Buscador"),
    ("rol_tk_redline", "TK Redline"),
    ("rol_constructor", "Constructora"),
    ("rol_ito", "ITO"),
    ("rol_ito_hse", "ITO HSE"),
    ("rol_esp_electrico", "Eléctrico"),
    ("rol_coordinador", "Coordinador"),
]

# Color distintivo por rol (sigla → hex). Usado en los badges del seguimiento y la leyenda.
ROL_COLORES = {
    "BUS": "#2563eb",  # azul
    "TKR": "#e11d48",  # rosa/rojo
    "CON": "#d97706",  # ámbar
    "ITO": "#059669",  # esmeralda
    "HSE": "#eab308",  # amarillo seguridad (hi-vis)
    "ELE": "#7c3aed",  # violeta
    "COO": "#0891b2",  # cian
}

# Acciones de "revisión": requieren confirmación manual (modal). El resto se
# auto-confirma al subir el archivo, según el rol del usuario.
ACCIONES_REVISION = {"REVISAR", "FIRMAR"}

# Roles transversales con acceso a TODOS los sitios sin necesidad de AccesoSitio
# (como el superusuario). No hace falta asignarles sitios en el Panel.
ROLES_TODO_SITIO = ("rol_coordinador", "rol_tk_redline")


class UserProfile(models.Model):
    # Rol único consolidado: 'visitante' (solo lectura) o una de las funciones ITO
    # (edita/sube/confirma y auto-confirma su rol en el documento). 'rol_coordinador'
    # además acepta borrados. El superusuario de Django es el tope.
    ROL_CHOICES = [("visitante", "Visitante")] + ROL_ITO_CHOICES
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    rol = models.CharField(max_length=20, choices=ROL_CHOICES, default="visitante")
    # Acceso por sección del navbar (el superusuario ve todo). Restrictivo por defecto:
    # el superusuario habilita cada sección por usuario en el Panel.
    acceso_contratista = models.BooleanField("Acceso Docs. Contratista", default=False)
    acceso_finales = models.BooleanField("Acceso Docs. Finales", default=False)
    acceso_seguimiento = models.BooleanField("Acceso Seguimiento", default=False)

    class Meta:
        verbose_name = "Perfil de usuario"
        verbose_name_plural = "Perfiles de usuario"

    def __str__(self):
        return f"{self.user.username} ({self.get_rol_display()})"


class AccesoSitio(models.Model):
    """Sitios (carpetas de Nextcloud) a los que un usuario tiene acceso.

    Restricción por (empresa, sitio). El superusuario no se restringe (ve todo).
    Sin filas para un usuario => no ve ningún sitio (criterio restrictivo).
    """
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="sitios_permitidos")
    empresa = models.CharField(
        max_length=100, help_text="Código de empresa (companies.json).")
    sitio = models.CharField(
        max_length=200, help_text="Nombre de la carpeta del sitio en Nextcloud.")

    class Meta:
        verbose_name = "Acceso a sitio"
        verbose_name_plural = "Accesos a sitios"
        unique_together = [("user", "empresa", "sitio")]
        ordering = ["user", "empresa", "sitio"]

    def __str__(self):
        return f"{self.user.username} → {self.empresa}/{self.sitio}"


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
        if rol != "visitante" and self.link_admin:
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
        if rol != "visitante" and self.link_admin:
            return self.link_admin
        return self.link_visitante


class PlantillaEstructura(models.Model):
    """Estructura nombrada y reutilizable de documentos esperados (la "plantilla").
    Cada :class:`DocumentoEsperado` pertenece a una plantilla; cada sitio apunta a una
    (vía :class:`SitioEstructura`) o usa la plantilla **default**. Permite guardar la
    estructura actual con un nombre y reutilizarla en otros sitios."""
    nombre = models.CharField(max_length=120, unique=True)
    descripcion = models.CharField(max_length=255, blank=True)
    es_default = models.BooleanField(
        default=False,
        help_text="Plantilla usada por los sitios sin asignación explícita. Solo una.")
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Plantilla de estructura"
        verbose_name_plural = "Plantillas de estructura"
        ordering = ["-es_default", "nombre"]

    def __str__(self):
        return self.nombre + (" (default)" if self.es_default else "")

    @classmethod
    def get_default(cls):
        """Devuelve (o crea) la plantilla marcada como default."""
        p = cls.objects.filter(es_default=True).first()
        if p is None:
            p = cls.objects.create(nombre="Estructura base", es_default=True)
        return p


class DocumentoEsperado(models.Model):
    """Documento esperado en obra, según la matriz ESTRUCTURA DOCUMENTOS.
    Define la lista maestra (por plantilla) contra la que se mide la completitud por sitio."""
    ETAPA_CHOICES = [
        ("00_ING._Y_DOC_TECNICA", "00 · Ingeniería y Doc. Técnica"),
        ("01_HABILITACION_E_INICIO", "01 · Habilitación e Inicio"),
        ("02_CALIDAD_OOCC", "02 · Calidad OOCC"),
        ("03_MONTAJE_E_IZAJE", "03 · Montaje e Izaje"),
        ("04_ELECTRICO", "04 · Eléctrico"),
        ("05_SEGUIMIENTO", "05 · Seguimiento"),
        ("06_CIERRE_Y_RECEPCION", "06 · Cierre y Recepción"),
        ("07_OTROS", "07 · Otros"),
    ]
    ACCION_CHOICES = [
        ("ELABORAR", "Elaborar"),
        ("REVISAR", "Revisar"),
        ("FIRMAR", "Firmar"),
        ("PRESENTAR", "Presentar"),
    ]
    # Campos de rol: (campo, etiqueta legible, sigla compacta).
    ROLES = [
        ("rol_buscador", "Buscador", "BUS"),
        ("rol_tk_redline", "TK Redline", "TKR"),
        ("rol_constructor", "Constructora", "CON"),
        ("rol_ito", "ITO", "ITO"),
        ("rol_ito_hse", "ITO HSE", "HSE"),
        ("rol_esp_electrico", "Eléctrico", "ELE"),
        ("rol_coordinador", "Coordinador", "COO"),
    ]

    plantilla = models.ForeignKey(
        PlantillaEstructura, on_delete=models.CASCADE, related_name="documentos")
    etapa = models.CharField(max_length=30, choices=ETAPA_CHOICES)
    carpeta = models.CharField(
        max_length=120, blank=True,
        help_text="Subcarpeta contenedora (columna CARPETA del xlsx), ej. PLANOS, ABUILT."
    )
    nombre = models.CharField(
        max_length=255,
        help_text="Nombre del documento esperado."
    )
    codigo = models.CharField(
        max_length=255, blank=True,
        help_text="Código/nombre del template (columna DOCUMENTO del xlsx)."
    )
    rol_buscador = models.CharField(max_length=12, blank=True, choices=ACCION_CHOICES)
    rol_tk_redline = models.CharField(max_length=12, blank=True, choices=ACCION_CHOICES)
    rol_constructor = models.CharField(max_length=12, blank=True, choices=ACCION_CHOICES)
    rol_ito = models.CharField(max_length=12, blank=True, choices=ACCION_CHOICES)
    rol_ito_hse = models.CharField(max_length=12, blank=True, choices=ACCION_CHOICES)
    rol_esp_electrico = models.CharField(max_length=12, blank=True, choices=ACCION_CHOICES)
    rol_coordinador = models.CharField(max_length=12, blank=True, choices=ACCION_CHOICES)
    TIPO_CHOICES = [
        ("", "Cualquiera"),
        ("PDF", "PDF"),
        ("DWG", "DWG"),
        ("XLSX", "Excel"),
        ("DOCX", "Word"),
        ("JPG", "Imagen"),
    ]
    # Familias de extensiones equivalentes por tipo esperado.
    _TIPO_ALIAS = {"XLSX": {"XLSX", "XLS"}, "DOCX": {"DOCX", "DOC"},
                   "JPG": {"JPG", "JPEG", "PNG"}}
    tipo_esperado = models.CharField(
        max_length=8, blank=True, choices=TIPO_CHOICES,
        help_text="Tipo de archivo esperado. 'Presente' = hay ≥1 de este tipo. Vacío = cualquiera.")
    obligatorio = models.BooleanField(default=True)
    galeria = models.BooleanField(
        default=False,
        help_text="Mostrar los archivos como mosaico de fotos (modal grande). Para "
                  "documentos tipo registro fotográfico.")
    orden = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Documento esperado"
        verbose_name_plural = "Documentos esperados"
        ordering = ["etapa", "orden", "nombre"]
        unique_together = [("plantilla", "etapa", "nombre")]

    def __str__(self):
        return f"{self.get_etapa_display()} · {self.nombre}"

    def carpeta_etapa(self):
        """Carpeta de la etapa en Nextcloud, ej. '00_ING._Y_DOC_TECNICA'."""
        return _sanitize_segment(self.etapa)

    def carpeta_contenedora(self):
        """Carpeta donde vive el documento (como archivo): etapa/[CARPETA].
        Los documentos NO tienen carpeta propia: son archivos sueltos en la etapa,
        o dentro de su subcarpeta (columna CARPETA, ej. PLANOS)."""
        segs = [self.carpeta_etapa()]
        if self.carpeta:
            segs.append(_sanitize_segment(self.carpeta))
        return "/".join(segs)

    def _claves(self):
        """[(clave_normalizada, peso)] para reconocer archivos de este documento.
        Mayor peso = coincidencia más específica (desempata entre documentos)."""
        claves = []
        for txt in (self.nombre, _acronimo(self.nombre), _acronimo(self.codigo)):
            k = _norm_key(txt)
            if len(k) >= 3:
                claves.append((k, len(k)))
        return claves

    def score_match(self, filename):
        """Puntaje de coincidencia del archivo con este documento (0 = no coincide).
        Reconoce tanto el nombre completo del código (col. DOCUMENTO, con el sitio
        ``CL-XX-0000`` variable) como el acrónimo + descripción libre del archivo real
        (ej. ``CL-AN-1300-COC-LA CHIMBA.pdf`` → documento COC)."""
        stem = filename.rsplit(".", 1)[0]
        if self.codigo:
            pat = _codigo_a_regex(self.codigo)
            if pat and re.search(pat, stem, re.IGNORECASE):
                return 1000  # señal fuerte: nombre completo del código
        fk = _norm_key(stem)
        return max((peso for clave, peso in self._claves() if clave in fk), default=0)

    def coincide(self, filename):
        """¿El archivo corresponde a este documento? (score > 0)."""
        return self.score_match(filename) > 0

    def tipo_ok(self, extensiones):
        """¿La lista de extensiones (mayúsculas) satisface el tipo esperado?
        Sin tipo esperado → basta cualquier archivo."""
        if not self.tipo_esperado:
            return bool(extensiones)
        aceptadas = self._TIPO_ALIAS.get(self.tipo_esperado, {self.tipo_esperado})
        return any(e in aceptadas for e in extensiones)

    def roles_activos(self):
        """[(label, accion)] de los roles con acción asignada."""
        return [(lbl, getattr(self, f)) for f, lbl, _ in self.ROLES if getattr(self, f)]

    def roles_resumen(self):
        """Píldoras compactas de los roles activos:
        [{sigla, accion, titulo, es_constructor}]. La acción va capitalizada."""
        out = []
        for f, lbl, sigla in self.ROLES:
            v = getattr(self, f)
            if v:
                out.append({
                    "sigla": sigla, "accion": v.capitalize(),
                    "titulo": f"{lbl}: {v}", "es_constructor": f == "rol_constructor",
                })
        return out


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


class SeguimientoCache(models.Model):
    """Caché del estado de completitud de documentos del ITO por sitio."""
    sitio = models.CharField(max_length=200, unique=True)
    ultima_actualizacion_ts = models.FloatField(
        null=True, blank=True,
        help_text="Timestamp Unix de la última modificación del subárbol del sitio."
    )
    datos = models.JSONField(
        help_text="Estado calculado: lista de documentos con presente/falta y agregados."
    )
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Caché Seguimiento ITO"
        verbose_name_plural = "Caché Seguimiento ITO"
        ordering = ["sitio"]

    def __str__(self):
        return f"Seguimiento {self.sitio}"


class AsignacionArchivo(models.Model):
    """Asignación manual de un archivo (por ruta en Nextcloud) a un documento,
    para cuando el nombre no permite reconocerlo automáticamente. No mueve el
    archivo; solo registra la asociación por sitio."""
    empresa = models.CharField(max_length=100)
    sitio = models.CharField(max_length=200)
    path = models.CharField(max_length=500)
    documento = models.ForeignKey(
        DocumentoEsperado, on_delete=models.CASCADE, related_name="asignaciones")
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    fecha = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Asignación de archivo"
        verbose_name_plural = "Asignaciones de archivos"
        unique_together = [("empresa", "sitio", "path")]

    def __str__(self):
        return f"{self.sitio} · {self.path} → {self.documento_id}"


class DocumentoNoNecesario(models.Model):
    """Marca (por sitio) un documento como **no necesario**: no cuenta en la
    completitud. Si no existe la fila, el documento es necesario (default)."""
    empresa = models.CharField(max_length=100)
    sitio = models.CharField(max_length=200)
    documento = models.ForeignKey(
        DocumentoEsperado, on_delete=models.CASCADE, related_name="no_necesarios")

    class Meta:
        verbose_name = "Documento no necesario (por sitio)"
        verbose_name_plural = "Documentos no necesarios (por sitio)"
        unique_together = [("empresa", "sitio", "documento")]

    def __str__(self):
        return f"{self.sitio} · {self.documento_id} (no necesario)"


class ConfirmacionDocumento(models.Model):
    """Confirmación de que el responsable de un rol cumplió su parte de un documento,
    por sitio. Una fila por (empresa, sitio, documento, rol)."""
    empresa = models.CharField(max_length=100)
    sitio = models.CharField(max_length=200)
    documento = models.ForeignKey(
        DocumentoEsperado, on_delete=models.CASCADE, related_name="confirmaciones")
    rol = models.CharField(
        max_length=20, help_text="Campo de rol, ej. 'rol_ito' (ver DocumentoEsperado.ROLES).")
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    fecha = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Confirmación de documento"
        verbose_name_plural = "Confirmaciones de documentos"
        unique_together = [("empresa", "sitio", "documento", "rol")]
        ordering = ["sitio", "documento", "rol"]

    def __str__(self):
        return f"{self.sitio} · {self.documento_id} · {self.rol}"


class ObservacionDocumento(models.Model):
    """Observación de un revisor que **no está conforme** con un documento (deja una nota y
    el documento queda con ⚠ para que se corrija). Una fila por (empresa, sitio, documento,
    rol). Es excluyente con ``ConfirmacionDocumento`` del mismo rol."""
    empresa = models.CharField(max_length=100)
    sitio = models.CharField(max_length=200)
    documento = models.ForeignKey(
        DocumentoEsperado, on_delete=models.CASCADE, related_name="observaciones")
    rol = models.CharField(
        max_length=20, help_text="Campo de rol que observó (ver DocumentoEsperado.ROLES).")
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    texto = models.TextField()
    enmendada = models.BooleanField(
        default=False,
        help_text="El autor de la observación marcó que ya fue subsanada (✓ verde).")
    fecha = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Observación de documento"
        verbose_name_plural = "Observaciones de documentos"
        unique_together = [("empresa", "sitio", "documento", "rol")]
        ordering = ["sitio", "documento", "rol"]

    def __str__(self):
        return f"{self.sitio} · {self.documento_id} · {self.rol} (obs)"


class EliminacionPendiente(models.Model):
    """Marca de un archivo **pendiente de borrado**: un rol pidió eliminarlo (X) pero no se
    borra de Nextcloud hasta que un Coordinador/superusuario lo acepte. Una fila por
    (empresa, sitio, path)."""
    empresa = models.CharField(max_length=100)
    sitio = models.CharField(max_length=200)
    path = models.CharField(max_length=500)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    fecha = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Eliminación pendiente"
        verbose_name_plural = "Eliminaciones pendientes"
        unique_together = [("empresa", "sitio", "path")]
        ordering = ["sitio", "path"]

    def __str__(self):
        return f"{self.sitio} · {self.path} (pendiente)"


class ArchivoOculto(models.Model):
    """Imagen **oculta** (soft-delete reversible) en una galería. El archivo NO se borra de
    Nextcloud: solo se marca para que no aparezca en la galería. Un admin puede restaurarla
    quitando la fila. Una fila por (empresa, sitio, path)."""
    empresa = models.CharField(max_length=100)
    sitio = models.CharField(max_length=200)
    path = models.CharField(max_length=500)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    fecha = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Archivo oculto"
        verbose_name_plural = "Archivos ocultos"
        unique_together = [("empresa", "sitio", "path")]
        ordering = ["sitio", "path"]

    def __str__(self):
        return f"{self.sitio} · {self.path} (oculto)"


class SitioEstructura(models.Model):
    """Plantilla de estructura asignada a un sitio. Sin fila, el sitio usa la default.
    Apunta **por referencia** a la plantilla: editar la plantilla afecta a todos los
    sitios que la usan."""
    empresa = models.CharField(max_length=100)
    sitio = models.CharField(max_length=200)
    plantilla = models.ForeignKey(
        PlantillaEstructura, on_delete=models.CASCADE, related_name="sitios")

    class Meta:
        verbose_name = "Estructura por sitio"
        verbose_name_plural = "Estructuras por sitio"
        unique_together = [("empresa", "sitio")]
        ordering = ["empresa", "sitio"]

    def __str__(self):
        return f"{self.empresa}/{self.sitio} → {self.plantilla_id}"


def plantilla_de_sitio(empresa, sitio):
    """Plantilla asignada a (empresa, sitio), o la default si no hay asignación."""
    se = (SitioEstructura.objects
          .filter(empresa=empresa, sitio=sitio)
          .select_related("plantilla").first())
    return se.plantilla if se else PlantillaEstructura.get_default()
