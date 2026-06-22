from django.urls import path
from . import views

app_name = 'docs'

urlpatterns = [
    path('', views.index, name='index'),
    path('final/', views.final, name='final'),
    path('seguimiento/', views.seguimiento_view, name='seguimiento'),
    path('api/seguimiento/', views.api_seguimiento, name='api_seguimiento'),
    path('api/seguimiento/subir/', views.subir_archivo, name='subir_archivo'),
    path('api/seguimiento/subir-multimedia/', views.subir_multimedia, name='subir_multimedia'),
    path('api/seguimiento/confirmar/', views.confirmar, name='confirmar'),
    path('api/seguimiento/observar/', views.observar, name='observar'),
    path('api/seguimiento/quitar-observacion/', views.quitar_observacion, name='quitar_observacion'),
    path('api/seguimiento/enmendar-observacion/', views.enmendar_observacion, name='enmendar_observacion'),
    path('api/seguimiento/archivo/', views.descargar_archivo, name='descargar_archivo'),
    path('api/seguimiento/eliminar/', views.eliminar_archivo, name='eliminar_archivo'),
    path('api/seguimiento/eliminar/aceptar/', views.aceptar_eliminacion, name='aceptar_eliminacion'),
    path('api/seguimiento/eliminar/rechazar/', views.rechazar_eliminacion, name='rechazar_eliminacion'),
    path('api/seguimiento/ocultar/', views.ocultar_archivo, name='ocultar_archivo'),
    path('api/seguimiento/restaurar/', views.restaurar_archivo, name='restaurar_archivo'),
    path('api/seguimiento/asignar/', views.asignar_archivo, name='asignar_archivo'),
    path('api/seguimiento/desasignar/', views.desasignar_archivo, name='desasignar_archivo'),
    path('api/seguimiento/necesario/', views.marcar_necesario, name='marcar_necesario'),
    path('template/<int:pk>/', views.descargar_template, name='descargar_template'),
    path('api/sitios/', views.api_sitios, name='api_sitios'),
    path('api/carpetas20/', views.api_carpetas20, name='api_carpetas20'),
    path('api/seguimiento/refrescar-carpeta/', views.refrescar_carpeta, name='refrescar_carpeta'),
    path('api/seguimiento/actualizar-estructura/', views.actualizar_estructura, name='actualizar_estructura'),
    path('api/carpetas/', views.api_carpetas, name='api_carpetas'),
    path('api/carpetas/archivos/', views.api_carpetas_archivos, name='api_carpetas_archivos'),
    path('api/final/tree/', views.api_final_tree, name='api_final_tree'),
    path('api/final/archivos/', views.api_final_archivos, name='api_final_archivos'),
]
