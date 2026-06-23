from pathlib import Path

from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Carpeta, Documento, ResultadoIA
from .serializers import (
    CarpetaDetailSerializer,
    CarpetaListSerializer,
    DocumentoConCarpetaSerializer,
    DocumentoSerializer,
    EmailOrUsernameTokenObtainPairSerializer,
    ResultadoIASerializer,
    UserMeSerializer,
)


class LoginView(TokenObtainPairView):
    """Login con username o email + password. Devuelve par de tokens JWT (access/refresh)."""
    permission_classes = [AllowAny]
    serializer_class = EmailOrUsernameTokenObtainPairSerializer


@api_view(['GET'])
def me_view(request):
    """Datos del usuario autenticado (nombre, email, rol)."""
    return Response(UserMeSerializer(request.user).data)


class CarpetaListView(generics.ListAPIView):
    """Lista todas las carpetas ordenadas por fecha de recepción (más reciente primero)."""
    queryset = Carpeta.objects.all()
    serializer_class = CarpetaListSerializer


class CarpetaDetailView(generics.RetrieveAPIView):
    """Detalle de una carpeta con sus documentos y resultados IA."""
    queryset = Carpeta.objects.prefetch_related('documentos', 'resultados')
    serializer_class = CarpetaDetailSerializer
    lookup_field = 'pk'


class DocumentoListView(generics.ListAPIView):
    """Biblioteca global de documentos recibidos en todas las carpetas."""
    queryset = Documento.objects.select_related('carpeta').order_by('-subido_en')
    serializer_class = DocumentoConCarpetaSerializer


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
def subir_documentos_view(request, pk):
    """
    Sube uno o más documentos faltantes a una carpeta existente.

    POST /api/carpetas/<uuid>/documentos/  (multipart/form-data: archivos[])
    No relanza el pipeline automáticamente; usar luego /reprocesar/.
    """
    from core.email_poller import EXTENSIONES_PERMITIDAS

    try:
        carpeta = Carpeta.objects.get(pk=pk)
    except Carpeta.DoesNotExist:
        return Response({'detail': 'Carpeta no encontrada.'}, status=status.HTTP_404_NOT_FOUND)

    archivos = request.FILES.getlist('archivos')
    if not archivos:
        return Response(
            {'detail': 'Debe adjuntar al menos un archivo en el campo "archivos".'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    creados = []
    rechazados = []
    for archivo in archivos:
        ext = Path(archivo.name).suffix.lower()
        if ext not in EXTENSIONES_PERMITIDAS:
            rechazados.append(archivo.name)
            continue
        documento = Documento(
            carpeta=carpeta,
            nombre_archivo=archivo.name,
            formato=ext.lstrip('.').upper(),
        )
        documento.archivo.save(archivo.name, archivo, save=True)
        creados.append(documento)

    if not creados:
        return Response(
            {
                'detail': (
                    'Ningún archivo tiene una extensión válida '
                    f'({", ".join(sorted(EXTENSIONES_PERMITIDAS))}).'
                ),
            },
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    return Response(
        {
            'documentos': DocumentoSerializer(creados, many=True).data,
            'rechazados': rechazados,
        },
        status=status.HTTP_201_CREATED,
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


@api_view(['GET'])
def corpus_buscar_view(request):
    """
    Búsqueda semántica en el corpus legal (leyes y ordenanzas indexadas).

    GET /api/corpus/buscar/?q=...&municipio=...&n=6
    """
    from core.ia_client import buscar_corpus

    q = request.GET.get('q', '').strip()
    if len(q) < 3:
        return Response(
            {'detail': 'El parámetro "q" debe tener al menos 3 caracteres.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    municipio = request.GET.get('municipio') or None
    n = int(request.GET.get('n', 6))

    try:
        data = buscar_corpus(q, municipio=municipio, n=n)
    except RuntimeError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response(data)


@api_view(['GET'])
def corpus_fuentes_view(request):
    """Lista los documentos legales indexados y estadísticas del corpus."""
    from core.ia_client import listar_fuentes_corpus

    try:
        data = listar_fuentes_corpus()
    except RuntimeError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response(data)


@api_view(['POST'])
def corpus_indexar_pdf_view(request):
    """
    Sube e indexa un PDF de ordenanza municipal en el corpus legal.

    POST /api/corpus/indexar-pdf/  (multipart/form-data: archivo, municipio)
    """
    from core.ia_client import indexar_pdf_corpus

    archivo = request.FILES.get('archivo')
    if not archivo or not archivo.name.lower().endswith('.pdf'):
        return Response(
            {'detail': 'Debe adjuntar un archivo PDF en el campo "archivo".'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    municipio = request.POST.get('municipio', 'Nacional')

    try:
        data = indexar_pdf_corpus(archivo, archivo.name, municipio)
    except RuntimeError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response(data)
