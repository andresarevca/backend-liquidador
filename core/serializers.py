from rest_framework import serializers

from .models import Carpeta, Documento, ResultadoIA


class DocumentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Documento
        fields = ['id', 'nombre_archivo', 'formato', 'tipo_doc', 'subido_en']


class ResultadoIASerializer(serializers.ModelSerializer):
    paso_display = serializers.CharField(source='get_paso_display', read_only=True)

    class Meta:
        model = ResultadoIA
        fields = ['paso', 'paso_display', 'resultado', 'generado_en']


class CarpetaListSerializer(serializers.ModelSerializer):
    total_documentos = serializers.IntegerField(source='documentos.count', read_only=True)

    class Meta:
        model = Carpeta
        fields = ['id', 'caso_id', 'email_remitente', 'email_asunto',
                  'estado', 'recibida_en', 'procesada_en', 'total_documentos']


class CarpetaDetailSerializer(serializers.ModelSerializer):
    documentos = DocumentoSerializer(many=True, read_only=True)
    resultados = ResultadoIASerializer(many=True, read_only=True)

    class Meta:
        model = Carpeta
        fields = '__all__'
