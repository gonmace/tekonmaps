from django.urls import path

from . import views

app_name = "proyectos"

urlpatterns = [
    path("", views.index, name="index"),
    path("api/proyecto/", views.api_proyecto, name="api_proyecto"),
    path("api/proyecto/estado/", views.api_proyecto_estado, name="api_proyecto_estado"),
    path("api/proyecto/ubicacion/", views.api_proyecto_ubicacion, name="api_proyecto_ubicacion"),
    path("api/habilitados/", views.api_habilitados, name="api_habilitados"),
    path("api/proyecto/habilitar/", views.api_proyecto_habilitar, name="api_proyecto_habilitar"),
    path("api/archivos/", views.api_archivos, name="api_archivos"),
    path("archivo/", views.archivo_ver, name="archivo_ver"),
    path("api/imagenes/", views.api_imagenes, name="api_imagenes"),
    path("miniatura/", views.miniatura, name="miniatura"),
    path("api/itos/", views.api_itos, name="api_itos"),
    path("api/itos/guardar/", views.api_itos_guardar, name="api_itos_guardar"),
    path("api/mapa/", views.api_mapa, name="api_mapa"),
    path("api/etapa/estado/", views.api_etapa_estado, name="api_etapa_estado"),
    path("api/pendiente/crear/", views.api_pendiente_crear, name="api_pendiente_crear"),
    path("tablero/", views.tablero, name="tablero"),
    path("api/tablero/", views.api_tablero, name="api_tablero"),
    path("api/actividad/", views.api_actividad, name="api_actividad"),
    path("api/papelera/", views.api_papelera, name="api_papelera"),
    path("api/restaurar/", views.api_restaurar, name="api_restaurar"),
    path("api/pendiente/editar/", views.api_pendiente_editar, name="api_pendiente_editar"),
    path("api/pendiente/toggle/", views.api_pendiente_toggle, name="api_pendiente_toggle"),
    path("api/pendiente/eliminar/", views.api_pendiente_eliminar, name="api_pendiente_eliminar"),
    path("api/nota/crear/", views.api_nota_crear, name="api_nota_crear"),
    path("api/nota/eliminar/", views.api_nota_eliminar, name="api_nota_eliminar"),
    path("api/imagen/subir/", views.api_imagen_subir, name="api_imagen_subir"),
    path("api/imagen/eliminar/", views.api_imagen_eliminar, name="api_imagen_eliminar"),
    path("imagen/<int:pk>/", views.imagen_ver, name="imagen_ver"),
]
