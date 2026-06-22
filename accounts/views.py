from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

# Clave de sesión donde se guarda el usuario que está creando su contraseña
# por primera vez (flujo de primer ingreso).
PWD_SETUP_SESSION_KEY = "pwd_setup_uid"


def _landing(user):
    """Primera sección del navbar a la que el usuario tiene acceso, o 'home' si ninguna."""
    if user.is_superuser:
        return reverse("docs:index")
    p = getattr(user, "profile", None)
    if p and p.acceso_contratista:
        return reverse("docs:index")
    if p and p.acceso_finales:
        return reverse("docs:final")
    if p and p.acceso_seguimiento:
        return reverse("docs:seguimiento")
    return reverse("home")


def _destino_seguro(request, next_url):
    """Devuelve next_url si es una ruta local segura; si no, la primera sección permitida."""
    if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()},
            require_https=request.is_secure()):
        return next_url
    return _landing(request.user)


def _buscar_usuario(correo):
    """Busca un usuario por correo (o username, para el superusuario heredado)."""
    correo = (correo or "").strip()
    if not correo:
        return None
    return User.objects.filter(
        Q(email__iexact=correo) | Q(username__iexact=correo)).first()


def login_view(request):
    """Login combinado (correo + contraseña).

    - Si el correo corresponde a una cuenta sin contraseña usable (recién creada
      por el superusuario), redirige a la pantalla de creación de contraseña.
    - Si la cuenta ya tiene contraseña, autentica con la contraseña ingresada.
    No existe auto-registro: un correo desconocido devuelve error.
    """
    if request.user.is_authenticated:
        return redirect(_landing(request.user))

    next_url = request.POST.get("next") or request.GET.get("next") or ""
    context = {"next": next_url, "correo": ""}

    if request.method == "POST":
        correo = (request.POST.get("correo") or "").strip()
        password = request.POST.get("password") or ""
        context["correo"] = correo
        user = _buscar_usuario(correo)

        if user is None:
            context["error"] = ("No existe una cuenta con ese correo. "
                                 "Contacta al administrador.")
        elif not user.is_active:
            context["error"] = "Tu cuenta está deshabilitada. Contacta al administrador."
        elif not user.has_usable_password():
            # Primer ingreso: derivar a creación de contraseña.
            request.session[PWD_SETUP_SESSION_KEY] = user.pk
            destino = reverse("accounts:crear_password")
            if next_url:
                destino = f"{destino}?next={next_url}"
            return redirect(destino)
        elif not password:
            context["error"] = "Ingresa tu contraseña."
        else:
            auth_user = authenticate(
                request, username=user.username, password=password)
            if auth_user is not None:
                login(request, auth_user)
                return redirect(_destino_seguro(request, next_url))
            context["error"] = "Correo o contraseña incorrectos."

    return render(request, "accounts/login.html", context)


def crear_password_view(request):
    """Creación de contraseña en el primer ingreso.

    Solo accesible si la sesión apunta a un usuario sin contraseña usable.
    """
    uid = request.session.get(PWD_SETUP_SESSION_KEY)
    user = User.objects.filter(pk=uid).first() if uid else None
    if user is None or user.has_usable_password() or not user.is_active:
        request.session.pop(PWD_SETUP_SESSION_KEY, None)
        return redirect("accounts:login")

    next_url = request.POST.get("next") or request.GET.get("next") or ""
    context = {"next": next_url, "correo": user.email or user.username}

    if request.method == "POST":
        p1 = request.POST.get("password1") or ""
        p2 = request.POST.get("password2") or ""
        if p1 != p2:
            context["error"] = "Las contraseñas no coinciden."
        else:
            try:
                validate_password(p1, user)
            except ValidationError as exc:
                context["error"] = " ".join(exc.messages)
            else:
                user.set_password(p1)
                user.save()
                request.session.pop(PWD_SETUP_SESSION_KEY, None)
                login(request, user,
                      backend="django.contrib.auth.backends.ModelBackend")
                return redirect(_destino_seguro(request, next_url))

    return render(request, "accounts/crear_password.html", context)


def logout_view(request):
    """Cierra sesión y redirige al root."""
    logout(request)
    return redirect("home")
