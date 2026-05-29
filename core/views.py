from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Carpeta, ResultadoIA
from .serializers import (
    CarpetaDetailSerializer,
    CarpetaListSerializer,
    ResultadoIASerializer,
)


class CarpetaListView(generics.ListAPIView):
    """Lista todas las carpetas ordenadas por fecha de recepción (más reciente primero)."""
    queryset = Carpeta.objects.all()
    serializer_class = CarpetaListSerializer


class CarpetaDetailView(generics.RetrieveAPIView):
    """Detalle de una carpeta con sus documentos y resultados IA."""
    queryset = Carpeta.objects.prefetch_related('documentos', 'resultados')
    serializer_class = CarpetaDetailSerializer
    lookup_field = 'pk'


@api_view(['GET'])
def dictamen_view(request, pk):
    """Devuelve el dictamen (Paso C) de una carpeta específica."""
    try:
        resultado = ResultadoIA.objects.get(carpeta__pk=pk, paso='C')
        return Response(ResultadoIASerializer(resultado).data)
    except ResultadoIA.DoesNotExist:
        return Response(
            {'detail': 'El dictamen aún no está disponible para esta carpeta.'},
            status=status.HTTP_404_NOT_FOUND,
        )


@api_view(['POST'])
def reprocesar_view(request, pk):
    """Vuelve a lanzar el pipeline IA para una carpeta existente."""
    try:
        carpeta = Carpeta.objects.get(pk=pk)
    except Carpeta.DoesNotExist:
        return Response({'detail': 'Carpeta no encontrada.'}, status=status.HTTP_404_NOT_FOUND)

    from core.tasks import procesar_carpeta
    procesar_carpeta.delay(str(carpeta.pk))

    return Response({'detail': f"Pipeline relanzado para carpeta '{carpeta.caso_id}'."})
