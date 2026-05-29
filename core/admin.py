from django.contrib import admin

from .models import Carpeta, Documento, ResultadoIA


class DocumentoInline(admin.TabularInline):
    model = Documento
    extra = 0
    readonly_fields = ['nombre_archivo', 'formato', 'tipo_doc', 'subido_en']


class ResultadoIAInline(admin.TabularInline):
    model = ResultadoIA
    extra = 0
    readonly_fields = ['paso', 'generado_en']


@admin.register(Carpeta)
class CarpetaAdmin(admin.ModelAdmin):
    list_display = ['caso_id', 'email_remitente', 'estado', 'recibida_en', 'procesada_en']
    list_filter = ['estado']
    search_fields = ['caso_id', 'email_remitente', 'email_asunto']
    readonly_fields = ['id', 'recibida_en', 'procesada_en']
    inlines = [DocumentoInline, ResultadoIAInline]


@admin.register(Documento)
class DocumentoAdmin(admin.ModelAdmin):
    list_display = ['nombre_archivo', 'formato', 'tipo_doc', 'carpeta', 'subido_en']
    search_fields = ['nombre_archivo', 'carpeta__caso_id']
    list_filter = ['formato', 'tipo_doc']


@admin.register(ResultadoIA)
class ResultadoIAAdmin(admin.ModelAdmin):
    list_display = ['carpeta', 'paso', 'generado_en']
    list_filter = ['paso']
    search_fields = ['carpeta__caso_id']
