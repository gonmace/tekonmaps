from django.urls import path
from . import views
from .views import buscar_sitio

urlpatterns = [
    path('', views.Home.as_view(), name='Home'),
    path('buscar_sitio/', buscar_sitio, name='buscar_sitio'),
]