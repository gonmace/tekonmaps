import json
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from django.contrib.auth.models import User

from docs import company_loader, nextcloud, seguimiento
from docs.models import (
    AccesoSitio, ArchivoOculto, ConfirmacionDocumento, DocumentoEsperado,
    EliminacionPendiente, ObservacionDocumento, PlantillaEstructura, SitioEstructura,
    UserProfile,
)


# Respuesta WebDAV multistatus de ejemplo (Depth 1 sobre una carpeta con 1 subcarpeta y 1 archivo).
_MULTISTATUS = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/remote.php/dav/files/svc/20-ITO_SEGUIMIENTO/Sitio%201/</d:href>
    <d:propstat><d:status>HTTP/1.1 200 OK</d:status>
      <d:prop><d:resourcetype><d:collection/></d:resourcetype>
        <d:getlastmodified>Mon, 14 Nov 2025 10:00:00 GMT</d:getlastmodified></d:prop>
    </d:propstat>
  </d:response>
  <d:response>
    <d:href>/remote.php/dav/files/svc/20-ITO_SEGUIMIENTO/Sitio%201/1-Ingenier%C3%ADa/</d:href>
    <d:propstat><d:status>HTTP/1.1 200 OK</d:status>
      <d:prop><d:resourcetype><d:collection/></d:resourcetype>
        <d:getlastmodified>Mon, 14 Nov 2025 11:00:00 GMT</d:getlastmodified></d:prop>
    </d:propstat>
  </d:response>
  <d:response>
    <d:href>/remote.php/dav/files/svc/20-ITO_SEGUIMIENTO/Sitio%201/registro.pdf</d:href>
    <d:propstat><d:status>HTTP/1.1 200 OK</d:status>
      <d:prop><d:resourcetype/>
        <d:getcontentlength>1234</d:getcontentlength>
        <d:getlastmodified>Tue, 15 Nov 2025 09:30:00 GMT</d:getlastmodified></d:prop>
    </d:propstat>
  </d:response>
</d:multistatus>"""


class PropfindParserTests(TestCase):
    def setUp(self):
        p = mock.patch.object(
            nextcloud, "_base_url",
            return_value="https://nc.example/remote.php/dav/files/svc")
        p.start()
        self.addCleanup(p.stop)

    def test_parsea_carpeta_y_archivo_omite_la_raiz(self):
        items = nextcloud._parse_multistatus(
            _MULTISTATUS.encode(), "/20-ITO_SEGUIMIENTO/Sitio 1")
        # La carpeta consultada se omite; quedan 2 items.
        self.assertEqual(len(items), 2)
        por_nombre = {i["nombre"]: i for i in items}
        self.assertIn("1-Ingeniería", por_nombre)          # tilde decodificada
        self.assertTrue(por_nombre["1-Ingeniería"]["es_dir"])
        self.assertIn("registro.pdf", por_nombre)
        self.assertFalse(por_nombre["registro.pdf"]["es_dir"])
        self.assertEqual(por_nombre["registro.pdf"]["size"], 1234)
        self.assertIsNotNone(por_nombre["registro.pdf"]["mtime"])


class EstadoSitioTests(TestCase):
    def setUp(self):
        cache.clear()  # caché por-carpeta (seg:roots20 / seg:cons:*) entre tests
        # Plantilla default: los sitios sin asignación miden contra ella.
        self.plantilla = PlantillaEstructura.get_default()
        # Doc sin subcarpeta y doc dentro de una subcarpeta (col CARPETA).
        DocumentoEsperado.objects.create(
            plantilla=self.plantilla,
            etapa="00_ING._Y_DOC_TECNICA", nombre="REGISTRO TX/TSS", orden=1,
            rol_ito="ELABORAR")
        DocumentoEsperado.objects.create(
            plantilla=self.plantilla,
            etapa="03_MONTAJE_E_IZAJE", carpeta="SEGURIDAD_IZAJE",
            nombre="WPH-Trabajo en Altura", orden=1, rol_ito_hse="REVISAR")

    def test_documento_en_carpeta_constructor_es_presente(self):
        """Lee la carpeta real del constructor (/20 AJ/<sitio>); el área ITO va vacía."""
        cons = "/20 AJ/Sitio 1"
        fake_items = [
            {"path": f"{cons}/REGISTRO TX-TSS v2.pdf", "nombre": "REGISTRO TX-TSS v2.pdf",
             "es_dir": False, "mtime": 1700000000.0, "size": 10},
            {"path": f"{cons}/notas varias.pdf", "nombre": "notas varias.pdf",
             "es_dir": False, "mtime": 1700000000.0, "size": 5},
        ]

        def fake_tree(path, max_depth=5):
            return fake_items if path.startswith("/20 AJ") else []

        def fake_list_folder(path):  # Depth 1: la subcarpeta del sitio bajo el root
            if path == "/20 AJ":
                return [{"path": cons, "nombre": "Sitio 1", "es_dir": True,
                         "mtime": 1700000000.0, "size": None}]
            return []

        emp = company_loader.Company(nombre="AJ", carpeta_nextcloud="20 AJ")
        with mock.patch.object(nextcloud, "is_configured", return_value=True), \
             mock.patch.object(company_loader, "get_by_nombre", return_value=emp), \
             mock.patch.object(seguimiento, "roots_constructora", return_value=["/20 AJ"]), \
             mock.patch.object(nextcloud, "list_folder", side_effect=fake_list_folder), \
             mock.patch.object(nextcloud, "ensure_tree", return_value=None), \
             mock.patch.object(nextcloud, "tree", side_effect=fake_tree):
            est = seguimiento.estado_sitio("AJ", "Sitio 1")

        self.assertEqual(est["total"], 2)
        self.assertEqual(est["presentes"], 1)
        docs = {x["nombre"]: x for x in est["documentos"]}
        self.assertEqual(docs["REGISTRO TX/TSS"]["estado"], "presente")
        self.assertEqual([a["nombre"] for a in docs["REGISTRO TX/TSS"]["archivos"]],
                         ["REGISTRO TX-TSS v2.pdf"])
        self.assertEqual(docs["WPH-Trabajo en Altura"]["estado"], "falta")
        # El archivo que no coincide con ningún documento aparece en inesperados.
        self.assertEqual([x["nombre"] for x in est["inesperados"]], ["notas varias.pdf"])

    def test_confirmacion_de_rol_aparece_en_estado(self):
        d1 = DocumentoEsperado.objects.get(nombre="REGISTRO TX/TSS")
        u = User.objects.create_user("ito1", password="x")
        ConfirmacionDocumento.objects.create(
            empresa="AJ", sitio="Sitio 1", documento=d1, rol="rol_ito", usuario=u)
        emp = company_loader.Company(nombre="AJ", carpeta_nextcloud="20 AJ")
        with mock.patch.object(nextcloud, "is_configured", return_value=True), \
             mock.patch.object(company_loader, "get_by_nombre", return_value=emp), \
             mock.patch.object(seguimiento, "roots_constructora", return_value=["/20 AJ"]), \
             mock.patch.object(nextcloud, "list_folder", side_effect=lambda path: []), \
             mock.patch.object(nextcloud, "ensure_tree", return_value=None), \
             mock.patch.object(nextcloud, "tree", side_effect=lambda p, max_depth=5: []):
            est = seguimiento.estado_sitio("AJ", "Sitio 1")
        doc = next(x for x in est["documentos"] if x["nombre"] == "REGISTRO TX/TSS")
        rol = next(r for r in doc["roles"] if r["rol"] == "rol_ito")
        self.assertTrue(rol["confirmado"])
        self.assertEqual(rol["usuario"], "ito1")

    def test_coincide_codigo_con_sitio_reemplazado(self):
        d = DocumentoEsperado.objects.create(
            plantilla=self.plantilla,
            etapa="01_HABILITACION_E_INICIO", carpeta="SEGUROS",
            nombre="COI-Seguro Contra Accidentes", orden=2,
            codigo="CL-XX-0000-COI Certificate of Insurance", rol_ito_hse="REVISAR")
        # Archivo real: XX→ML, 0000→1345.
        self.assertTrue(d.coincide("CL-ML-1345-COI Certificate of Insurance.pdf"))
        self.assertTrue(d.coincide("CL-AB-0099-COI Certificate of Insurance.docx"))
        # Otro documento (SRR) no debe coincidir.
        self.assertFalse(d.coincide("CL-ML-1345-SRR Site Reception Report.pdf"))

    def test_carpeta_contenedora(self):
        d1 = DocumentoEsperado.objects.get(nombre="REGISTRO TX/TSS")
        d2 = DocumentoEsperado.objects.get(nombre="WPH-Trabajo en Altura")
        self.assertEqual(d1.carpeta_contenedora(), "00_ING._Y_DOC_TECNICA")
        self.assertEqual(d2.carpeta_contenedora(),
                         "03_MONTAJE_E_IZAJE/SEGURIDAD_IZAJE")

    def test_multimedia_suelta_se_lista_bajo_documento_imagenes(self):
        """Imágenes/videos sueltos (sin match por nombre), aunque vivan en el área de
        constructora, se asignan al documento de 05_SEGUIMIENTO/Imágenes|Videos del sitio."""
        seguimiento_etapa = "05_SEGUIMIENTO"
        DocumentoEsperado.objects.create(
            plantilla=self.plantilla, etapa=seguimiento_etapa, carpeta="Imágenes",
            nombre="Registro fotográfico", orden=1)
        DocumentoEsperado.objects.create(
            plantilla=self.plantilla, etapa=seguimiento_etapa, carpeta="Videos",
            nombre="Registro audiovisual", orden=2)
        ito = seguimiento.ito_path("Sitio 1")
        cons = "/20 AJ/Sitio 1"
        archivos = [
            {"path": f"{cons}/18 FOTOS/foto.jpg", "nombre": "foto.jpg",
             "fecha": "x", "mtime": 1.7e9, "base": cons},
            {"path": f"{cons}/clip.mp4", "nombre": "clip.mp4",
             "fecha": "x", "mtime": 1.7e9, "base": cons},
            {"path": f"{cons}/otros/informe.pdf", "nombre": "informe.pdf",
             "fecha": "x", "mtime": 1.7e9, "base": cons},  # no multimedia → inesperado
        ]
        datos, _ = seguimiento._ensamblar_datos("AJ", "Sitio 1", archivos, ito)
        por_doc = {d["nombre"]: d for d in datos["documentos"]}
        self.assertEqual([a["nombre"] for a in por_doc["Registro fotográfico"]["archivos"]],
                         ["foto.jpg"])
        self.assertEqual(por_doc["Registro fotográfico"]["estado"], "presente")
        self.assertEqual([a["nombre"] for a in por_doc["Registro audiovisual"]["archivos"]],
                         ["clip.mp4"])
        # El PDF sin match sigue en inesperados; la multimedia NO.
        self.assertEqual([x["nombre"] for x in datos["inesperados"]], ["informe.pdf"])

    def test_multimedia_sin_documento_se_omite(self):
        """Sin documento Imágenes/Videos en la plantilla, la multimedia suelta se omite (no
        satura la lista de inesperados)."""
        ito = seguimiento.ito_path("Sitio 1")
        cons = "/20 AJ/Sitio 1"
        archivos = [{"path": f"{cons}/foto.jpg", "nombre": "foto.jpg",
                     "fecha": "x", "mtime": 1.7e9, "base": cons}]
        datos, _ = seguimiento._ensamblar_datos("AJ", "Sitio 1", archivos, ito)
        self.assertEqual(datos["inesperados"], [])
        self.assertFalse(any(d["archivos"] for d in datos["documentos"]))

    def test_no_configurado_devuelve_error(self):
        with mock.patch.object(nextcloud, "is_configured", return_value=False):
            est = seguimiento.estado_sitio("AJ", "Sitio 1")
        self.assertTrue(est["error"])
        self.assertEqual(est["presentes"], 0)

    def test_plantilla_por_sitio_mide_contra_sus_documentos(self):
        """Un sitio asignado a otra plantilla mide su completitud contra los documentos
        de esa plantilla, no contra la default."""
        p2 = PlantillaEstructura.objects.create(nombre="Plantilla B")
        DocumentoEsperado.objects.create(
            plantilla=p2, etapa="07_OTROS", nombre="Solo B", orden=1, rol_ito="ELABORAR")
        SitioEstructura.objects.create(empresa="AJ", sitio="Sitio B", plantilla=p2)
        # is_configured=False evita mockear Nextcloud: los documentos vienen de la BD.
        with mock.patch.object(nextcloud, "is_configured", return_value=False):
            est_default = seguimiento.estado_sitio("AJ", "Sitio 1")  # sin asignación → default
            est_b = seguimiento.estado_sitio("AJ", "Sitio B")        # asignado a Plantilla B
        nombres_default = {d["nombre"] for d in est_default["documentos"]}
        nombres_b = {d["nombre"] for d in est_b["documentos"]}
        self.assertIn("REGISTRO TX/TSS", nombres_default)
        self.assertEqual(nombres_b, {"Solo B"})
        self.assertNotIn("REGISTRO TX/TSS", nombres_b)

    def test_guardar_estructura_en_plantilla_asignada_sin_copia_ni_escaneo(self):
        """'Actualizar estructura' guarda la estructura mostrada EN LA plantilla asignada (en
        su lugar): no crea copia por sitio ni re-escanea Nextcloud, y conserva los documentos."""
        n_plantillas = PlantillaEstructura.objects.count()
        # 'Sitio 1' no tiene asignación → usa la default (compartida).
        resumen = seguimiento.guardar_estructura("AJ", "Sitio 1")

        self.assertEqual(resumen["plantilla"], self.plantilla.nombre)
        self.assertTrue(resumen["es_default"])
        self.assertEqual(resumen["total"], 2)  # los 2 docs activos del setUp
        # No creó copias ni asignaciones por sitio, ni tocó los documentos.
        self.assertEqual(PlantillaEstructura.objects.count(), n_plantillas)
        self.assertFalse(SitioEstructura.objects.filter(empresa="AJ", sitio="Sitio 1").exists())
        self.assertEqual(self.plantilla.documentos.count(), 2)

    def test_guardar_estructura_es_compartida(self):
        """La estructura guardada vive en la plantilla asignada; si otro sitio usa la misma
        plantilla, ve exactamente los mismos documentos."""
        p = PlantillaEstructura.objects.create(nombre="Compartida")
        DocumentoEsperado.objects.create(
            plantilla=p, etapa="07_OTROS", nombre="Doc compartido", orden=1, rol_ito="ELABORAR")
        SitioEstructura.objects.create(empresa="AJ", sitio="Sitio A", plantilla=p)
        SitioEstructura.objects.create(empresa="AJ", sitio="Sitio B", plantilla=p)

        resumen = seguimiento.guardar_estructura("AJ", "Sitio A")
        self.assertEqual(resumen["plantilla"], "Compartida")
        self.assertEqual(resumen["n_sitios"], 2)
        # Ambos sitios miden contra los mismos documentos.
        with mock.patch.object(nextcloud, "is_configured", return_value=False):
            a = seguimiento.estado_sitio("AJ", "Sitio A")
            b = seguimiento.estado_sitio("AJ", "Sitio B")
        self.assertEqual([d["nombre"] for d in a["documentos"]],
                         [d["nombre"] for d in b["documentos"]])

    def test_fast_path_evita_reescaneo_si_no_cambio_la_fecha(self):
        """2ª carga con la misma fecha de carpeta de sitio → sirve del caché sin re-listar
        roots ni escaneo profundo; solo consulta ``folder_lastmod`` de las carpetas de sitio."""
        cons = "/20 AJ/Sitio 1"

        def fake_tree(path, max_depth=5):
            return ([{"path": f"{cons}/REGISTRO TX-TSS v2.pdf", "nombre": "REGISTRO TX-TSS v2.pdf",
                      "es_dir": False, "mtime": 1700000000.0, "size": 10}]
                    if path.startswith("/20 AJ") else [])

        def fake_list_folder(path):
            if path == "/20 AJ":
                return [{"path": cons, "nombre": "Sitio 1", "es_dir": True,
                         "mtime": 1700000000.0, "size": None}]
            return []

        emp = company_loader.Company(nombre="AJ", carpeta_nextcloud="20 AJ")

        # 1ª carga: escaneo completo (puebla SeguimientoCache + firma del fast-path).
        with mock.patch.object(nextcloud, "is_configured", return_value=True), \
             mock.patch.object(company_loader, "get_by_nombre", return_value=emp), \
             mock.patch.object(seguimiento, "roots_constructora", return_value=["/20 AJ"]), \
             mock.patch.object(nextcloud, "ensure_tree", return_value=None), \
             mock.patch.object(nextcloud, "folder_lastmod", return_value=1700000000.0), \
             mock.patch.object(nextcloud, "list_folder", side_effect=fake_list_folder), \
             mock.patch.object(nextcloud, "tree", side_effect=fake_tree) as tr1:
            est1 = seguimiento.estado_sitio("AJ", "Sitio 1")
        self.assertEqual(est1["presentes"], 1)
        self.assertGreater(tr1.call_count, 0)

        # 2ª carga: fast-path. No debe re-listar roots (list_folder) ni escanear (tree).
        with mock.patch.object(nextcloud, "is_configured", return_value=True), \
             mock.patch.object(company_loader, "get_by_nombre", return_value=emp), \
             mock.patch.object(seguimiento, "roots_constructora", return_value=["/20 AJ"]), \
             mock.patch.object(nextcloud, "ensure_tree", return_value=None), \
             mock.patch.object(nextcloud, "folder_lastmod", return_value=1700000000.0), \
             mock.patch.object(nextcloud, "list_folder", side_effect=fake_list_folder) as lf2, \
             mock.patch.object(nextcloud, "tree", side_effect=fake_tree) as tr2:
            est2 = seguimiento.estado_sitio("AJ", "Sitio 1")
        self.assertEqual(est2["presentes"], 1)
        self.assertEqual(est2, est1)
        self.assertEqual(tr2.call_count, 0, "no debe re-escanear a fondo")
        self.assertEqual(lf2.call_count, 0, "no debe re-listar roots")

    def test_editar_documento_se_refleja_sin_reescanear(self):
        """Un cambio en la BD (agregar documento) se refleja en la carga siguiente
        reconstruyendo desde los `archivos` cacheados, sin tocar Nextcloud."""
        cons = "/20 AJ/Sitio 1"

        def fake_tree(path, max_depth=5):
            return [] if not path.startswith("/20 AJ") else [
                {"path": f"{cons}/REGISTRO TX-TSS v2.pdf", "nombre": "REGISTRO TX-TSS v2.pdf",
                 "es_dir": False, "mtime": 1700000000.0, "size": 10}]

        def fake_list_folder(path):
            if path == "/20 AJ":
                return [{"path": cons, "nombre": "Sitio 1", "es_dir": True,
                         "mtime": 1700000000.0, "size": None}]
            return []

        emp = company_loader.Company(nombre="AJ", carpeta_nextcloud="20 AJ")
        patches = lambda: [
            mock.patch.object(nextcloud, "is_configured", return_value=True),
            mock.patch.object(company_loader, "get_by_nombre", return_value=emp),
            mock.patch.object(seguimiento, "roots_constructora", return_value=["/20 AJ"]),
            mock.patch.object(nextcloud, "ensure_tree", return_value=None),
            mock.patch.object(nextcloud, "folder_lastmod", return_value=1700000000.0),
            mock.patch.object(nextcloud, "list_folder", side_effect=fake_list_folder),
        ]

        with patches()[0], patches()[1], patches()[2], patches()[3], patches()[4], patches()[5], \
             mock.patch.object(nextcloud, "tree", side_effect=fake_tree):
            est1 = seguimiento.estado_sitio("AJ", "Sitio 1")
        self.assertEqual(est1["total"], 2)

        # Cambio de BD: se agrega un documento (como al editar en el Panel).
        DocumentoEsperado.objects.create(
            plantilla=self.plantilla,
            etapa="07_OTROS", nombre="Nuevo Documento", orden=1, rol_ito="ELABORAR")

        # 2ª carga sin forzar: refleja el nuevo documento SIN escanear Nextcloud.
        with patches()[0], patches()[1], patches()[2], patches()[3], patches()[4], patches()[5] as lf2, \
             mock.patch.object(nextcloud, "tree", side_effect=fake_tree) as tr2:
            est2 = seguimiento.estado_sitio("AJ", "Sitio 1")
        self.assertEqual(est2["total"], 3, "el nuevo documento debe aparecer")
        self.assertEqual(tr2.call_count, 0, "no debe re-escanear a fondo")
        self.assertEqual(lf2.call_count, 0, "no debe re-listar roots")

    def test_fp_se_guarda_aunque_una_fuente_falle(self):
        """Si un root /20* falla al listar, el fast-path igual se guarda con las demás fuentes
        (antes, un root flaky bloqueaba el cacheo para todos los sitios de esa carga)."""
        cache.clear()

        def fake_list_folder(path):
            if path == "/20 AJ":
                raise RuntimeError("root caído")  # Fase 1 de esta fuente → None
            return []  # el área ITO responde (vacía)

        emp = company_loader.Company(nombre="AJ", carpeta_nextcloud="20 AJ")
        with mock.patch.object(nextcloud, "is_configured", return_value=True), \
             mock.patch.object(company_loader, "get_by_nombre", return_value=emp), \
             mock.patch.object(seguimiento, "roots_constructora", return_value=["/20 AJ"]), \
             mock.patch.object(nextcloud, "ensure_tree", return_value=None), \
             mock.patch.object(nextcloud, "folder_lastmod", return_value=1700000000.0), \
             mock.patch.object(nextcloud, "list_folder", side_effect=fake_list_folder), \
             mock.patch.object(nextcloud, "tree", side_effect=lambda p, max_depth=5: []):
            seguimiento.estado_sitio("AJ", "Sitio 1")
            fp = seguimiento._cache.get(seguimiento._fp_key("AJ/Sitio 1"))
        self.assertIsNotNone(fp, "el fp debe guardarse aunque una fuente falle")
        self.assertIn(seguimiento.ito_path("Sitio 1"), fp["paths"])


class RolConsolidadoTests(TestCase):
    def test_es_admin_y_coordinador_segun_rol(self):
        from docs.views import _es_admin, _es_coordinador
        vis = User.objects.create_user("vis", password="x")
        UserProfile.objects.create(user=vis, rol="visitante")
        ito = User.objects.create_user("ito", password="x")
        UserProfile.objects.create(user=ito, rol="rol_ito")
        coo = User.objects.create_user("coo", password="x")
        UserProfile.objects.create(user=coo, rol="rol_coordinador")
        sup = User.objects.create_user("sup", password="x", is_superuser=True)
        self.assertFalse(_es_admin(vis))
        self.assertTrue(_es_admin(ito))
        self.assertTrue(_es_admin(coo))
        self.assertFalse(_es_coordinador(ito))
        self.assertTrue(_es_coordinador(coo))
        self.assertTrue(_es_coordinador(sup))


class RevisionYBorradoTests(TestCase):
    def setUp(self):
        cache.clear()
        self.plantilla = PlantillaEstructura.get_default()
        self.doc = DocumentoEsperado.objects.create(
            plantilla=self.plantilla, etapa="05_SEGUIMIENTO", nombre="Doc revisión",
            orden=1, rol_ito_hse="REVISAR")
        self.ito = User.objects.create_user("ito_user", password="x")
        UserProfile.objects.create(user=self.ito, rol="rol_ito_hse")
        self.coord = User.objects.create_user("coord", password="x")
        UserProfile.objects.create(user=self.coord, rol="rol_coordinador")
        # Acceso por sitio: las escrituras exigen AccesoSitio al (empresa, sitio).
        for u in (self.ito, self.coord):
            AccesoSitio.objects.create(user=u, empresa="AJ", sitio="S1")
        self.client = Client()

    def _post(self, name, body):
        return self.client.post(reverse(name), data=json.dumps(body),
                                content_type="application/json")

    def test_observar_crea_warning_y_quita_confirmacion(self):
        self.client.force_login(self.ito)
        ConfirmacionDocumento.objects.create(
            empresa="AJ", sitio="S1", documento=self.doc, rol="rol_ito_hse")
        r = self._post("docs:observar", {"empresa": "AJ", "sitio": "S1",
                                         "doc_id": self.doc.id, "rol": "rol_ito_hse",
                                         "texto": "falta firma"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(ObservacionDocumento.objects.filter(
            documento=self.doc, rol="rol_ito_hse").exists())
        self.assertFalse(ConfirmacionDocumento.objects.filter(
            documento=self.doc, rol="rol_ito_hse").exists())

    def test_observar_requiere_texto(self):
        self.client.force_login(self.ito)
        r = self._post("docs:observar", {"empresa": "AJ", "sitio": "S1",
                                         "doc_id": self.doc.id, "rol": "rol_ito_hse",
                                         "texto": "  "})
        self.assertEqual(r.status_code, 400)

    def test_eliminar_marca_no_borra(self):
        self.client.force_login(self.ito)
        with mock.patch.object(nextcloud, "delete") as deleted:
            r = self._post("docs:eliminar_archivo",
                           {"empresa": "AJ", "sitio": "S1", "path": "/20 AJ/S1/f.pdf"})
        self.assertEqual(r.status_code, 200)
        deleted.assert_not_called()
        self.assertTrue(EliminacionPendiente.objects.filter(path="/20 AJ/S1/f.pdf").exists())

    def test_aceptar_requiere_coordinador(self):
        self.client.force_login(self.ito)  # rol_ito_hse, no coordinador
        EliminacionPendiente.objects.create(empresa="AJ", sitio="S1", path="/20 AJ/S1/f.pdf")
        with mock.patch.object(nextcloud, "delete") as deleted:
            r = self._post("docs:aceptar_eliminacion",
                           {"empresa": "AJ", "sitio": "S1", "path": "/20 AJ/S1/f.pdf"})
        self.assertEqual(r.status_code, 403)
        deleted.assert_not_called()
        self.assertTrue(EliminacionPendiente.objects.filter(path="/20 AJ/S1/f.pdf").exists())

    def test_aceptar_eliminacion_borra(self):
        self.client.force_login(self.coord)
        EliminacionPendiente.objects.create(empresa="AJ", sitio="S1", path="/20 AJ/S1/f.pdf")
        with mock.patch.object(nextcloud, "delete", return_value=204) as deleted:
            r = self._post("docs:aceptar_eliminacion",
                           {"empresa": "AJ", "sitio": "S1", "path": "/20 AJ/S1/f.pdf"})
        self.assertEqual(r.status_code, 200)
        deleted.assert_called_once()
        self.assertFalse(EliminacionPendiente.objects.filter(path="/20 AJ/S1/f.pdf").exists())

    def test_rechazar_quita_marca_sin_borrar(self):
        self.client.force_login(self.coord)
        EliminacionPendiente.objects.create(empresa="AJ", sitio="S1", path="/20 AJ/S1/f.pdf")
        with mock.patch.object(nextcloud, "delete") as deleted:
            r = self._post("docs:rechazar_eliminacion",
                           {"empresa": "AJ", "sitio": "S1", "path": "/20 AJ/S1/f.pdf"})
        self.assertEqual(r.status_code, 200)
        deleted.assert_not_called()
        self.assertFalse(EliminacionPendiente.objects.filter(path="/20 AJ/S1/f.pdf").exists())

    def test_escritura_en_sitio_no_asignado_da_403(self):
        """IDOR: un usuario con rol pero sin AccesoSitio al (empresa, sitio) no puede mutarlo,
        aunque sí pueda actuar sobre los sitios que tiene asignados."""
        self.client.force_login(self.ito)  # solo tiene AccesoSitio a ("AJ", "S1")
        r = self._post("docs:observar", {"empresa": "AJ", "sitio": "OTRO",
                                         "doc_id": self.doc.id, "rol": "rol_ito_hse",
                                         "texto": "intruso"})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(ObservacionDocumento.objects.filter(sitio="OTRO").exists())
        with mock.patch.object(nextcloud, "delete") as deleted:
            r = self._post("docs:eliminar_archivo",
                           {"empresa": "AJ", "sitio": "OTRO", "path": "/20 AJ/OTRO/f.pdf"})
        self.assertEqual(r.status_code, 403)
        deleted.assert_not_called()

    def test_desasignar_quita_la_asignacion(self):
        from docs.models import AsignacionArchivo
        self.client.force_login(self.ito)
        AsignacionArchivo.objects.create(
            empresa="AJ", sitio="S1", path="/20 AJ/S1/f.pdf", documento=self.doc)
        r = self._post("docs:desasignar_archivo",
                       {"empresa": "AJ", "sitio": "S1", "path": "/20 AJ/S1/f.pdf"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(AsignacionArchivo.objects.filter(path="/20 AJ/S1/f.pdf").exists())


class OcultarFotosTests(TestCase):
    """Soft-delete reversible de fotos en una galería (ArchivoOculto): nunca toca Nextcloud."""

    def setUp(self):
        cache.clear()
        self.ito = User.objects.create_user("ito_user", password="x")
        UserProfile.objects.create(user=self.ito, rol="rol_ito")
        AccesoSitio.objects.create(user=self.ito, empresa="AJ", sitio="S1")
        self.vis = User.objects.create_user("vis", password="x")
        UserProfile.objects.create(user=self.vis, rol="visitante")
        self.client = Client()

    def _post(self, name, body):
        return self.client.post(reverse(name), data=json.dumps(body),
                                content_type="application/json")

    def test_ocultar_varias_no_borra_de_nextcloud(self):
        self.client.force_login(self.ito)
        with mock.patch.object(nextcloud, "delete") as deleted:
            r = self._post("docs:ocultar_archivo", {
                "empresa": "AJ", "sitio": "S1",
                "paths": ["/20 AJ/S1/a.jpg", "/20 AJ/S1/b.jpg"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["ocultos"], 2)
        deleted.assert_not_called()
        self.assertEqual(ArchivoOculto.objects.filter(empresa="AJ", sitio="S1").count(), 2)

    def test_restaurar_quita_la_marca(self):
        self.client.force_login(self.ito)
        ArchivoOculto.objects.create(empresa="AJ", sitio="S1", path="/20 AJ/S1/a.jpg")
        r = self._post("docs:restaurar_archivo",
                       {"empresa": "AJ", "sitio": "S1", "path": "/20 AJ/S1/a.jpg"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(ArchivoOculto.objects.filter(path="/20 AJ/S1/a.jpg").exists())

    def test_visitante_no_puede_ocultar(self):
        self.client.force_login(self.vis)
        r = self._post("docs:ocultar_archivo",
                       {"empresa": "AJ", "sitio": "S1", "paths": ["/20 AJ/S1/a.jpg"]})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(ArchivoOculto.objects.exists())

    def test_ocultar_sitio_no_asignado_da_403(self):
        self.client.force_login(self.ito)  # solo AccesoSitio a ("AJ", "S1")
        r = self._post("docs:ocultar_archivo",
                       {"empresa": "AJ", "sitio": "OTRO", "paths": ["/20 AJ/OTRO/a.jpg"]})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(ArchivoOculto.objects.exists())


class AccesoTodoSitioTests(TestCase):
    """Coordinador y TK Redline ven todos los sitios sin AccesoSitio (como el superusuario)."""

    def _user(self, username, rol):
        u = User.objects.create_user(username, password="x")
        UserProfile.objects.create(user=u, rol=rol)
        return u

    def test_roles_transversales_sin_restriccion(self):
        from docs.views import _sitios_permitidos, _empresas_permitidas, _denegar_sitio
        for rol in ("rol_coordinador", "rol_tk_redline"):
            u = self._user(f"u_{rol}", rol)
            # Sin ninguna AccesoSitio: igualmente ve todo (None = sin restricción).
            self.assertIsNone(_sitios_permitidos(u, "AJ"), rol)
            self.assertIsNone(_empresas_permitidas(u), rol)
            self.assertIsNone(_denegar_sitio(u, "AJ", "CUALQUIER-SITIO"), rol)

    def test_rol_normal_sigue_restringido(self):
        from docs.views import _sitios_permitidos, _denegar_sitio
        u = self._user("u_ito", "rol_ito")
        self.assertEqual(_sitios_permitidos(u, "AJ"), set())
        self.assertIsNotNone(_denegar_sitio(u, "AJ", "S1"))  # 403: sin AccesoSitio


class ZonaHorariaTests(TestCase):
    """La zona horaria del navegador (cookie 'tz') manda; los timestamps se muestran local."""

    def _tz_activada(self, cookie_val):
        from django.http import HttpResponse
        from django.test import RequestFactory
        from django.utils import timezone
        from core.middleware import TimezoneMiddleware
        capturado = {}

        def get_response(req):
            capturado['tz'] = timezone.get_current_timezone_name()
            return HttpResponse()

        req = RequestFactory().get('/')
        if cookie_val is not None:
            req.COOKIES['tz'] = cookie_val
        TimezoneMiddleware(get_response)(req)
        return capturado['tz']

    def test_cookie_valida_activa_su_tz(self):
        self.assertEqual(self._tz_activada('America/La_Paz'), 'America/La_Paz')

    def test_cookie_invalida_o_ausente_usa_fallback(self):
        # settings.TIME_ZONE (America/Santiago) es el fallback.
        self.assertEqual(self._tz_activada('Marte/Olympus'), 'America/Santiago')
        self.assertEqual(self._tz_activada(None), 'America/Santiago')

    def test_format_fecha_respeta_la_tz_activa(self):
        from datetime import datetime, timezone as dt_tz
        from django.utils import timezone
        from docs.seguimiento import _format_fecha
        dt = datetime(2025, 1, 1, 1, 0, tzinfo=dt_tz.utc)  # 01:00 UTC del 1 de enero
        with timezone.override('America/La_Paz'):           # UTC-4 → 31 dic 21:00
            self.assertEqual(_format_fecha(dt), '31 dic 2024')
        with timezone.override('UTC'):
            self.assertEqual(_format_fecha(dt), '01 ene 2025')
