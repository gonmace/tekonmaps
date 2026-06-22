from django.urls import path

from . import views

app_name = 'panel'

urlpatterns = [
    path('', views.index, name='index'),

    path('empresas/', views.empresas, name='empresas'),
    path('empresas/nueva/', views.empresa_form, name='empresa_crear'),
    path('empresas/<int:pk>/', views.empresa_form, name='empresa_editar'),
    path('empresas/<int:pk>/eliminar/', views.empresa_eliminar, name='empresa_eliminar'),

    path('sitios/', views.sitios, name='sitios'),
    path('sitios/nuevo/', views.sitio_form, name='sitio_crear'),
    path('sitios/<int:pk>/', views.sitio_form, name='sitio_editar'),
    path('sitios/<int:pk>/eliminar/', views.sitio_eliminar, name='sitio_eliminar'),

    path('estructuras/', views.estructuras, name='estructuras'),
    path('estructuras/nueva/', views.plantilla_form, name='plantilla_crear'),
    path('estructuras/asignar/', views.estructura_asignar, name='estructura_asignar'),
    path('estructuras/<int:pk>/', views.plantilla_form, name='plantilla_editar'),
    path('estructuras/<int:pk>/clonar/', views.plantilla_clonar, name='plantilla_clonar'),
    path('estructuras/<int:pk>/default/', views.plantilla_default, name='plantilla_default'),
    path('estructuras/<int:pk>/eliminar/', views.plantilla_eliminar, name='plantilla_eliminar'),

    path('documentos/', views.documentos, name='documentos'),
    path('documentos/roles/', views.documentos_roles, name='documentos_roles'),
    path('documentos/nuevo/', views.documento_form, name='documento_crear'),
    path('documentos/<int:pk>/', views.documento_form, name='documento_editar'),
    path('documentos/<int:pk>/eliminar/', views.documento_eliminar, name='documento_eliminar'),
    path('documentos/<int:pk>/obligatorio/', views.documento_toggle_obligatorio, name='documento_toggle_obligatorio'),


    path('usuarios/', views.usuarios, name='usuarios'),
    path('usuarios/nuevo/', views.usuario_crear, name='usuario_crear'),
    path('usuarios/<int:pk>/', views.usuario_editar, name='usuario_editar'),
    path('usuarios/<int:pk>/toggle/', views.usuario_toggle_activo, name='usuario_toggle_activo'),
    path('usuarios/<int:pk>/toggle-acceso/<str:seccion>/', views.usuario_toggle_acceso, name='usuario_toggle_acceso'),
    path('usuarios/<int:pk>/eliminar/', views.usuario_eliminar, name='usuario_eliminar'),

    path('accesos/', views.accesos, name='accesos'),
    path('accesos/<int:pk>/', views.usuario_sitios, name='usuario_sitios'),
    path('accesos/<int:pk>/guardar/', views.usuario_sitios_guardar, name='usuario_sitios_guardar'),

    path('caches/', views.caches, name='caches'),
]
