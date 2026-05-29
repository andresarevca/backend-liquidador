"""
email_poller.py
===============
Módulo IMAP para recuperar correos con adjuntos (carpetas de siniestros).

Flujo:
  1. Conecta al servidor IMAP configurado en settings.
  2. Busca correos no leídos en la carpeta configurada.
  3. Por cada correo: extrae adjuntos, crea Carpeta + Documento en la BD.
  4. Marca el correo como leído.
  5. Retorna lista de PKs de Carpeta creadas, para lanzar el pipeline.
"""

import email
import imaplib
import logging
import re
import uuid
from email.header import decode_header
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

EXTENSIONES_PERMITIDAS = {'.pdf', '.jpg', '.jpeg', '.png', '.docx', '.odt', '.odf', '.txt'}


def _decodificar_header(valor: str) -> str:
    """Decodifica cabeceras MIME que pueden estar en distintas codificaciones."""
    if not valor:
        return ''
    partes = decode_header(valor)
    decoded = []
    for parte, charset in partes:
        if isinstance(parte, bytes):
            decoded.append(parte.decode(charset or 'utf-8', errors='replace'))
        else:
            decoded.append(str(parte))
    return ''.join(decoded)


def _sanitizar_caso_id(asunto: str) -> str:
    """Genera un caso_id seguro y legible a partir del asunto del email."""
    clean = re.sub(r'[^\w\s-]', '', asunto).strip()
    clean = re.sub(r'\s+', '-', clean)[:80]
    return clean or f"CASO-{uuid.uuid4().hex[:8].upper()}"


def poll_emails() -> list[str]:
    """
    Recupera correos no leídos del servidor IMAP y crea registros en la BD.

    Retorna lista de PKs (str) de las Carpeta recién creadas.
    """
    from core.models import Carpeta, Documento  # import local para evitar ciclos

    host = getattr(settings, 'IMAP_HOST', '')
    port = getattr(settings, 'IMAP_PORT', 993)
    user = getattr(settings, 'IMAP_USER', '')
    password = getattr(settings, 'IMAP_PASSWORD', '')
    folder = getattr(settings, 'IMAP_FOLDER', 'INBOX')

    if not all([host, user, password]):
        logger.error("Configuración IMAP incompleta. Verifica IMAP_HOST, IMAP_USER, IMAP_PASSWORD.")
        return []

    carpetas_creadas = []

    try:
        conn = imaplib.IMAP4_SSL(host, port)
        conn.login(user, password)
        conn.select(folder)

        _, msg_ids_data = conn.search(None, 'UNSEEN')
        ids = msg_ids_data[0].split() if msg_ids_data[0] else []
        logger.info(f"Emails no leídos encontrados: {len(ids)}")

        for msg_id in ids:
            try:
                _, data = conn.fetch(msg_id, '(RFC822)')
                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)

                asunto = _decodificar_header(msg.get('Subject', 'Sin asunto'))
                remitente = _decodificar_header(msg.get('From', ''))
                caso_id_base = _sanitizar_caso_id(asunto)

                # Garantizar unicidad del caso_id
                caso_id = caso_id_base
                suffix = 1
                while Carpeta.objects.filter(caso_id=caso_id).exists():
                    caso_id = f"{caso_id_base}-{suffix}"
                    suffix += 1

                carpeta = Carpeta.objects.create(
                    caso_id=caso_id,
                    email_remitente=remitente[:500],
                    email_asunto=asunto[:500],
                    estado='RECIBIDA',
                )

                adjuntos_guardados = 0
                for part in msg.walk():
                    content_disposition = part.get('Content-Disposition', '')
                    if 'attachment' not in content_disposition:
                        continue

                    filename_raw = part.get_filename()
                    if not filename_raw:
                        continue

                    filename = _decodificar_header(filename_raw)
                    # Sanitizar nombre del archivo
                    filename = re.sub(r'[^\w\s.\-]', '_', filename).strip()
                    ext = Path(filename).suffix.lower()

                    if ext not in EXTENSIONES_PERMITIDAS:
                        logger.warning(f"Adjunto ignorado (extensión no permitida): {filename}")
                        continue

                    payload = part.get_payload(decode=True)
                    if not payload:
                        logger.warning(f"Adjunto vacío: {filename}")
                        continue

                    documento = Documento(
                        carpeta=carpeta,
                        nombre_archivo=filename,
                        formato=ext.lstrip('.').upper(),
                    )
                    documento.archivo.save(filename, ContentFile(payload), save=True)
                    adjuntos_guardados += 1
                    logger.info(f"  Adjunto guardado: {filename} ({len(payload)} bytes)")

                if adjuntos_guardados == 0:
                    carpeta.estado = 'ERROR'
                    carpeta.mensaje_error = 'El correo no contenía adjuntos con extensión válida (pdf, jpg, png, docx, odt, txt).'
                    carpeta.save(update_fields=['estado', 'mensaje_error'])
                    logger.warning(f"Carpeta {caso_id}: sin adjuntos válidos, no se procesa.")
                else:
                    carpetas_creadas.append(str(carpeta.pk))
                    logger.info(f"Carpeta creada: {caso_id} | {adjuntos_guardados} documento(s).")

                # Marcar como leído
                conn.store(msg_id, '+FLAGS', '\\Seen')

            except Exception as e:
                logger.exception(f"Error procesando email id={msg_id}: {e}")

        conn.logout()

    except imaplib.IMAP4.error as e:
        logger.error(f"Error de autenticación/conexión IMAP: {e}")
    except OSError as e:
        logger.error(f"Error de red al conectar con IMAP ({host}:{port}): {e}")
    except Exception as e:
        logger.exception(f"Error inesperado en poll_emails: {e}")

    return carpetas_creadas
