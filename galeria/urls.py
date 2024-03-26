from django.urls import path
from . import views
from .views import GaleriaListView, galeria_detalle

app_name = 'galeria'

urlpatterns = [
    path('', GaleriaListView.as_view(), name='galeria_list'),
    path('cargar/', views.fileupload, name='cargar_imagenes'),
    path('<slug:slug>/', galeria_detalle, name='galeria_detalle'),


    # path('cargar/<int:pk>/', views.cargar_imagenes, name='cargar_imagenes'),
    # path('galeria/<int:pk>/cargar/', views.cargar_imagenes, name='cargar_imagenes'),
    # Añade más rutas según necesites
]
