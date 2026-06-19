from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Carpeta, Documento, ResultadoIA

User = get_user_model()


class EmailOrUsernameTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Permite loguearse con el username o con el email del usuario."""

    def validate(self, attrs):
        login = attrs.get(self.username_field)
        try:
            user = User.objects.get(email__iexact=login)
            attrs[self.username_field] = user.get_username()
        except User.DoesNotExist:
            pass
        return super().validate(attrs)


class UserMeSerializer(serializers.ModelSerializer):
    nombre = serializers.SerializerMethodField()
    rol = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['email', 'nombre', 'rol']

    def get_nombre(self, obj):
        return obj.get_full_name() or obj.get_username()

    def get_rol(self, obj):
        return 'Admin' if obj.is_staff or obj.is_superuser else 'Liquidador'


class DocumentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Documento
        fields = ['id', 'nombre_archivo', 'formato', 'tipo_doc', 'subido_en']


class DocumentoConCarpetaSerializer(serializers.ModelSerializer):
    caso_id = serializers.CharField(source='carpeta.caso_id', read_only=True)
    caso_pk = serializers.UUIDField(source='carpeta_id', read_only=True)

    class Meta:
        model = Documento
        fields = ['id', 'nombre_archivo', 'formato', 'tipo_doc', 'subido_en', 'caso_id', 'caso_pk']


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
