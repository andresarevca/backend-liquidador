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


@api_view(['GET'])
def preinforme_view(request, pk):
    """
    Genera y descarga el pre-informe como archivo DOCX (Word) editable.

    Requiere que existan ResultadoIA paso='B' (y opcionalmente paso='C').
    Llama al microservicio ia-liquidador para obtener los datos estructurados,
    construye el documento Word con python-docx y lo sirve como descarga.

    GET /api/carpetas/<uuid>/preinforme/
      → descarga  preinforme-<caso_id>.docx
    """
    from django.http import HttpResponse
    from core.ia_client import generar_preinforme
    from core.report_generator import generar_docx

    # 1. Obtener carpeta
    try:
        carpeta = Carpeta.objects.prefetch_related('documentos').get(pk=pk)
    except Carpeta.DoesNotExist:
        return Response({'detail': 'Carpeta no encontrada.'}, status=status.HTTP_404_NOT_FOUND)

    # 2. Obtener resultados IA (paso B obligatorio, paso C opcional)
    try:
        paso_b = ResultadoIA.objects.get(carpeta=carpeta, paso='B').resultado
    except ResultadoIA.DoesNotExist:
        return Response(
            {'detail': 'El paso B (extracción) aún no está disponible. Ejecute el pipeline primero.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    paso_c_obj = ResultadoIA.objects.filter(carpeta=carpeta, paso='C').first()
    paso_c = paso_c_obj.resultado if paso_c_obj else None

    # 3. Metadatos del proceso desde la carpeta Django
    metadatos = {
        'nro_siniestro': carpeta.caso_id,
        'fecha_designacion': carpeta.recibida_en.strftime('%d/%m/%Y') if carpeta.recibida_en else '',
        'documentos': list(carpeta.documentos.values_list('nombre_archivo', flat=True)),
    }

    # 4. Llamar al microservicio ia-liquidador
    try:
        datos = generar_preinforme(carpeta.caso_id, paso_b, paso_c, metadatos)
    except RuntimeError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    # 5. Descargar logo si se proporcionó como query param
    logo_bytes = None
    logo_url = request.GET.get('logo_url')
    if logo_url:
        import urllib.request
        try:
            if not logo_url.startswith(('http://', 'https://')):
                raise ValueError('URL de logo inválida')
            req = urllib.request.Request(logo_url, headers={'User-Agent': 'liquidador/1.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                logo_bytes = resp.read()
        except Exception as exc:
            return Response(
                {'detail': f'No se pudo obtener el logo: {exc}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # 6. Generar DOCX y devolver como descarga
    docx_bytes = generar_docx(datos, logo_bytes=logo_bytes)
    safe_caso_id = carpeta.caso_id.replace('/', '-').replace(' ', '_')
    filename = f'preinforme-{safe_caso_id}.docx'
    response = HttpResponse(
        docx_bytes,
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
