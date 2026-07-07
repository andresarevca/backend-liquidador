"""Serializers exclusivos del namespace /api/admin/ (backoffice)."""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Carpeta, CorreoRechazado

User = get_user_model()


class AdminUsuarioSerializer(serializers.ModelSerializer):
    nombre = serializers.SerializerMethodField()
    carpetas_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'nombre', 'is_staff', 'is_active',
            'date_joined', 'last_login', 'carpetas_count',
        ]

    def get_nombre(self, obj):
        return obj.get_full_name() or obj.get_username()


class AdminUsuarioCreateSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(write_only=True, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['email', 'nombre', 'password', 'is_staff', 'is_active']

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Ya existe un usuario con ese email.')
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        nombre = validated_data.pop('nombre', '')
        password = validated_data.pop('password')
        email = validated_data.pop('email')
        user = User(username=email, email=email, first_name=nombre, **validated_data)
        user.set_password(password)
        user.save()
        return user

    def to_representation(self, instance):
        instance.carpetas_count = instance.carpetas.count()
        return AdminUsuarioSerializer(instance).data


class AdminUsuarioUpdateSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(write_only=True, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ['email', 'nombre', 'password', 'is_staff', 'is_active']
        extra_kwargs = {'email': {'required': False}}

    def validate_email(self, value):
        if User.objects.exclude(pk=self.instance.pk).filter(email__iexact=value).exists():
            raise serializers.ValidationError('Ya existe un usuario con ese email.')
        return value

    def validate_password(self, value):
        if value:
            validate_password(value, user=self.instance)
        return value

    def update(self, instance, validated_data):
        nombre = validated_data.pop('nombre', None)
        password = validated_data.pop('password', None)
        email = validated_data.pop('email', None)

        if email:
            instance.email = email
            instance.username = email
        if nombre is not None:
            instance.first_name = nombre
        if password:
            instance.set_password(password)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance

    def to_representation(self, instance):
        instance.carpetas_count = instance.carpetas.count()
        return AdminUsuarioSerializer(instance).data


class AdminCarpetaSerializer(serializers.ModelSerializer):
    total_documentos = serializers.IntegerField(source='documentos.count', read_only=True)
    usuario_id = serializers.IntegerField(source='usuario.id', read_only=True, default=None)
    usuario_email = serializers.CharField(source='usuario.email', read_only=True, default=None)
    usuario_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Carpeta
        fields = [
            'id', 'caso_id', 'usuario_id', 'usuario_email', 'usuario_nombre',
            'email_remitente', 'email_asunto', 'estado', 'recibida_en',
            'procesada_en', 'total_documentos',
        ]

    def get_usuario_nombre(self, obj):
        if not obj.usuario:
            return None
        return obj.usuario.get_full_name() or obj.usuario.get_username()


class CorreoRechazadoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CorreoRechazado
        fields = ['id', 'email_remitente', 'email_asunto', 'motivo', 'recibido_en']
