from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect
from django.urls import reverse_lazy


class CustomLoginView(LoginView):
    """Vista de login con el mismo aspecto que el resto del sitio."""
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True
    success_url = reverse_lazy('docs:index')


def logout_view(request):
    """Cierra sesión y redirige al root."""
    logout(request)
    return redirect('home')
