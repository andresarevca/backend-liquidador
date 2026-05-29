from django.urls import path

from . import views

urlpatterns = [
    path('carpetas/', views.CarpetaListView.as_view(), name='carpeta-list'),
    path('carpetas/<uuid:pk>/', views.CarpetaDetailView.as_view(), name='carpeta-detail'),
    path('carpetas/<uuid:pk>/dictamen/', views.dictamen_view, name='carpeta-dictamen'),
    path('carpetas/<uuid:pk>/reprocesar/', views.reprocesar_view, name='carpeta-reprocesar'),
]
