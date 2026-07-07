from django.urls import path

from . import admin_views

urlpatterns = [
    path('usuarios/', admin_views.AdminUsuarioListCreateView.as_view(), name='admin-usuario-list'),
    path('usuarios/<int:pk>/', admin_views.AdminUsuarioDetailView.as_view(), name='admin-usuario-detail'),
    path('carpetas/', admin_views.AdminCarpetaListView.as_view(), name='admin-carpeta-list'),
    path('carpetas/<uuid:pk>/', admin_views.AdminCarpetaDetailView.as_view(), name='admin-carpeta-detail'),
    path('correos-rechazados/', admin_views.AdminCorreoRechazadoListView.as_view(), name='admin-correo-rechazado-list'),
    path('metricas/', admin_views.metricas_view, name='admin-metricas'),
]
