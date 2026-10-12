"""Impersonación de usuarios (solo superusuario).

El superusuario inicia la impersonación desde el Panel (Usuarios); se guarda el id
del usuario objetivo en la sesión y este middleware intercambia ``request.user`` en
cada request. No hay ``login()``: la sesión autenticada sigue siendo la del
superusuario (django-axes y ``last_login`` del objetivo no se tocan), por lo que
toda la app —roles, secciones, accesos por sitio, gate del Panel— se comporta
exactamente como la ve el usuario impersonado. El usuario real queda disponible en
``request.usuario_real`` (el banner de ``header.html`` lo usa para ofrecer "Volver").
"""
from django.contrib.auth.models import User

IMPERSONATE_SESSION_KEY = "impersonar_uid"


class ImpersonateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        uid = request.session.get(IMPERSONATE_SESSION_KEY)
        if uid and request.user.is_authenticated and request.user.is_superuser:
            target = User.objects.filter(
                pk=uid, is_active=True, is_superuser=False).first()
            if target is not None:
                request.usuario_real = request.user
                request.user = target
            else:  # objetivo borrado/desactivado/promovido → autolimpieza
                request.session.pop(IMPERSONATE_SESSION_KEY, None)
        return self.get_response(request)
