from django.urls import path
from . import views

app_name = 'docs'

urlpatterns = [
    path('', views.index, name='index'),
    path('final/', views.final, name='final'),
    path('api/sitios/', views.api_sitios, name='api_sitios'),
    path('api/carpetas/', views.api_carpetas, name='api_carpetas'),
    path('api/carpetas/archivos/', views.api_carpetas_archivos, name='api_carpetas_archivos'),
    path('api/final/tree/', views.api_final_tree, name='api_final_tree'),
    path('api/final/archivos/', views.api_final_archivos, name='api_final_archivos'),
]
