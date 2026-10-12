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
                             {"correo": "nadie@x.cl", "password": "loquesea"})
        self.assertEqual(r.status_code, 200)
        # Mensaje genérico (anti-enumeración): no revela si el correo existe.
        self.assertContains(r, "Correo o contraseña incorrectos")
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
                                   args=[self.u.pk, "proyectos"]))
        self.assertRedirects(r, reverse("panel:usuarios"))
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.acceso_proyectos)
        # «Seguimiento old» ya no se asigna desde el Panel.
        self.client.post(reverse("panel:usuario_toggle_acceso", args=[self.u.pk, "seguimiento"]))
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.acceso_seguimiento)

    def test_seguimiento_old_solo_superusuario(self):
        """Aunque el perfil tenga el flag, el tablero viejo no es accesible; el superusuario sí."""
        self.profile.acceso_seguimiento = True
        self.profile.acceso_proyectos = True
        self.profile.save()
        self.client.force_login(self.u)
        r = self.client.get(reverse("docs:seguimiento"))
        self.assertRedirects(r, reverse("proyectos:index"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("docs:api_seguimiento"),
                                         {"empresa": "AJ", "sitio": "S"}).status_code, 403)
        # Escrituras del tablero (antes solo exigían un rol ITO): también 403.
        self.profile.rol = "rol_coordinador"
        self.profile.save()
        r = self.client.post(reverse("docs:confirmar"), data="{}", content_type="application/json")
        self.assertEqual(r.status_code, 403)
        # El enlace no aparece en el menú.
        html = self.client.get(reverse("proyectos:index")).content.decode()
        self.assertNotIn(reverse("docs:seguimiento"), html)
        su = User.objects.create_superuser(username="su3", email="su3@x.cl", password="x")
        self.client.force_login(su)
        html = self.client.get(reverse("proyectos:index")).content.decode()
        self.assertIn(reverse("docs:seguimiento"), html)


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
        u = User.objects.get(email="beto@x.cl")
        # Rol que no ve todo: tras crear se abre su pantalla de sitios.
        self.assertRedirects(r, reverse("panel:usuario_sitios", args=[u.pk]),
                             fetch_redirect_response=False)
        self.assertEqual(u.username, "beto@x.cl")
        self.assertEqual(u.first_name, "Beto Soto")
        self.assertFalse(u.has_usable_password())
        self.assertEqual(u.profile.rol, "rol_ito")
        # Sin marcar nada en el formulario: no hay acceso a ninguna sección, y el tablero
        # viejo nunca se asigna.
        self.assertFalse(u.profile.acceso_proyectos)
        self.assertFalse(u.profile.acceso_contratista)
        self.assertFalse(u.profile.acceso_finales)
        self.assertFalse(u.profile.acceso_seguimiento)

    def test_alta_envia_correo_de_ingreso_por_defecto(self):
        from django.core import mail
        self.client.post(reverse("panel:usuario_crear"), {
            "full_name": "Ana", "email": "ana2@x.cl", "rol": "rol_coordinador"})
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        self.assertEqual(m.to, ["ana2@x.cl"])
        self.assertIn(reverse("accounts:login"), m.body)
        self.assertFalse(User.objects.get(email="ana2@x.cl").has_usable_password())

    def test_alta_con_contraseña_directa_no_envia_correo(self):
        from django.core import mail
        self.client.post(reverse("panel:usuario_crear"), {
            "full_name": "Pedro", "email": "pedro@x.cl", "rol": "rol_coordinador",
            "modo_acceso": "password", "password": "Clave-segura-2026"})
        u = User.objects.get(email="pedro@x.cl")
        self.assertTrue(u.check_password("Clave-segura-2026"))
        self.assertEqual(len(mail.outbox), 0)

    def test_alta_con_contraseña_exige_un_valor_valido(self):
        for pwd in ("", "123"):
            r = self.client.post(reverse("panel:usuario_crear"), {
                "full_name": "Luis", "email": "luis@x.cl", "rol": "rol_coordinador",
                "modo_acceso": "password", "password": pwd})
            self.assertEqual(r.status_code, 200)   # vuelve al formulario con error
        self.assertFalse(User.objects.filter(email="luis@x.cl").exists())

    def test_correo_con_fallo_no_impide_crear(self):
        with mock.patch("django.core.mail.send_mail", side_effect=OSError("smtp")):
            r = self.client.post(reverse("panel:usuario_crear"), {
                "full_name": "Eva", "email": "eva@x.cl", "rol": "rol_coordinador"})
        self.assertRedirects(r, reverse("panel:usuarios"))
        self.assertTrue(User.objects.filter(email="eva@x.cl").exists())

    def test_reenviar_invitacion_solo_si_sin_contraseña(self):
        from django.core import mail
        sin = User.objects.create_user(username="s@x.cl", email="s@x.cl")
        sin.set_unusable_password(); sin.save()
        con = User.objects.create_user(username="c2@x.cl", email="c2@x.cl", password="x")
        self.client.post(reverse("panel:usuario_invitar", args=[sin.pk]))
        self.assertEqual(len(mail.outbox), 1)
        self.client.post(reverse("panel:usuario_invitar", args=[con.pk]))
        self.assertEqual(len(mail.outbox), 1)

    def test_formulario_de_alta_solo_seguimiento_marcado_por_defecto(self):
        r = self.client.get(reverse("panel:usuario_crear"))
        form = r.context["form"]
        self.assertTrue(form["acceso_proyectos"].value())
        self.assertFalse(form["acceso_contratista"].value())
        self.assertFalse(form["acceso_finales"].value())

    def test_alta_con_privilegios_y_va_a_sitios(self):
        r = self.client.post(reverse("panel:usuario_crear"), {
            "full_name": "Ana", "email": "ana@x.cl", "rol": "rol_ito",
            "acceso_contratista": "on", "acceso_proyectos": "on"})
        u = User.objects.get(email="ana@x.cl")
        self.assertRedirects(r, reverse("panel:usuario_sitios", args=[u.pk]),
                             fetch_redirect_response=False)
        self.assertTrue(u.profile.acceso_contratista)
        self.assertTrue(u.profile.acceso_proyectos)
        self.assertFalse(u.profile.acceso_finales)

    def test_rol_que_ve_todo_no_pasa_por_sitios(self):
        r = self.client.post(reverse("panel:usuario_crear"), {
            "full_name": "Coo", "email": "coo2@x.cl", "rol": "rol_coordinador",
            "acceso_proyectos": "on"})
        self.assertRedirects(r, reverse("panel:usuarios"))

    def test_editar_actualiza_privilegios(self):
        u = User.objects.create_user(username="e@x.cl", email="e@x.cl", password="x")
        UserProfile.objects.create(user=u, rol="visitante", acceso_contratista=True)
        r = self.client.post(reverse("panel:usuario_editar", args=[u.pk]), {
            "full_name": "E", "email": "e@x.cl", "rol": "visitante", "is_active": "on",
            "acceso_finales": "on"})
        self.assertRedirects(r, reverse("panel:usuarios"))
        u.profile.refresh_from_db()
        self.assertFalse(u.profile.acceso_contratista)
        self.assertTrue(u.profile.acceso_finales)

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


@_PLAIN_STATIC
class ImpersonacionTests(TestCase):
    """Impersonación por sesión (middleware): el superusuario ve la app como otro
    usuario; sin login(), la sesión real no cambia."""

    def setUp(self):
        self.su = User.objects.create_superuser("root@x.cl", "root@x.cl", "x")
        self.otro_su = User.objects.create_superuser("root2@x.cl", "root2@x.cl", "x")
        self.target = User.objects.create_user(
            username="obj@x.cl", email="obj@x.cl", password="x")
        UserProfile.objects.create(user=self.target, rol="visitante",
                                   acceso_seguimiento=True)
        self.client = Client()
        self.client.force_login(self.su)

    def _impersonar(self, user):
        return self.client.post(reverse("panel:usuario_impersonar", args=[user.pk]))

    def test_impersonar_intercambia_el_usuario_y_muestra_banner(self):
        r = self._impersonar(self.target)
        self.assertEqual(r.status_code, 302)  # a la landing del objetivo
        r = self.client.get(reverse("home"))
        self.assertEqual(r.context["user"], self.target)
        self.assertContains(r, "Viendo como")
        self.assertContains(r, "Volver a mi cuenta")
        # El Panel queda gateado como el objetivo (no superuser) → redirect a login.
        r = self.client.get(reverse("panel:usuarios"))
        self.assertEqual(r.status_code, 302)

    def test_volver_restaura_al_superusuario(self):
        self._impersonar(self.target)
        r = self.client.post(reverse("accounts:volver"))
        self.assertEqual(r.status_code, 302)
        r = self.client.get(reverse("home"))
        self.assertEqual(r.context["user"], self.su)
        self.assertNotContains(r, "Viendo como")

    def test_no_se_puede_impersonar_a_un_superusuario(self):
        self._impersonar(self.otro_su)
        r = self.client.get(reverse("home"))
        self.assertEqual(r.context["user"], self.su)

    def test_usuario_normal_no_puede_impersonar(self):
        normal = User.objects.create_user(username="n2@x.cl", password="x")
        self.client.force_login(normal)
        r = self._impersonar(self.target)
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("accounts:login"), r.url)
        # Ni siquiera inyectando la clave a mano: el middleware exige superuser real.
        session = self.client.session
        session["impersonar_uid"] = self.target.pk
        session.save()
        r = self.client.get(reverse("home"))
        self.assertEqual(r.context["user"], normal)

    def test_objetivo_desactivado_se_autolimpia(self):
        self._impersonar(self.target)
        self.target.is_active = False
        self.target.save(update_fields=["is_active"])
        r = self.client.get(reverse("home"))
        self.assertEqual(r.context["user"], self.su)


@_PLAIN_STATIC
@override_settings(SEGUIMIENTO_OLD_SOLO_SUPERUSER=False)  # prueban la lógica de sincronización por rol
class SitioSincronizadoTests(TestCase):
    """Solo el superusuario inicia la sincronización de un sitio nuevo en Seguimiento;
    los demás roles solo acceden/ven sitios ya sincronizados (SitioSincronizado)."""

    def setUp(self):
        from docs.models import SitioSincronizado  # noqa: F401 (modelo bajo prueba)
        self.client = Client()
        self.su = User.objects.create_superuser("su@x.cl", "su@x.cl", "x")
        self.coord = User.objects.create_user(username="coo@x.cl", password="x")
        UserProfile.objects.create(user=self.coord, rol="rol_coordinador",
                                   acceso_seguimiento=True)  # ve todos los sitios (rol transversal)
        self.emp = Company(nombre="AJ", carpeta_nextcloud="20 AJ")
        self._estado = {"sitio": "Sitio Uno", "empresa": "AJ", "documentos": [],
                        "agregados": {}, "inesperados": [], "total": 0, "presentes": 0,
                        "error": ""}

    def _items(self):
        return [
            {"path": "/20 AJ/Sitio Uno", "type": "folder"},
            {"path": "/20 AJ/Sitio Dos", "type": "folder"},
        ]

    def test_no_superuser_403_en_sitio_no_sincronizado(self):
        self.client.force_login(self.coord)
        with mock.patch.object(seguimiento, "estado_sitio") as scan:
            r = self.client.get(reverse("docs:api_seguimiento"),
                                {"empresa": "AJ", "sitio": "Sitio Uno"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("sincronizado", r.json()["error"])
        scan.assert_not_called()  # ni siquiera dispara el escaneo

    def test_superuser_primera_carga_registra_la_sincronizacion(self):
        from docs.models import SitioSincronizado
        self.client.force_login(self.su)
        with mock.patch.object(seguimiento, "estado_sitio", return_value=self._estado):
            r = self.client.get(reverse("docs:api_seguimiento"),
                                {"empresa": "AJ", "sitio": "Sitio Uno"})
        self.assertEqual(r.status_code, 200)
        marca = SitioSincronizado.objects.get(empresa="AJ", sitio="Sitio Uno")
        self.assertEqual(marca.usuario, self.su)
        # Y desde entonces el resto puede cargarlo.
        self.client.force_login(self.coord)
        with mock.patch.object(seguimiento, "estado_sitio", return_value=self._estado):
            r = self.client.get(reverse("docs:api_seguimiento"),
                                {"empresa": "AJ", "sitio": "Sitio Uno"})
        self.assertEqual(r.status_code, 200)

    def test_carga_fallida_no_registra(self):
        from docs.models import SitioSincronizado
        self.client.force_login(self.su)
        fallido = dict(self._estado, error="Nextcloud no responde")
        with mock.patch.object(seguimiento, "estado_sitio", return_value=fallido):
            self.client.get(reverse("docs:api_seguimiento"),
                            {"empresa": "AJ", "sitio": "Sitio Uno"})
        self.assertFalse(SitioSincronizado.objects.exists())

    def test_api_sitios_sinc_filtra_solo_a_no_superusers(self):
        from docs.models import SitioSincronizado
        SitioSincronizado.objects.create(empresa="AJ", sitio="Sitio Uno")
        # No-superuser (rol transversal, sin restricción AccesoSitio): solo sincronizados.
        self.client.force_login(self.coord)
        with mock.patch.object(company_loader, "get_by_nombre", return_value=self.emp), \
             mock.patch.object(docs_views, "_fetch_items", return_value=self._items()):
            r = self.client.get(reverse("docs:api_sitios"), {"empresa": "AJ", "sinc": "1"})
        self.assertEqual(r.json()["sitios"], ["Sitio Uno"])
        # Superuser: ve todos (puede iniciar la sincronización de "Sitio Dos").
        self.client.force_login(self.su)
        with mock.patch.object(company_loader, "get_by_nombre", return_value=self.emp), \
             mock.patch.object(docs_views, "_fetch_items", return_value=self._items()):
            r = self.client.get(reverse("docs:api_sitios"), {"empresa": "AJ", "sinc": "1"})
        self.assertEqual(r.json()["sitios"], ["Sitio Dos", "Sitio Uno"])
