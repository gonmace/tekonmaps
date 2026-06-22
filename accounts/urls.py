from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('crear-password/', views.crear_password_view, name='crear_password'),
    path('logout/', views.logout_view, name='logout'),
]
