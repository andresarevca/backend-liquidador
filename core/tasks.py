"""
tasks.py
========
Tareas Celery para procesamiento asíncrono de carpetas de siniestros.

Tareas:
  poll_email_task  — Tarea periódica: recupera emails y dispara el pipeline.
  procesar_carpeta — Ejecuta el pipeline IA completo para una carpeta.
"""

import logging

from celery import shared_task
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(name='core.tasks.poll_email_task')
def poll_email_task():
    """
    Tarea periódica ejecutada por Celery Beat.
    Recupera emails nuevos y lanza procesar_carpeta por cada uno.
    """
    from core.email_poller import poll_emails

    logger.info("Iniciando poll de correos...")
    carpetas_ids = poll_emails()
    logger.info(f"Carpetas nuevas encontradas: {len(carpetas_ids)}")

    for pk in carpetas_ids:
        procesar_carpeta.delay(pk)

    return {'carpetas_encoladas': len(carpetas_ids)}


@shared_task(name='core.tasks.procesar_carpeta', bind=True, max_retries=2)
def procesar_carpeta(self, carpeta_pk: str):
    """
    Ejecuta el pipeline IA (Paso A → B → C) para la carpeta indicada.
    Guarda los resultados en ResultadoIA y actualiza el estado de la Carpeta.
    """
    from core.models import Carpeta, ResultadoIA
    from core.pipeline import ejecutar_pipeline

    try:
        carpeta = Carpeta.objects.get(pk=carpeta_pk)
    except Carpeta.DoesNotExist:
        logger.error(f"Carpeta no encontrada: pk={carpeta_pk}")
        return

    carpeta.estado = 'PROCESANDO'
    carpeta.mensaje_error = ''
    carpeta.save(update_fields=['estado', 'mensaje_error'])

    documentos = list(carpeta.documentos.all())
    if not documentos:
        carpeta.estado = 'ERROR'
        carpeta.mensaje_error = 'La carpeta no tiene documentos adjuntos.'
        carpeta.save(update_fields=['estado', 'mensaje_error'])
        return

    resultado = ejecutar_pipeline(carpeta.caso_id, documentos)

    # Persistir Paso A
    if resultado.get('paso_a'):
        ResultadoIA.objects.update_or_create(
            carpeta=carpeta,
            paso='A',
            defaults={'resultado': resultado['paso_a']},
        )
        # Actualizar tipo_doc en cada Documento
        for doc_result in resultado['paso_a']:
            if not doc_result.get('error') and doc_result.get('tipo_doc'):
                carpeta.documentos.filter(
                    nombre_archivo=doc_result['archivo']
                ).update(tipo_doc=doc_result['tipo_doc'])

    # Persistir Paso B
    if resultado.get('paso_b'):
        ResultadoIA.objects.update_or_create(
            carpeta=carpeta,
            paso='B',
            defaults={'resultado': resultado['paso_b']},
        )

    # Persistir Paso C
    if resultado.get('paso_c'):
        ResultadoIA.objects.update_or_create(
            carpeta=carpeta,
            paso='C',
            defaults={'resultado': resultado['paso_c']},
        )

    carpeta.procesada_en = timezone.now()
    if resultado.get('error'):
        carpeta.estado = 'ERROR'
        carpeta.mensaje_error = resultado['error']
    else:
        carpeta.estado = 'COMPLETADA'

    carpeta.save(update_fields=['estado', 'procesada_en', 'mensaje_error'])
    logger.info(f"Pipeline finalizado — caso: {carpeta.caso_id} | estado: {carpeta.estado}")

    # Si todo salió bien, generamos el pre-informe y lo enviamos de vuelta al emisor
    if carpeta.estado == 'COMPLETADA':
        try:
            from core.ia_client import generar_preinforme
            from core.report_generator import generar_docx
            from django.core.mail import EmailMessage
            import email.utils

            # Extraer sólo la dirección de email limpia para evitar problemas con cabeceras con nombre largo
            _, destinatario = email.utils.parseaddr(carpeta.email_remitente)
            if not destinatario:
                destinatario = carpeta.email_remitente

            logger.info(f"Iniciando generación de pre-informe para envío a {destinatario}...")

            # Organizar metadatos
            metadatos = {
                'nro_siniestro': carpeta.caso_id,
                'fecha_designacion': carpeta.recibida_en.strftime('%d/%m/%Y') if carpeta.recibida_en else '',
                'documentos': list(carpeta.documentos.values_list('nombre_archivo', flat=True)),
            }

            paso_b = ResultadoIA.objects.get(carpeta=carpeta, paso='B').resultado
            paso_c_obj = ResultadoIA.objects.filter(carpeta=carpeta, paso='C').first()
            paso_c = paso_c_obj.resultado if paso_c_obj else None

            # Llamar a la IA
            datos = generar_preinforme(carpeta.caso_id, paso_b, paso_c, metadatos)
            
            # Generar los bytes del Word (DOCX)
            docx_bytes = generar_docx(datos)
            safe_caso_id = carpeta.caso_id.replace('/', '-').replace(' ', '_')
            filename = f'preinforme-{safe_caso_id}.docx'

            # Construir y enviar el correo
            asunto_saliente = f"RE: {carpeta.email_asunto}"
            cuerpo = (
                f"Estimado remitente,\n\n"
                f"Hemos procesado la carpeta con ID: {carpeta.caso_id}.\n"
                f"Adjunto a este correo encontrará el pre-informe técnico de liquidación generado automáticamente para su revisión.\n\n"
                f"Atentamente,\n"
                f"Sistema de Liquidación Inteligente"
            )

            email_msg = EmailMessage(
                asunto_saliente,
                cuerpo,
                settings.DEFAULT_FROM_EMAIL,
                [destinatario],
            )
            email_msg.attach(filename, docx_bytes, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
            email_msg.send()

            logger.info(f"Pre-informe enviado exitosamente a {destinatario} para el caso {carpeta.caso_id}.")

        except Exception as e:
            logger.exception(f"Error al generar o enviar el pre-informe por correo para {carpeta.caso_id}: {e}")
