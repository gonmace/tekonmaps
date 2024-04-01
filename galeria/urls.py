from django.urls import path
from . import views
from .views import GaleriaListView, galeria_detalle, UltimasImagenes, CustomLoginView

app_name = 'galeria'

urlpatterns = [
    path('', GaleriaListView.as_view(), name='galeria_list'),
    path('cargar/login/', CustomLoginView.as_view(), name='login'),
    path('cargar/', views.fileupload, name='cargar_imagenes'),
    path('<slug:slug>/', galeria_detalle, name='galeria_detalle'),
    path('api/<slug:slug_sitio>/', UltimasImagenes.as_view(), name='ultimas_imagenes'),




    # path('cargar/<int:pk>/', views.cargar_imagenes, name='cargar_imagenes'),
    # path('galeria/<int:pk>/cargar/', views.cargar_imagenes, name='cargar_imagenes'),
    # Añade más rutas según necesites
]
