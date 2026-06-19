from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path('auth/login/', views.LoginView.as_view(), name='auth-login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='auth-refresh'),
    path('auth/me/', views.me_view, name='auth-me'),
    path('documentos/', views.DocumentoListView.as_view(), name='documento-list'),
    path('carpetas/', views.CarpetaListView.as_view(), name='carpeta-list'),
    path('carpetas/<uuid:pk>/', views.CarpetaDetailView.as_view(), name='carpeta-detail'),
    path('carpetas/<uuid:pk>/dictamen/', views.dictamen_view, name='carpeta-dictamen'),
    path('carpetas/<uuid:pk>/reprocesar/', views.reprocesar_view, name='carpeta-reprocesar'),
    path('carpetas/<uuid:pk>/preinforme/', views.preinforme_view, name='carpeta-preinforme'),
]
