import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from docs import nextcloud
from docs.models import AccesoSitio, UserProfile

from . import calendario, servicios
from .models import Etapa, Imagen, Nota, Pendiente, Proyecto


class ProyectosBase(TestCase):
    def setUp(self):
        cache.clear()
        self.sup = User.objects.create_user("sup", password="x", is_superuser=True)
        self.u = User.objects.create_user("ito", password="x")
        UserProfile.objects.create(user=self.u, rol="rol_ito", acceso_proyectos=True)
        AccesoSitio.objects.create(user=self.u, empresa="AJ", sitio="S1")
        self.client.force_login(self.u)

    def post(self, name, body):
        return self.client.post(reverse(f"proyectos:{name}"), data=json.dumps(body),
                                content_type="application/json")

    def proyecto(self, sitio="S1", activo=True):
        p = servicios.obtener_proyecto("AJ", sitio)
        Proyecto.objects.filter(pk=p.pk).update(activo=activo)
        p.refresh_from_db()
        return p


class AccesoTests(ProyectosBase):
    def test_sin_flag_redirige_y_api_403(self):
        UserProfile.objects.filter(user=self.u).update(acceso_proyectos=False)
        self.assertEqual(self.client.get(reverse("proyectos:index")).status_code, 302)
        r = self.client.get(reverse("proyectos:api_proyecto"), {"empresa": "AJ", "sitio": "S1"})
        self.assertEqual(r.status_code, 403)

    def test_sitio_no_asignado_403(self):
        r = self.client.get(reverse("proyectos:api_proyecto"), {"empresa": "AJ", "sitio": "OTRO"})
        self.assertEqual(r.status_code, 403)

    def test_crea_dos_etapas(self):
        self.proyecto()
        r = self.client.get(reverse("proyectos:api_proyecto"), {"empresa": "AJ", "sitio": "S1"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual([e["etapa"] for e in r.json()["etapas"]], ["ING", "CON"])

    def test_visitante_no_escribe(self):
        UserProfile.objects.filter(user=self.u).update(rol="visitante")
        p = self.proyecto()
        e = p.etapas.get(etapa="CON")
        self.assertEqual(self.post("api_etapa_estado", {"etapa_id": e.pk, "estado": "CUR"}).status_code, 403)
        self.assertEqual(self.post("api_nota_crear", {"etapa_id": e.pk, "texto": "x"}).status_code, 403)


class HabilitarTests(ProyectosBase):
    def test_no_habilitado_404_y_no_escribe(self):
        p = self.proyecto(activo=False)
        r = self.client.get(reverse("proyectos:api_proyecto"), {"empresa": "AJ", "sitio": "S1"})
        self.assertEqual(r.status_code, 404)
        e = p.etapas.get(etapa="CON")
        self.assertEqual(self.post("api_etapa_estado", {"etapa_id": e.pk, "estado": "CUR"}).status_code, 403)

    def test_solo_superusuario_habilita(self):
        body = {"empresa": "AJ", "sitio": "S1", "activo": True}
        self.assertEqual(self.post("api_proyecto_habilitar", body).status_code, 403)
        self.client.force_login(self.sup)
        self.assertEqual(self.post("api_proyecto_habilitar", body).status_code, 200)
        self.assertTrue(Proyecto.objects.get(sitio="S1").activo)
        self.assertEqual(Proyecto.objects.get(sitio="S1").etapas.count(), 2)

    def test_listado_habilitados_filtra_por_acceso(self):
        self.proyecto("S1")
        self.proyecto("S2")
        self.proyecto("S3", activo=False)
        r = self.client.get(reverse("proyectos:api_habilitados"), {"empresa": "AJ"})
        self.assertEqual(r.json()["habilitados"], ["S1"])  # S2 sin AccesoSitio, S3 sin check
        self.client.force_login(self.sup)
        r = self.client.get(reverse("proyectos:api_habilitados"), {"empresa": "AJ"})
        self.assertEqual(r.json()["habilitados"], ["S1", "S2"])


class MultiEmpresaTests(ProyectosBase):
    def test_listado_y_mapa_sin_empresa(self):
        AccesoSitio.objects.create(user=self.u, empresa="MER", sitio="M1")
        a = self.proyecto("S1")
        b = servicios.obtener_proyecto("MER", "M1")
        Proyecto.objects.filter(pk=b.pk).update(activo=True, lat=-20, lon=-70)
        Proyecto.objects.filter(pk=a.pk).update(lat=-33, lon=-70)
        r = self.client.get(reverse("proyectos:api_habilitados"))
        self.assertEqual([(p["empresa"], p["sitio"]) for p in r.json()["proyectos"]],
                         [("AJ", "S1"), ("MER", "M1")])
        r = self.client.get(reverse("proyectos:api_mapa"))
        self.assertEqual(sorted(s["empresa"] for s in r.json()["sitios"]), ["AJ", "MER"])


class MapaTests(ProyectosBase):
    def test_ubicacion_y_mapa(self):
        self.proyecto()
        r = self.post("api_proyecto_ubicacion", {"empresa": "AJ", "sitio": "S1", "lat": -33.4, "lon": -70.6})
        self.assertEqual(r.status_code, 200)
        r = self.client.get(reverse("proyectos:api_mapa"), {"empresa": "AJ"})
        self.assertEqual([s["sitio"] for s in r.json()["sitios"]], ["S1"])

    def test_coordenadas_invalidas(self):
        self.proyecto()
        r = self.post("api_proyecto_ubicacion", {"empresa": "AJ", "sitio": "S1", "lat": 200, "lon": 0})
        self.assertEqual(r.status_code, 400)

    def test_quitar_ubicacion_y_mapa_solo_habilitados(self):
        p = self.proyecto()
        self.post("api_proyecto_ubicacion", {"empresa": "AJ", "sitio": "S1", "lat": -33.4, "lon": -70.6})
        Proyecto.objects.filter(pk=p.pk).update(activo=False)
        r = self.client.get(reverse("proyectos:api_mapa"), {"empresa": "AJ"})
        self.assertEqual(r.json()["sitios"], [])
        Proyecto.objects.filter(pk=p.pk).update(activo=True)
        self.post("api_proyecto_ubicacion", {"empresa": "AJ", "sitio": "S1", "lat": None, "lon": None})
        self.assertIsNone(Proyecto.objects.get(pk=p.pk).lat)

    def test_mapa_oculta_sitios_sin_acceso(self):
        self.proyecto("S2")
        Proyecto.objects.filter(sitio="S2").update(lat=-33, lon=-70)
        r = self.client.get(reverse("proyectos:api_mapa"), {"empresa": "AJ"})
        self.assertEqual(r.json()["sitios"], [])


class EtapasTests(ProyectosBase):
    def estado(self, p, etapa, estado):
        e = p.etapas.get(etapa=etapa)
        return self.post("api_etapa_estado", {"etapa_id": e.pk, "estado": estado})

    def test_ingenieria_excluye_a_las_otras(self):
        p = self.proyecto()
        self.assertEqual(self.estado(p, "CON", "CUR").status_code, 200)
        self.assertEqual(self.estado(p, "ING", "CUR").status_code, 400)
        self.estado(p, "CON", "TER")
        self.assertEqual(self.estado(p, "ING", "CUR").status_code, 200)

    def test_estado_invalido(self):
        p = self.proyecto()
        self.assertEqual(self.estado(p, "ING", "XXX").status_code, 400)

    def test_estado_proyecto_lo_cambia_superusuario_y_coordinador(self):
        self.proyecto()
        body = {"empresa": "AJ", "sitio": "S1", "estado": "EJE"}
        self.client.force_login(self.sup)
        self.assertEqual(self.post("api_proyecto_estado", body).status_code, 200)
        self.assertEqual(Proyecto.objects.get().estado, "EJE")
        coord = User.objects.create_user("coord", password="x")
        UserProfile.objects.create(user=coord, rol="rol_coordinador", acceso_proyectos=True)
        self.client.force_login(coord)
        self.assertEqual(self.post("api_proyecto_estado", {**body, "estado": "TER"}).status_code, 200)
        self.assertEqual(Proyecto.objects.get().estado, "TER")

    def test_ito_no_puede_cambiar_el_estado(self):
        self.proyecto()
        r = self.post("api_proyecto_estado", {"empresa": "AJ", "sitio": "S1", "estado": "EJE"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Proyecto.objects.get().estado, "ASG")

    @override_settings(STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
    def test_selector_de_estado_deshabilitado_para_ito(self):
        html = self.client.get(reverse("proyectos:index")).content.decode()
        self.assertRegex(html, r'id="proyecto-estado"[^>]*disabled')


class PendientesNotasTests(ProyectosBase):
    def test_pendiente_crear_toggle_eliminar(self):
        e = self.proyecto().etapas.get(etapa="CON")
        r = self.post("api_pendiente_crear", {"etapa_id": e.pk, "titulo": "Visita",
                                              "fecha": "2026-10-13", "responsable": "Ana"})
        self.assertEqual(r.status_code, 200)
        p = Pendiente.objects.get()
        self.assertEqual(str(p.fecha), "2026-10-13")
        self.assertTrue(self.post("api_pendiente_toggle", {"id": p.pk}).json()["hecho"])
        self.assertEqual(self.post("api_pendiente_eliminar", {"id": p.pk}).status_code, 200)
        # Borrado lógico: el registro se conserva pero ya no se muestra ni se puede modificar.
        p.refresh_from_db()
        self.assertIsNotNone(p.eliminado_en)
        self.assertEqual(p.eliminado_por, self.u)
        self.assertEqual(self.client.get(reverse("proyectos:api_proyecto"),
                                         {"empresa": "AJ", "sitio": "S1"}).json()["etapas"][0]["pendientes"]
                         + self.client.get(reverse("proyectos:api_proyecto"),
                                           {"empresa": "AJ", "sitio": "S1"}).json()["etapas"][1]["pendientes"], [])
        self.assertEqual(self.post("api_pendiente_toggle", {"id": p.pk}).status_code, 404)

    def test_pendiente_sin_titulo(self):
        e = self.proyecto().etapas.get(etapa="CON")
        self.assertEqual(self.post("api_pendiente_crear", {"etapa_id": e.pk, "titulo": " "}).status_code, 400)

    def test_nota_solo_autor_o_coordinador_borra(self):
        e = self.proyecto().etapas.get(etapa="CON")
        n = Nota.objects.create(etapa=e, texto="hola", usuario=self.sup)
        self.assertEqual(self.post("api_nota_eliminar", {"id": n.pk}).status_code, 403)
        self.client.force_login(self.sup)
        self.assertEqual(self.post("api_nota_eliminar", {"id": n.pk}).status_code, 200)
        n.refresh_from_db()
        self.assertIsNotNone(n.eliminado_en)          # borrado lógico
        self.assertEqual(n.eliminado_por, self.sup)
        notas = [x for e in self.client.get(reverse("proyectos:api_proyecto"),
                 {"empresa": "AJ", "sitio": "S1"}).json()["etapas"] for x in e["notas"]]
        self.assertEqual(notas, [])
        self.assertEqual(self.post("api_nota_eliminar", {"id": n.pk}).status_code, 404)


class ImagenesTests(ProyectosBase):
    def subir(self, etapa, nombre="foto.jpg", data=b"abc"):
        f = SimpleUploadedFile(nombre, data, content_type="image/jpeg")
        return self.client.post(reverse("proyectos:api_imagen_subir"),
                                {"etapa_id": etapa.pk, "descripcion": "d", "archivos": f})

    def test_subir_va_a_nextcloud(self):
        e = self.proyecto().etapas.get(etapa="CON")
        with mock.patch.object(nextcloud, "ensure_tree") as tree, \
                mock.patch.object(nextcloud, "upload") as up:
            r = self.subir(e)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(tree.call_args[0][0], "/20-ITO_SEGUIMIENTO/S1/06_PROYECTO/Construccion")
        self.assertTrue(up.call_args[0][0].startswith(
            "/20-ITO_SEGUIMIENTO/S1/06_PROYECTO/Construccion/"))
        self.assertEqual(Imagen.objects.count(), 1)

    def test_rechaza_no_imagen(self):
        e = self.proyecto().etapas.get(etapa="CON")
        with mock.patch.object(nextcloud, "ensure_tree"), mock.patch.object(nextcloud, "upload") as up:
            r = self.subir(e, nombre="x.exe")
        self.assertEqual(r.status_code, 400)
        up.assert_not_called()

    def test_ver_proxy_y_acceso_por_sitio(self):
        e = self.proyecto().etapas.get(etapa="CON")
        img = Imagen.objects.create(etapa=e, path="/20-ITO_SEGUIMIENTO/S1/a.jpg", subido_por=self.u)
        url = reverse("proyectos:imagen_ver", args=[img.pk])
        with mock.patch.object(nextcloud, "download", return_value=(b"abc", "image/jpeg")):
            self.assertEqual(self.client.get(url).status_code, 200)
            AccesoSitio.objects.filter(user=self.u).delete()
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_eliminar_borra_en_nextcloud(self):
        e = self.proyecto().etapas.get(etapa="CON")
        img = Imagen.objects.create(etapa=e, path="/20-ITO_SEGUIMIENTO/S1/a.jpg", subido_por=self.u)
        with mock.patch.object(nextcloud, "delete") as dele:
            r = self.post("api_imagen_eliminar", {"id": img.pk})
        self.assertEqual(r.status_code, 200)
        dele.assert_called_once_with("/20-ITO_SEGUIMIENTO/S1/a.jpg")
        self.assertFalse(Imagen.objects.exists())


class ArchivosTests(ProyectosBase):
    RAIZ = [
        {"path": "/20-ITO INTERNO/S1/01 INGENIERIA", "nombre": "01 INGENIERIA", "es_dir": True, "mtime": 1.0, "size": None},
        {"path": "/20-ITO INTERNO/S1/02-CONSTRUCCIÓN", "nombre": "02-CONSTRUCCIÓN", "es_dir": True, "mtime": 1.0, "size": None},
        {"path": "/20-ITO INTERNO/S1/otros.txt", "nombre": "otros.txt", "es_dir": False, "mtime": 1.0, "size": 1},
    ]
    HIJOS = [
        {"path": "/20-ITO INTERNO/S1/01 INGENIERIA/plano.pdf", "nombre": "plano.pdf", "es_dir": False,
         "mtime": 1700000000.0, "size": 2048},
    ]

    def setUp(self):
        super().setUp()
        self.proyecto()

    def get(self, name, **params):
        base = {"empresa": "AJ", "sitio": "S1"}
        base.update(params)
        return self.client.get(reverse(f"proyectos:{name}"), base)

    def patches(self):
        return (mock.patch.object(nextcloud, "list_folder", return_value=self.RAIZ),
                mock.patch.object(nextcloud, "tree", return_value=self.HIJOS))

    def test_lista_la_carpeta_de_ingenieria(self):
        pl, pt = self.patches()
        with pl, pt as tree:
            r = self.get("api_archivos", origen="ito", etapa="ING")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(tree.call_args[0][0], "/20-ITO INTERNO/S1/01 INGENIERIA")
        d = r.json()
        self.assertEqual(d["carpetas"], ["01 INGENIERIA"])
        self.assertEqual(d["archivos"], 1)
        self.assertEqual([i["ruta"] for i in d["items"]],
                         ["01 INGENIERIA", "01 INGENIERIA/plano.pdf"])

    def test_construccion_con_acento(self):
        pl, pt = self.patches()
        with pl, pt as tree:
            d = self.get("api_archivos", origen="ito", etapa="CON").json()
        self.assertEqual(d["carpetas"], ["02-CONSTRUCCIÓN"])
        self.assertEqual(tree.call_args[0][0], "/20-ITO INTERNO/S1/02-CONSTRUCCIÓN")

    def test_etapa_sin_carpeta(self):
        pl, pt = self.patches()
        with pl, pt as tree:
            d = self.get("api_archivos", origen="ito", etapa="CIE").json()
        self.assertTrue(d["existe"])
        self.assertEqual(d["carpetas"], [])
        tree.assert_not_called()

    def test_cache_evita_segunda_lectura(self):
        pl, pt = self.patches()
        with pl as lf, pt as tree:
            self.get("api_archivos", origen="ito", etapa="ING")
            n = tree.call_count
            self.get("api_archivos", origen="ito", etapa="ING")
            self.assertEqual(tree.call_count, n)          # servido desde caché
            self.get("api_archivos", origen="ito", etapa="ING", refresh="1")
            self.assertEqual(tree.call_count, n + 1)       # refresh relee

    def test_contratista_usa_raiz_de_la_empresa(self):
        from docs import company_loader
        emp = company_loader.Company(nombre="AJ", carpeta_nextcloud="20 AJ", orden=0)
        with mock.patch.object(company_loader, "get_all", return_value=[emp]), \
                mock.patch.object(nextcloud, "list_folder", return_value=[]) as lf:
            r = self.get("api_archivos", origen="contratista", etapa="ING")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(lf.call_args_list[-1][0][0], "/20 AJ/S1")

    def test_carpeta_inexistente(self):
        import requests
        err = requests.HTTPError(response=mock.Mock(status_code=404))
        with mock.patch.object(nextcloud, "list_folder", side_effect=err):
            r = self.get("api_archivos", origen="ito", etapa="ING")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["existe"])

    def test_sitio_sin_acceso_origen_y_etapa_invalidos(self):
        self.assertEqual(self.get("api_archivos", origen="ito", etapa="ING", sitio="OTRO").status_code, 403)
        self.assertEqual(self.get("api_archivos", origen="xxx", etapa="ING").status_code, 400)
        self.assertEqual(self.get("api_archivos", origen="ito", etapa="ZZZ").status_code, 400)

    def test_resuelve_carpeta_del_sitio_por_codigo(self):
        # En ITO INTERNO el sitio se llama distinto que en la carpeta del contratista.
        raiz_ito = [{"path": "/20-ITO INTERNO/CL-AN-1300 ZA380 LA CHIMBA",
                     "nombre": "CL-AN-1300 ZA380 LA CHIMBA", "es_dir": True, "mtime": 1.0, "size": None}]
        AccesoSitio.objects.create(user=self.u, empresa="AJ", sitio="CL-AN-1300 (ZA380) La Chimba")
        self.proyecto("CL-AN-1300 (ZA380) La Chimba")

        def fake_list(path):
            return raiz_ito if path == "/20-ITO INTERNO" else self.RAIZ
        with mock.patch.object(nextcloud, "list_folder", side_effect=fake_list), \
                mock.patch.object(nextcloud, "tree", return_value=[]):
            d = self.get("api_archivos", sitio="CL-AN-1300 (ZA380) La Chimba",
                         origen="ito", etapa="ING").json()
        self.assertEqual(d["base"], "/20-ITO INTERNO/CL-AN-1300 ZA380 LA CHIMBA")

    def test_descarga_valida_y_traversal(self):
        with mock.patch.object(nextcloud, "download", return_value=(b"%PDF", "application/pdf")) as dl:
            ok = self.get("archivo_ver", origen="ito", ruta="01_ING/plano.pdf")
            self.assertEqual(ok.status_code, 200)
            self.assertEqual(dl.call_args[0][0], "/20-ITO INTERNO/S1/01_ING/plano.pdf")
            self.assertIn("inline", ok["Content-Disposition"])
            for ruta in ("../S2/x.pdf", "/etc/passwd", "a/../../x"):
                self.assertEqual(self.get("archivo_ver", origen="ito", ruta=ruta).status_code, 404)

    def test_html_se_descarga_como_adjunto(self):
        with mock.patch.object(nextcloud, "download", return_value=(b"<script>", "text/html")):
            r = self.get("archivo_ver", origen="ito", ruta="x.html")
        self.assertIn("attachment", r["Content-Disposition"])


class ImagenesCarpetaTests(ProyectosBase):
    def setUp(self):
        super().setUp()
        self.proyecto()

    def _it(self, ruta, es_dir=False, mtime=1.0):
        return {"path": f"/20-ITO INTERNO/S1/{ruta}", "nombre": ruta.rsplit("/", 1)[-1],
                "es_dir": es_dir, "mtime": mtime, "size": 10}

    def test_solo_imagenes_dentro_de_carpetas_de_fotos(self):
        raiz = [self._it("01 INGENIERIA", True)]
        arbol = [
            self._it("01 INGENIERIA/FOTOGRAFIAS", True),
            self._it("01 INGENIERIA/FOTOGRAFIAS/a.jpg", mtime=5.0),
            self._it("01 INGENIERIA/Imágenes/sub/b.PNG", mtime=9.0),
            self._it("01 INGENIERIA/plano.pdf"),
            self._it("01 INGENIERIA/Planos/c.jpg"),          # carpeta que no es de fotos
            self._it("01 INGENIERIA/FOTOS/nota.txt"),         # no es imagen
            self._it("01 INGENIERIA/suelta.jpg"),             # sin carpeta de fotos
        ]
        with mock.patch.object(nextcloud, "list_folder", return_value=raiz), \
                mock.patch.object(nextcloud, "tree", return_value=arbol):
            r = self.client.get(reverse("proyectos:api_imagenes"),
                                {"empresa": "AJ", "sitio": "S1", "etapa": "ING"})
        self.assertEqual(r.status_code, 200)
        nombres = sorted({i["nombre"] for i in r.json()["imagenes"]})
        self.assertEqual(nombres, ["a.jpg", "b.PNG"])
        self.assertEqual(r.json()["imagenes"][0]["nombre"], "b.PNG")   # más reciente primero

    def test_miniatura_usa_preview_y_cachea(self):
        with mock.patch.object(nextcloud, "list_folder", return_value=[]), \
                mock.patch.object(nextcloud, "preview", return_value=(b"PNG", "image/png")) as pv:
            for _ in range(2):
                r = self.client.get(reverse("proyectos:miniatura"), {
                    "empresa": "AJ", "sitio": "S1", "origen": "ito", "ruta": "01 ING/FOTOS/a.jpg"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b"PNG")
        self.assertEqual(pv.call_count, 1)

    def test_miniatura_rechaza_traversal_y_no_imagen(self):
        with mock.patch.object(nextcloud, "list_folder", return_value=[]):
            for ruta in ("../x.jpg", "01/doc.pdf"):
                r = self.client.get(reverse("proyectos:miniatura"), {
                    "empresa": "AJ", "sitio": "S1", "origen": "ito", "ruta": ruta})
                self.assertEqual(r.status_code, 404)

    def test_ing_como_palabra(self):
        self.assertEqual(servicios.carpetas_de_etapa(["00 ING", "01 AB (PLANOS)", "MARKETING"], "ING"),
                         ["00 ING"])


class CalendarioTests(ProyectosBase):
    def setUp(self):
        super().setUp()
        self.e = self.proyecto().etapas.get(etapa="CON")

    def crear(self, **extra):
        body = {"etapa_id": self.e.pk, "titulo": "Visita", "fecha": "2026-10-13", "responsable": "Ana"}
        body.update(extra)
        return self.post("api_pendiente_crear", body)

    def test_crear_con_fecha_crea_evento(self):
        with mock.patch.object(calendario, "habilitado", return_value=True), \
                mock.patch.object(calendario, "guardar_evento") as g:
            r = self.crear()
        self.assertEqual(r.json()["calendario"], "ok")
        g.assert_called_once()
        self.assertTrue(Pendiente.objects.get().en_calendario)

    def test_sin_fecha_no_crea_evento(self):
        with mock.patch.object(calendario, "habilitado", return_value=True), \
                mock.patch.object(calendario, "guardar_evento") as g:
            r = self.crear(fecha="")
        self.assertEqual(r.json()["calendario"], "sin_fecha")
        g.assert_not_called()
        self.assertFalse(Pendiente.objects.get().en_calendario)

    def test_fallo_de_nextcloud_no_impide_guardar(self):
        with mock.patch.object(calendario, "habilitado", return_value=True), \
                mock.patch.object(calendario, "guardar_evento", side_effect=RuntimeError("x")):
            r = self.crear()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["calendario"], "error")
        self.assertEqual(Pendiente.objects.count(), 1)
        self.assertFalse(Pendiente.objects.get().en_calendario)

    def test_toggle_actualiza_y_eliminar_borra(self):
        with mock.patch.object(calendario, "habilitado", return_value=True), \
                mock.patch.object(calendario, "guardar_evento") as g, \
                mock.patch.object(calendario, "borrar_evento") as b:
            self.crear()
            p = Pendiente.objects.get()
            self.post("api_pendiente_toggle", {"id": p.pk})
            self.assertEqual(g.call_count, 2)
            self.assertTrue(Pendiente.objects.get().hecho)
            self.post("api_pendiente_eliminar", {"id": p.pk})
            b.assert_called_once()
        p = Pendiente.objects.get()
        self.assertIsNotNone(p.eliminado_en)
        self.assertFalse(p.en_calendario)

    def test_con_hora_evento_de_una_hora(self):
        import datetime
        p = Pendiente.objects.create(etapa=self.e, titulo="Visita", fecha=datetime.date(2026, 10, 13),
                                     hora=datetime.time(10, 30))
        ics = calendario.construir_ics(p)
        self.assertIn("DTSTART:20261013T103000", ics)
        self.assertIn("DTEND:20261013T113000", ics)
        self.assertNotIn("VALUE=DATE", ics)

    def test_con_hora_cruza_medianoche(self):
        import datetime
        p = Pendiente.objects.create(etapa=self.e, titulo="Guardia", fecha=datetime.date(2026, 10, 13),
                                     hora=datetime.time(23, 30))
        ics = calendario.construir_ics(p)
        self.assertIn("DTSTART:20261013T233000", ics)
        self.assertIn("DTEND:20261014T003000", ics)

    def test_hora_solo_con_fecha_y_se_guarda(self):
        with mock.patch.object(calendario, "habilitado", return_value=False):
            self.crear(hora="10:30")
            self.crear(titulo="Sin fecha", fecha="", hora="10:30")
        self.assertEqual(str(Pendiente.objects.get(titulo="Visita").hora), "10:30:00")
        self.assertIsNone(Pendiente.objects.get(titulo="Sin fecha").hora)

    def test_ics_valido(self):
        import datetime
        p = Pendiente.objects.create(etapa=self.e, titulo="Visita, torre; nº 1", fecha=datetime.date(2026, 10, 13),
                                     responsable="Ana", hecho=True)
        ics = calendario.construir_ics(p)
        self.assertIn("DTSTART;VALUE=DATE:20261013", ics)
        self.assertIn("DTEND;VALUE=DATE:20261014", ics)
        self.assertIn("SUMMARY:✓ Visita\\, torre\\; nº 1 · Construcción", ics)
        self.assertIn(f"UID:pendiente-{p.pk}@pti.tekon-rl.cl", ics)
        self.assertTrue(all(len(l.encode()) <= 75 for l in ics.split("\r\n")))


class ITOsTests(ProyectosBase):
    def setUp(self):
        super().setUp()
        self.proyecto("S9", activo=True)
        self.ito2 = User.objects.create_user("ito2", password="x", first_name="Beto")
        UserProfile.objects.create(user=self.ito2, rol="rol_ito_hse", acceso_proyectos=True)
        self.constructor = User.objects.create_user("cons", password="x")
        UserProfile.objects.create(user=self.constructor, rol="rol_constructor", acceso_proyectos=True)
        self.client.force_login(self.sup)

    def guardar(self, ids, sitio="S9"):
        return self.post("api_itos_guardar", {"empresa": "AJ", "sitio": sitio, "ids": ids})

    def test_candidatos_son_solo_ito_y_ito_hse(self):
        r = self.client.get(reverse("proyectos:api_itos"), {"empresa": "AJ", "sitio": "S9"})
        ids = {c["id"] for c in r.json()["candidatos"]}
        self.assertEqual(ids, {self.u.pk, self.ito2.pk})

    def test_asignar_da_acceso_solo_a_esos_sitios(self):
        self.assertEqual(self.guardar([self.ito2.pk]).status_code, 200)
        self.assertTrue(AccesoSitio.objects.filter(user=self.ito2, empresa="AJ", sitio="S9").exists())
        # El ITO asignado ve el sitio; no ve uno que no tiene.
        self.client.force_login(self.ito2)
        r = self.client.get(reverse("proyectos:api_habilitados"))
        self.assertEqual([p["sitio"] for p in r.json()["proyectos"]], ["S9"])
        r = self.client.get(reverse("proyectos:api_proyecto"), {"empresa": "AJ", "sitio": "S1"})
        self.assertEqual(r.status_code, 403)

    def test_desasignar_quita_acceso_y_no_toca_otros_roles(self):
        AccesoSitio.objects.create(user=self.constructor, empresa="AJ", sitio="S9")
        self.guardar([self.ito2.pk])
        self.guardar([])
        self.assertFalse(AccesoSitio.objects.filter(user=self.ito2, sitio="S9").exists())
        self.assertTrue(AccesoSitio.objects.filter(user=self.constructor, sitio="S9").exists())

    def test_varios_itos_y_no_candidatos_se_ignoran(self):
        self.guardar([self.u.pk, self.ito2.pk, self.constructor.pk, self.sup.pk])
        usuarios = set(AccesoSitio.objects.filter(sitio="S9").values_list("user_id", flat=True))
        self.assertEqual(usuarios, {self.u.pk, self.ito2.pk})

    def test_solo_superusuario_asigna(self):
        self.client.force_login(self.u)
        self.assertEqual(self.guardar([self.u.pk]).status_code, 403)
        r = self.client.get(reverse("proyectos:api_itos"), {"empresa": "AJ", "sitio": "S9"})
        self.assertEqual(r.status_code, 403)

    def test_el_sitio_muestra_sus_itos(self):
        self.guardar([self.ito2.pk])
        r = self.client.get(reverse("proyectos:api_proyecto"), {"empresa": "AJ", "sitio": "S9"})
        self.assertEqual([i["nombre"] for i in r.json()["itos"]], ["Beto"])


class ResponsableYEdicionTests(ProyectosBase):
    def setUp(self):
        super().setUp()
        self.e = self.proyecto().etapas.get(etapa="CON")

    def crear(self, **extra):
        body = {"etapa_id": self.e.pk, "titulo": "Visita", "fecha": "2026-10-20"}
        body.update(extra)
        return self.post("api_pendiente_crear", body)

    def test_responsable_usuario(self):
        self.crear(responsable_id=self.u.pk)
        p = Pendiente.objects.get()
        self.assertEqual(p.responsable_user, self.u)
        self.assertEqual(p.responsable, "ito")
        d = self.client.get(reverse("proyectos:api_proyecto"), {"empresa": "AJ", "sitio": "S1"}).json()
        pend = [x for e in d["etapas"] for x in e["pendientes"]][0]
        self.assertEqual(pend["responsable_id"], self.u.pk)
        self.assertIn({"id": self.u.pk, "nombre": "ito"}, d["responsables"])

    def test_responsable_texto_libre(self):
        self.crear(responsable="Contratista externo")
        p = Pendiente.objects.get()
        self.assertIsNone(p.responsable_user)
        self.assertEqual(p.responsable, "Contratista externo")

    def test_usuario_no_elegible_cae_a_texto(self):
        otro = User.objects.create_user("otro", password="x")
        UserProfile.objects.create(user=otro, rol="rol_ito")      # sin acceso al sitio
        self.crear(responsable_id=otro.pk, responsable="Pedro")
        p = Pendiente.objects.get()
        self.assertIsNone(p.responsable_user)
        self.assertEqual(p.responsable, "Pedro")

    def test_editar_y_sincroniza_calendario(self):
        self.crear()
        p = Pendiente.objects.get()
        with mock.patch.object(calendario, "habilitado", return_value=True), \
                mock.patch.object(calendario, "guardar_evento") as g:
            r = self.post("api_pendiente_editar", {
                "id": p.pk, "titulo": "Visita reprogramada", "fecha": "2026-10-22", "hora": "15:30",
                "prioridad": "A", "responsable_id": self.u.pk})
        self.assertEqual(r.status_code, 200)
        p.refresh_from_db()
        self.assertEqual((p.titulo, str(p.fecha), str(p.hora), p.prioridad),
                         ("Visita reprogramada", "2026-10-22", "15:30:00", "A"))
        self.assertEqual(p.responsable_user, self.u)
        g.assert_called_once()

    def test_editar_sin_fecha_quita_evento(self):
        self.crear()
        p = Pendiente.objects.get()
        Pendiente.objects.filter(pk=p.pk).update(en_calendario=True)
        with mock.patch.object(calendario, "habilitado", return_value=True), \
                mock.patch.object(calendario, "borrar_evento") as b:
            self.post("api_pendiente_editar", {"id": p.pk, "titulo": "Sin fecha", "fecha": ""})
        b.assert_called_once()
        p.refresh_from_db()
        self.assertFalse(p.en_calendario)

    def test_editar_exige_titulo_y_rol(self):
        self.crear()
        p = Pendiente.objects.get()
        self.assertEqual(self.post("api_pendiente_editar", {"id": p.pk, "titulo": " "}).status_code, 400)
        UserProfile.objects.filter(user=self.u).update(rol="visitante")
        self.assertEqual(self.post("api_pendiente_editar", {"id": p.pk, "titulo": "x"}).status_code, 403)

    def test_prioridad_alta_va_primero(self):
        self.crear(titulo="Normal", fecha="2026-10-15")
        self.crear(titulo="Urgente", fecha="2026-10-25", prioridad="A")
        d = self.client.get(reverse("proyectos:api_proyecto"), {"empresa": "AJ", "sitio": "S1"}).json()
        titulos = [x["titulo"] for e in d["etapas"] for x in e["pendientes"]]
        self.assertEqual(titulos[0], "Urgente")


class ActividadYPapeleraTests(ProyectosBase):
    def setUp(self):
        super().setUp()
        self.p = self.proyecto()
        self.e = self.p.etapas.get(etapa="CON")

    def actividad(self):
        r = self.client.get(reverse("proyectos:api_actividad"), {"empresa": "AJ", "sitio": "S1"})
        return [a["tipo"] for a in r.json()["actividad"]]

    def test_registra_los_movimientos(self):
        self.post("api_pendiente_crear", {"etapa_id": self.e.pk, "titulo": "X", "fecha": "2026-10-20"})
        pk = Pendiente.objects.get().pk
        self.post("api_pendiente_toggle", {"id": pk})
        self.post("api_nota_crear", {"etapa_id": self.e.pk, "texto": "hola"})
        self.post("api_pendiente_eliminar", {"id": pk})
        self.client.force_login(self.sup)       # el historial es solo del superusuario
        tipos = self.actividad()
        for esperado in ("pend_crear", "pend_hecho", "nota_crear", "pend_eliminar"):
            self.assertIn(esperado, tipos)
        self.assertEqual(tipos[0], "pend_eliminar")        # más reciente primero

    def test_estado_y_ubicacion_quedan_en_actividad(self):
        self.client.force_login(self.sup)
        self.post("api_proyecto_estado", {"empresa": "AJ", "sitio": "S1", "estado": "EJE"})
        self.post("api_proyecto_ubicacion", {"empresa": "AJ", "sitio": "S1", "lat": -33, "lon": -70})
        self.assertEqual(self.actividad()[:2], ["ubicacion", "estado"])

    def test_historial_solo_superusuario(self):
        for nombre in ("api_actividad", "api_papelera"):
            r = self.client.get(reverse("proyectos:" + nombre), {"empresa": "AJ", "sitio": "S1"})
            self.assertEqual(r.status_code, 403)

    def test_actividad_respeta_acceso_al_sitio(self):
        r = self.client.get(reverse("proyectos:api_actividad"), {"empresa": "AJ", "sitio": "OTRO"})
        self.assertEqual(r.status_code, 403)

    def test_papelera_y_restaurar_pendiente(self):
        self.post("api_pendiente_crear", {"etapa_id": self.e.pk, "titulo": "Borrame"})
        pk = Pendiente.objects.get().pk
        self.post("api_pendiente_eliminar", {"id": pk})
        self.client.force_login(self.sup)       # el historial es solo del superusuario
        r = self.client.get(reverse("proyectos:api_papelera"), {"empresa": "AJ", "sitio": "S1"})
        self.assertEqual([(i["tipo"], i["id"]) for i in r.json()["papelera"]], [("pendiente", pk)])
        self.assertEqual(self.post("api_restaurar", {"tipo": "pendiente", "id": pk}).status_code, 200)
        self.assertIsNone(Pendiente.objects.get(pk=pk).eliminado_en)
        r = self.client.get(reverse("proyectos:api_papelera"), {"empresa": "AJ", "sitio": "S1"})
        self.assertEqual(r.json()["papelera"], [])
        self.assertIn("pend_restaurar", self.actividad())

    def test_restaurar_nota_solo_autor_o_coordinador(self):
        n = Nota.objects.create(etapa=self.e, texto="de otro", usuario=self.sup,
                                eliminado_en=timezone.now())
        self.assertEqual(self.post("api_restaurar", {"tipo": "nota", "id": n.pk}).status_code, 403)
        mia = Nota.objects.create(etapa=self.e, texto="mía", usuario=self.u,
                                  eliminado_en=timezone.now())
        self.assertEqual(self.post("api_restaurar", {"tipo": "nota", "id": mia.pk}).status_code, 200)

    def test_restaurar_algo_no_eliminado_da_404(self):
        self.post("api_pendiente_crear", {"etapa_id": self.e.pk, "titulo": "Vivo"})
        pk = Pendiente.objects.get().pk
        self.assertEqual(self.post("api_restaurar", {"tipo": "pendiente", "id": pk}).status_code, 404)


class TableroTests(ProyectosBase):
    def test_pagina_exige_la_seccion(self):
        UserProfile.objects.filter(user=self.u).update(acceso_proyectos=False)
        self.assertEqual(self.client.get(reverse("proyectos:tablero")).status_code, 302)

    def test_resumen_por_sitio_y_acceso(self):
        a = self.proyecto("S1")
        self.proyecto("S2")                        # sin AccesoSitio para este usuario
        e = a.etapas.get(etapa="CON")
        hoy = timezone.localdate()
        Pendiente.objects.create(etapa=e, titulo="Vencido", fecha=hoy - timedelta(days=2))
        Pendiente.objects.create(etapa=e, titulo="Próximo", fecha=hoy + timedelta(days=3),
                                 prioridad="A")
        Pendiente.objects.create(etapa=e, titulo="Hecho", fecha=hoy, hecho=True)
        Pendiente.objects.create(etapa=e, titulo="Borrado", fecha=hoy, eliminado_en=timezone.now())
        Nota.objects.create(etapa=e, texto="última", usuario=self.u)
        r = self.client.get(reverse("proyectos:api_tablero"))
        self.assertEqual(r.status_code, 200)
        sitios = r.json()["sitios"]
        self.assertEqual([s["sitio"] for s in sitios], ["S1"])
        s = sitios[0]
        self.assertEqual((s["abiertos"], s["hechos"], s["vencidos"], s["altas"]), (2, 1, 1, 1))
        self.assertEqual(s["proximo"]["titulo"], "Vencido")          # el más antiguo pendiente
        self.assertEqual(s["ultima_nota"]["texto"], "última")

    def test_superusuario_ve_todos_y_los_urgentes_primero(self):
        a = self.proyecto("S1")
        self.proyecto("S2")
        Pendiente.objects.create(etapa=a.etapas.get(etapa="CON"), titulo="v",
                                 fecha=timezone.localdate() - timedelta(days=1))
        self.client.force_login(self.sup)
        sitios = self.client.get(reverse("proyectos:api_tablero")).json()["sitios"]
        self.assertEqual([s["sitio"] for s in sitios], ["S1", "S2"])


class RecordatoriosTests(ProyectosBase):
    def setUp(self):
        super().setUp()
        self.p = self.proyecto()
        self.e = self.p.etapas.get(etapa="CON")
        self.hoy = timezone.localdate()

    def correr(self, *args):
        from io import StringIO
        from django.core import mail
        mail.outbox.clear()
        call_command("enviar_recordatorios", *args, stdout=StringIO())
        return mail.outbox

    def test_avisa_a_los_ito_cuando_no_hay_responsable(self):
        self.u.email = "ito@x.cl"; self.u.save()
        Pendiente.objects.create(etapa=self.e, titulo="Vencido!", fecha=self.hoy - timedelta(days=1))
        Pendiente.objects.create(etapa=self.e, titulo="Lejano", fecha=self.hoy + timedelta(days=30))
        out = self.correr()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].to, ["ito@x.cl"])
        self.assertIn("Vencido!", out[0].body)
        self.assertNotIn("Lejano", out[0].body)
        self.assertIn("1 vencido", out[0].subject)

    def test_responsable_usuario_recibe_solo_lo_suyo(self):
        self.u.email = "ito@x.cl"; self.u.save()
        otro = User.objects.create_user("otro2", password="x", email="otro@x.cl")
        UserProfile.objects.create(user=otro, rol="rol_ito", acceso_proyectos=True)
        AccesoSitio.objects.create(user=otro, empresa="AJ", sitio="S1")
        Pendiente.objects.create(etapa=self.e, titulo="De otro", fecha=self.hoy,
                                 responsable_user=otro)
        out = self.correr()
        self.assertEqual([m.to for m in out], [["otro@x.cl"]])

    def test_ignora_hechos_eliminados_y_dry_run(self):
        self.u.email = "ito@x.cl"; self.u.save()
        Pendiente.objects.create(etapa=self.e, titulo="a", fecha=self.hoy, hecho=True)
        Pendiente.objects.create(etapa=self.e, titulo="b", fecha=self.hoy, eliminado_en=timezone.now())
        self.assertEqual(self.correr(), [])
        Pendiente.objects.create(etapa=self.e, titulo="c", fecha=self.hoy)
        self.assertEqual(self.correr("--dry-run"), [])
        self.assertEqual(len(self.correr()), 1)


class PanelToggleTests(ProyectosBase):
    def test_toggle_proyectos(self):
        self.client.force_login(self.sup)
        self.client.post(reverse("panel:usuario_toggle_acceso", args=[self.u.pk, "proyectos"]))
        self.u.profile.refresh_from_db()
        self.assertFalse(self.u.profile.acceso_proyectos)
