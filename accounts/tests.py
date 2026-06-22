from unittest import mock

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from docs import company_loader, seguimiento, views as docs_views
from docs.company_loader import Company
from docs.models import AccesoSitio, UserProfile

# En tests no se corre collectstatic, así que el manifest de WhiteNoise no existe.
# Usamos un storage simple para poder renderizar plantillas con {% static %}.
_PLAIN_STATIC = override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})


@_PLAIN_STATIC
class LoginFlowTests(TestCase):
    """Flujo de login por correo + creación de contraseña en el primer ingreso."""

    def setUp(self):
        self.client = Client()
        self.u = User.objects.create_user(username="ana@x.cl", email="ana@x.cl")
        self.u.first_name = "Ana Pérez"
        self.u.set_unusable_password()
        self.u.save()
        UserProfile.objects.create(user=self.u, rol="rol_ito", acceso_contratista=True)

    def test_correo_desconocido_no_autoregistra(self):
        r = self.client.post(reverse("accounts:login"),
                             {"correo": "nadie@x.cl", "password": ""})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "No existe una cuenta")
        self.assertEqual(User.objects.count(), 1)

    def test_primer_ingreso_redirige_a_crear_password(self):
        r = self.client.post(reverse("accounts:login"),
                             {"correo": "ana@x.cl", "password": ""})
        self.assertRedirects(r, reverse("accounts:crear_password"))

    def test_crear_password_y_login_posterior(self):
        # Paso 1: correo → set session
        self.client.post(reverse("accounts:login"),
                        {"correo": "ana@x.cl", "password": ""})
        # Paso 2: crear contraseña
        r = self.client.post(reverse("accounts:crear_password"),
                            {"password1": "Sup3rClave!", "password2": "Sup3rClave!"})
        self.assertRedirects(r, reverse("docs:index"), fetch_redirect_response=False)
        self.u.refresh_from_db()
        self.assertTrue(self.u.has_usable_password())
        # Login posterior: correo + contraseña en una sola pantalla
        self.client.logout()
        r2 = self.client.post(reverse("accounts:login"),
                             {"correo": "ana@x.cl", "password": "Sup3rClave!"})
        self.assertRedirects(r2, reverse("docs:index"), fetch_redirect_response=False)

    def test_password_no_coincide(self):
        self.client.post(reverse("accounts:login"),
                        {"correo": "ana@x.cl", "password": ""})
        r = self.client.post(reverse("accounts:crear_password"),
                            {"password1": "Sup3rClave!", "password2": "otra"})
        self.assertContains(r, "no coinciden")

    def test_crear_password_sin_sesion_redirige_login(self):
        r = self.client.get(reverse("accounts:crear_password"))
        self.assertRedirects(r, reverse("accounts:login"))

    def test_usuario_inactivo_no_ingresa(self):
        self.u.is_active = False
        self.u.save()
        r = self.client.post(reverse("accounts:login"),
                            {"correo": "ana@x.cl", "password": ""})
        self.assertContains(r, "deshabilitada")


@_PLAIN_STATIC
class AccesoSitioEnforcementTests(TestCase):
    """api_sitios filtra por AccesoSitio; api_seguimiento devuelve 403 sin acceso."""

    def setUp(self):
        self.client = Client()
        self.u = User.objects.create_user(username="ito@x.cl", email="ito@x.cl",
                                          password="x")
        # Acceso a las secciones concedido: estos tests se centran en AccesoSitio.
        UserProfile.objects.create(user=self.u, rol="rol_ito",
                                   acceso_contratista=True, acceso_seguimiento=True)
        self.emp = Company(nombre="AJ", carpeta_nextcloud="20 AJ")

    def _items(self):
        return [
            {"path": "/20 AJ/Sitio Uno", "type": "folder"},
            {"path": "/20 AJ/Sitio Dos", "type": "folder"},
        ]

    def test_api_sitios_filtra_por_acceso(self):
        AccesoSitio.objects.create(user=self.u, empresa="AJ", sitio="Sitio Uno")
        self.client.force_login(self.u)
        with mock.patch.object(company_loader, "get_by_nombre", return_value=self.emp), \
             mock.patch.object(docs_views, "_fetch_items", return_value=self._items()):
            r = self.client.get(reverse("docs:api_sitios"), {"empresa": "AJ"})
        self.assertEqual(r.json()["sitios"], ["Sitio Uno"])

    def test_api_sitios_sin_acceso_vacio(self):
        self.client.force_login(self.u)
        with mock.patch.object(company_loader, "get_by_nombre", return_value=self.emp), \
             mock.patch.object(docs_views, "_fetch_items", return_value=self._items()):
            r = self.client.get(reverse("docs:api_sitios"), {"empresa": "AJ"})
        self.assertEqual(r.json()["sitios"], [])

    def test_superuser_ve_todos(self):
        su = User.objects.create_superuser(username="su", email="su@x.cl", password="x")
        self.client.force_login(su)
        with mock.patch.object(company_loader, "get_by_nombre", return_value=self.emp), \
             mock.patch.object(docs_views, "_fetch_items", return_value=self._items()):
            r = self.client.get(reverse("docs:api_sitios"), {"empresa": "AJ"})
        self.assertEqual(r.json()["sitios"], ["Sitio Dos", "Sitio Uno"])

    def test_api_sitios_generados_filtra_area_ito(self):
        su = User.objects.create_superuser(username="su", email="su@x.cl", password="x")
        self.client.force_login(su)
        with mock.patch.object(company_loader, "get_by_nombre", return_value=self.emp), \
             mock.patch.object(docs_views, "_fetch_items", return_value=self._items()), \
             mock.patch.object(seguimiento, "sitios_generados", return_value={"Sitio Uno"}):
            r = self.client.get(reverse("docs:api_sitios"),
                              {"empresa": "AJ", "generados": "1"})
        self.assertEqual(r.json()["sitios"], ["Sitio Uno"])

    def test_api_seguimiento_403_sin_acceso(self):
        self.client.force_login(self.u)
        r = self.client.get(reverse("docs:api_seguimiento"),
                           {"empresa": "AJ", "sitio": "Sitio Uno"})
        self.assertEqual(r.status_code, 403)


@_PLAIN_STATIC
class AccesoSeccionTests(TestCase):
    """Acceso por sección del navbar (acceso_contratista/finales/seguimiento)."""

    def setUp(self):
        self.client = Client()
        self.u = User.objects.create_user(username="u@x.cl", email="u@x.cl", password="x")
        self.profile = UserProfile.objects.create(user=self.u, rol="visitante")

    def test_sin_acceso_pagina_redirige_a_home(self):
        self.client.force_login(self.u)
        for name in ("docs:index", "docs:final", "docs:seguimiento"):
            r = self.client.get(reverse(name))
            self.assertRedirects(r, reverse("home"), fetch_redirect_response=False)

    def test_con_acceso_finales_entra(self):
        self.profile.acceso_finales = True
        self.profile.save()
        self.client.force_login(self.u)
        self.assertEqual(self.client.get(reverse("docs:final")).status_code, 200)
        # Las otras secciones redirigen a la primera permitida (Finales), no 403.
        r = self.client.get(reverse("docs:index"))
        self.assertRedirects(r, reverse("docs:final"), fetch_redirect_response=False)

    def test_api_finales_gated(self):
        self.client.force_login(self.u)
        self.assertEqual(self.client.get(reverse("docs:api_final_tree")).status_code, 403)
        self.profile.acceso_finales = True
        self.profile.save()
        # Con acceso ya no es 403 (mockeo el árbol para no tocar Nextcloud).
        with mock.patch.object(docs_views, "_build_tree", return_value=[]):
            self.assertEqual(self.client.get(reverse("docs:api_final_tree")).status_code, 200)

    def test_superuser_entra_a_todo(self):
        su = User.objects.create_superuser(username="su", email="su@x.cl", password="x")
        self.client.force_login(su)
        with mock.patch.object(docs_views, "_build_tree", return_value=[]):
            self.assertEqual(self.client.get(reverse("docs:final")).status_code, 200)

    def test_toggle_acceso_panel(self):
        su = User.objects.create_superuser(username="su2", email="su2@x.cl", password="x")
        self.client.force_login(su)
        r = self.client.post(reverse("panel:usuario_toggle_acceso",
                                   args=[self.u.pk, "seguimiento"]))
        self.assertRedirects(r, reverse("panel:usuarios"))
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.acceso_seguimiento)


@_PLAIN_STATIC
class PanelUsuariosTests(TestCase):
    """Alta simplificada y toggle de estado en el panel."""

    def setUp(self):
        self.client = Client()
        self.su = User.objects.create_superuser(username="su", email="su@x.cl",
                                               password="x")
        self.client.force_login(self.su)

    def test_alta_crea_usuario_sin_password(self):
        r = self.client.post(reverse("panel:usuario_crear"), {
            "full_name": "Beto Soto", "email": "beto@x.cl", "rol": "rol_ito"})
        self.assertRedirects(r, reverse("panel:usuarios"))
        u = User.objects.get(email="beto@x.cl")
        self.assertEqual(u.username, "beto@x.cl")
        self.assertEqual(u.first_name, "Beto Soto")
        self.assertFalse(u.has_usable_password())
        self.assertEqual(u.profile.rol, "rol_ito")
        # Por defecto el usuario nuevo accede a Seguimiento; no a Contratista/Finales.
        self.assertTrue(u.profile.acceso_seguimiento)
        self.assertFalse(u.profile.acceso_contratista)
        self.assertFalse(u.profile.acceso_finales)

    def test_toggle_activo(self):
        u = User.objects.create_user(username="c@x.cl", email="c@x.cl", password="x")
        self.assertTrue(u.is_active)
        r = self.client.post(reverse("panel:usuario_toggle_activo", args=[u.pk]))
        self.assertRedirects(r, reverse("panel:usuarios"))
        u.refresh_from_db()
        self.assertFalse(u.is_active)

    def test_toggle_protege_superuser(self):
        otro_su = User.objects.create_superuser(username="su2", email="su2@x.cl",
                                              password="x")
        self.client.post(reverse("panel:usuario_toggle_activo", args=[otro_su.pk]))
        otro_su.refresh_from_db()
        self.assertTrue(otro_su.is_active)

    def test_guardar_sitios_sincroniza(self):
        u = User.objects.create_user(username="d@x.cl", email="d@x.cl", password="x")
        AccesoSitio.objects.create(user=u, empresa="AJ", sitio="Viejo")
        self.client.post(reverse("panel:usuario_sitios_guardar", args=[u.pk]), {
            "empresa": "AJ", "sitio": ["Sitio Uno", "Sitio Dos"]})
        sitios = set(u.sitios_permitidos.filter(empresa="AJ")
                     .values_list("sitio", flat=True))
        self.assertEqual(sitios, {"Sitio Uno", "Sitio Dos"})

    def test_paginas_accesos_renderizan(self):
        u = User.objects.create_user(username="e@x.cl", email="e@x.cl", password="x")
        r1 = self.client.get(reverse("panel:accesos"))
        self.assertEqual(r1.status_code, 200)
        r2 = self.client.get(reverse("panel:usuario_sitios", args=[u.pk]))
        self.assertEqual(r2.status_code, 200)

    def test_usuarios_y_form_renderizan(self):
        self.assertEqual(self.client.get(reverse("panel:usuarios")).status_code, 200)
        self.assertEqual(self.client.get(reverse("panel:usuario_crear")).status_code, 200)

    def test_panel_requiere_superuser(self):
        self.client.logout()
        normal = User.objects.create_user(username="n@x.cl", email="n@x.cl",
                                         password="x")
        self.client.force_login(normal)
        r = self.client.get(reverse("panel:usuarios"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("accounts:login"), r.url)
