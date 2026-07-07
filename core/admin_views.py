"""Vistas exclusivas del namespace /api/admin/ (backoffice de gestión)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from .admin_serializers import (
    AdminCarpetaSerializer,
    AdminUsuarioCreateSerializer,
    AdminUsuarioSerializer,
    AdminUsuarioUpdateSerializer,
    CorreoRechazadoSerializer,
)
from .models import Carpeta, CorreoRechazado

User = get_user_model()


class AdminUsuarioListCreateView(generics.ListCreateAPIView):
    """Lista y crea usuarios del sistema (backoffice)."""
    permission_classes = [IsAdminUser]
    queryset = User.objects.annotate(carpetas_count=Count('carpetas')).order_by('-date_joined')

    def get_serializer_class(self):
        return AdminUsuarioCreateSerializer if self.request.method == 'POST' else AdminUsuarioSerializer


class AdminUsuarioDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Detalle, edición (parcial) y eliminación de un usuario (backoffice)."""
    permission_classes = [IsAdminUser]
    queryset = User.objects.annotate(carpetas_count=Count('carpetas'))

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return AdminUsuarioUpdateSerializer
        return AdminUsuarioSerializer

    def patch(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)


class AdminCarpetaListView(generics.ListAPIView):
    """Listado global de carpetas (todos los usuarios), con filtro opcional ?usuario=<id>."""
    permission_classes = [IsAdminUser]
    serializer_class = AdminCarpetaSerializer

    def get_queryset(self):
        qs = Carpeta.objects.select_related('usuario')
        usuario_id = self.request.query_params.get('usuario')
        if usuario_id:
            qs = qs.filter(usuario_id=usuario_id)
        return qs


class AdminCarpetaDetailView(generics.RetrieveAPIView):
    """Detalle de una carpeta, sin restricción de dueño (backoffice)."""
    permission_classes = [IsAdminUser]
    serializer_class = AdminCarpetaSerializer
    queryset = Carpeta.objects.select_related('usuario').prefetch_related('documentos', 'resultados')
    lookup_field = 'pk'


class AdminCorreoRechazadoListView(generics.ListAPIView):
    """Auditoría de correos entrantes ignorados por remitente no registrado."""
    permission_classes = [IsAdminUser]
    serializer_class = CorreoRechazadoSerializer
    queryset = CorreoRechazado.objects.all()


@api_view(['GET'])
@permission_classes([IsAdminUser])
def metricas_view(request):
    """Métricas de uso de la app para el dashboard del backoffice."""
    ahora = timezone.now()
    desde = ahora - timedelta(days=30)

    carpetas_por_estado = dict(
        Carpeta.objects.values_list('estado').annotate(total=Count('id')).order_by()
    )
    total_carpetas = sum(carpetas_por_estado.values())

    carpetas_por_dia = list(
        Carpeta.objects.filter(recibida_en__gte=desde)
        .annotate(dia=TruncDate('recibida_en'))
        .values('dia')
        .annotate(total=Count('id'))
        .order_by('dia')
    )

    tiempo_procesamiento = Carpeta.objects.filter(
        estado='COMPLETADA', procesada_en__isnull=False,
    ).aggregate(
        promedio=Avg(
            ExpressionWrapper(F('procesada_en') - F('recibida_en'), output_field=DurationField())
        )
    )['promedio']

    top_usuarios = list(
        User.objects.annotate(total_carpetas=Count('carpetas'))
        .filter(total_carpetas__gt=0)
        .order_by('-total_carpetas')[:10]
        .values('id', 'email', 'first_name', 'last_name', 'total_carpetas')
    )

    return Response({
        'usuarios_activos': User.objects.filter(is_active=True).count(),
        'usuarios_inactivos': User.objects.filter(is_active=False).count(),
        'total_carpetas': total_carpetas,
        'carpetas_por_estado': carpetas_por_estado,
        'tasa_error': (
            round(100 * carpetas_por_estado.get('ERROR', 0) / total_carpetas, 1)
            if total_carpetas else 0
        ),
        'carpetas_por_dia': carpetas_por_dia,
        'tiempo_procesamiento_promedio_segundos': (
            tiempo_procesamiento.total_seconds() if tiempo_procesamiento else None
        ),
        'top_usuarios': top_usuarios,
        'correos_rechazados_30d': CorreoRechazado.objects.filter(recibido_en__gte=desde).count(),
    })
