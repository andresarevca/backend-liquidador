import uuid

from django.conf import settings
from django.db import models


class Carpeta(models.Model):
    ESTADO_CHOICES = [
        ('RECIBIDA', 'Recibida'),
        ('PROCESANDO', 'Procesando'),
        ('COMPLETADA', 'Completada'),
        ('ERROR', 'Error'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    caso_id = models.CharField(max_length=200, unique=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='carpetas',
        help_text='Usuario del sistema al que se asignó la carpeta (resuelto por el email del remitente).',
    )
    email_remitente = models.CharField(max_length=500)
    email_asunto = models.CharField(max_length=500)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='RECIBIDA')
    recibida_en = models.DateTimeField(auto_now_add=True)
    procesada_en = models.DateTimeField(null=True, blank=True)
    mensaje_error = models.TextField(blank=True)

    class Meta:
        ordering = ['-recibida_en']

    def __str__(self):
        return f"{self.caso_id} ({self.estado})"


class CorreoRechazado(models.Model):
    """Registro de correos entrantes ignorados por no provenir de un usuario del sistema."""

    email_remitente = models.CharField(max_length=500)
    email_asunto = models.CharField(max_length=500)
    motivo = models.CharField(max_length=200)
    recibido_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recibido_en']

    def __str__(self):
        return f"{self.email_remitente} — {self.motivo}"


class Documento(models.Model):
    carpeta = models.ForeignKey(Carpeta, on_delete=models.CASCADE, related_name='documentos')
    nombre_archivo = models.CharField(max_length=255)
    archivo = models.FileField(upload_to='documentos/%Y/%m/%d/')
    formato = models.CharField(max_length=50)
    contenido_texto = models.TextField(blank=True)
    tipo_doc = models.CharField(max_length=50, blank=True)
    subido_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nombre_archivo} → {self.carpeta.caso_id}"


class ResultadoIA(models.Model):
    PASO_CHOICES = [
        ('A', 'Clasificación'),
        ('B', 'Extracción'),
        ('C', 'Dictamen'),
    ]

    carpeta = models.ForeignKey(Carpeta, on_delete=models.CASCADE, related_name='resultados')
    paso = models.CharField(max_length=1, choices=PASO_CHOICES)
    resultado = models.JSONField()
    generado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['carpeta', 'paso']
        ordering = ['paso']

    def __str__(self):
        return f"Paso {self.paso} — {self.carpeta.caso_id}"
