"""
pipeline.py
===========
Servicio de pipeline IA para liquidación de siniestros vehiculares.
Adaptado de ia-liquidador/validar_pipeline_ia.py para uso en Django.

Pasos:
  A — Clasificación de documentos
  B — Extracción de variables críticas
  C — Análisis normativo y dictamen sugerido
"""

import json
import logging
import time
from pathlib import Path

import google.generativeai as genai
from django.conf import settings

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash"
MAX_RETRIES = 3
RETRY_DELAY = 5

_FORMATOS = {
    '.pdf': 'PDF_DIGITAL',
    '.jpg': 'IMAGEN',
    '.jpeg': 'IMAGEN',
    '.png': 'IMAGEN',
    '.docx': 'DOCX',
    '.odt': 'ODT',
    '.odf': 'ODF',
    '.txt': 'TEXTO',
}


def _get_formato(nombre_archivo: str) -> str:
    ext = Path(nombre_archivo).suffix.lower()
    return _FORMATOS.get(ext, 'OTRO')


def extraer_texto(ruta_archivo: str, nombre_archivo: str) -> str:
    """Extrae texto de un archivo según su formato."""
    formato = _get_formato(nombre_archivo)
    try:
        if formato in ('PDF_DIGITAL',):
            import pdfplumber
            with pdfplumber.open(ruta_archivo) as pdf:
                return '\n'.join(page.extract_text() or '' for page in pdf.pages)
        elif formato == 'IMAGEN':
            return f'[IMAGEN: {nombre_archivo} — contenido visual adjunto]'
        elif formato == 'DOCX':
            from docx import Document
            doc = Document(ruta_archivo)
            return '\n'.join(p.text for p in doc.paragraphs)
        elif formato in ('ODT', 'ODF'):
            from odf import teletype
            from odf.opendocument import load
            doc = load(ruta_archivo)
            return teletype.extractText(doc.body)
        else:
            with open(ruta_archivo, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
    except Exception as e:
        logger.warning(f"Error extrayendo texto de {nombre_archivo}: {e}")
        return ''


def _llamar_gemini(prompt_sistema: str, prompt_usuario: str) -> str | None:
    """Llama a la API de Gemini con reintentos automáticos."""
    api_key = getattr(settings, 'GEMINI_API_KEY', '')
    if not api_key:
        logger.error("GEMINI_API_KEY no configurada en settings.")
        return None

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=prompt_sistema,
    )
    for intento in range(1, MAX_RETRIES + 1):
        try:
            respuesta = model.generate_content(prompt_usuario)
            return respuesta.text
        except Exception as e:
            if intento < MAX_RETRIES:
                logger.warning(f"Gemini intento {intento}/{MAX_RETRIES} falló: {e}. Reintentando en {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
            else:
                logger.error(f"Gemini falló después de {MAX_RETRIES} intentos: {e}")
                return None


def _parsear_json(texto: str) -> dict | None:
    """Parsea JSON seguro desde respuesta de Gemini (limpia bloques Markdown)."""
    texto = texto.strip()
    if texto.startswith('```'):
        lineas = texto.split('\n')
        texto = '\n'.join(lineas[1:])
        if texto.strip().endswith('```'):
            texto = texto.strip()[:-3]
    try:
        return json.loads(texto)
    except json.JSONDecodeError as e:
        logger.error(f"JSON inválido de Gemini: {e}. Respuesta (300 chars): {texto[:300]}")
        return None


# ---------------------------------------------------------------------------
# PASO A — Clasificación de documentos
# ---------------------------------------------------------------------------

_SYSTEM_A = """
Eres un clasificador especializado en documentos de siniestros vehiculares del Paraguay.
Tu única tarea es analizar el contenido de cada archivo y devolver una clasificación en JSON.
REGLAS: Devuelve ÚNICAMENTE el objeto JSON. Sin texto adicional ni Markdown.
Si el documento es ilegible, marca legible: false. No extraigas datos en este paso.
""".strip()


def paso_a_clasificar(documentos: list[dict]) -> list[dict]:
    """
    Clasifica cada documento usando Gemini.

    documentos: [{"nombre_archivo": str, "formato": str, "contenido": str}]
    Retorna lista con resultados de clasificación.
    """
    resultados = []
    for doc in documentos:
        prompt = f"""Analiza el siguiente documento del caso de siniestro vehicular.

Nombre del archivo: {doc['nombre_archivo']}
Formato: {doc['formato']}

CONTENIDO:
{doc['contenido'][:6000]}

Clasifica y devuelve EXCLUSIVAMENTE este JSON:
{{
  "tipo_doc": "<POLIZA | DENUNCIA_POLICIAL | DENUNCIA_ADMINISTRATIVA | PERICIA_TECNICA | PRESUPUESTO_TALLER | FOTO_EVENTO | FOTO_DANIOS | CEDULA_VERDE | LICENCIA_CONDUCIR | INFORME_MEDICO | OTRO>",
  "legible": <true | false>,
  "confianza": <0.0 a 1.0>,
  "nota_clasificacion": "<observación breve o null>",
  "pertenece_al_caso": <true | false>,
  "razon_pertenencia": "<una frase explicando por qué>"
}}""".strip()

        respuesta = _llamar_gemini(_SYSTEM_A, prompt)
        if respuesta:
            parsed = _parsear_json(respuesta)
            if parsed:
                parsed['archivo'] = doc['nombre_archivo']
                parsed['contenido_original'] = doc['contenido']
                resultados.append(parsed)
                logger.info(f"Paso A — {doc['nombre_archivo']} → {parsed.get('tipo_doc')} (conf: {parsed.get('confianza')})")
                continue
        logger.error(f"Paso A — sin resultado para {doc['nombre_archivo']}")
        resultados.append({'archivo': doc['nombre_archivo'], 'error': True})
    return resultados


# ---------------------------------------------------------------------------
# PASO B — Extracción de variables críticas
# ---------------------------------------------------------------------------

_SYSTEM_B = """
Eres un extractor de datos forense especializado en siniestros vehiculares del Paraguay.
Analiza un conjunto de documentos y extrae todas las variables críticas en JSON.
REGLAS: Devuelve ÚNICAMENTE el objeto JSON. Sin texto adicional ni Markdown.
Si un dato no figura en ningún documento, usa null. NUNCA inventes datos.
Si el mismo dato aparece con valores contradictorios, agrégalo al array conflictos.
""".strip()

_SCHEMA_B = """{
  "siniestro": {
    "fecha_hora": "<ISO 8601 o null>",
    "municipio": "<municipio de Paraguay o null>",
    "direccion_aproximada": "<calle y barrio o null>",
    "tipo_via": "<CALLE_URBANA | RUTA_NACIONAL | RUTA_DEPARTAMENTAL | ESTACIONAMIENTO | OTRA | null>",
    "condicion_climatica": "<DESPEJADO | LLUVIA | NIEBLA | NOCHE | DESCONOCIDO>",
    "descripcion_dinamica": "<párrafo descriptivo en español formal>"
  },
  "vehiculos": [
    {
      "rol": "<ASEGURADO | TERCERO_1>",
      "marca": null, "modelo": null, "año": null, "matricula": null, "color": null,
      "conductor_nombre": null, "conductor_ci": null,
      "licencia_numero": null, "licencia_categoria": null, "danios_descripcion": null
    }
  ],
  "poliza": {
    "numero": null, "aseguradora": null,
    "vigencia_desde": null, "vigencia_hasta": null,
    "cobertura_tipo": "<RESPONSABILIDAD_CIVIL | TODO_RIESGO | PARCIAL | DESCONOCIDO>",
    "suma_asegurada": null, "franquicia": null
  },
  "documentacion": {
    "poliza_presente": false, "denuncia_policial_presente": false,
    "denuncia_administrativa_presente": false, "pericia_tecnica_presente": false,
    "fotos_evento_cantidad": 0, "cedula_verde_presente": false, "licencia_conductor_presente": false
  },
  "monto_danios": {"estimacion_pericia": null, "moneda_original": "PYG"},
  "conflictos": [],
  "calidad_extraccion": {"score": 0.0, "campos_faltantes_criticos": [], "observaciones": null}
}"""


def paso_b_extraer(resultados_a: list[dict], caso_id: str) -> dict | None:
    """Extrae variables críticas del conjunto de documentos clasificados."""
    bloques = []
    for r in resultados_a:
        if r.get('error'):
            continue
        tipo = r.get('tipo_doc', 'DESCONOCIDO')
        contenido = r.get('contenido_original', '')
        bloques.append(f"--- DOCUMENTO: {r['archivo']} | TIPO: {tipo} ---\n{contenido[:4000]}")

    prompt = f"""Analiza los siguientes documentos del caso {caso_id} y extrae variables estructuradas.

DOCUMENTOS DEL CASO:
{''.join(bloques)}

Devuelve EXCLUSIVAMENTE este JSON:
{_SCHEMA_B}""".strip()

    respuesta = _llamar_gemini(_SYSTEM_B, prompt)
    if respuesta:
        result = _parsear_json(respuesta)
        if result:
            score = result.get('calidad_extraccion', {}).get('score', 0)
            logger.info(f"Paso B — caso {caso_id} | score extracción: {score}")
        return result
    return None


# ---------------------------------------------------------------------------
# PASO C — Análisis normativo y dictamen sugerido
# ---------------------------------------------------------------------------

_SYSTEM_C = """
Eres un analista jurídico especializado en derecho de tránsito del Paraguay.
Analiza los datos de un siniestro y emite una sugerencia de dictamen.
MARCO LEGAL: Ley N° 5016/14 De Tránsito y Seguridad Vial, Ordenanzas municipales, Código Civil Paraguayo Arts. 1833-1847.
REGLAS: Devuelve ÚNICAMENTE el objeto JSON. Sin texto adicional ni Markdown.
NUNCA emitas un dictamen definitivo. Tu salida es una SUGERENCIA para el liquidador.
""".strip()

_LEY_5016 = """
Art. 89 — En condiciones de lluvia, reducir velocidad y aumentar distancia de seguridad.
Art. 139 — La señal de PARE obliga a detener el vehículo y ceder el paso a vehículos en vía preferencial.
Art. 158 — El conductor que infrinja normas y cause accidente es responsable por daños y perjuicios.
Art. 201 — Es obligatorio portar licencia habilitante para la categoría del vehículo que conduce.
""".strip()

_SCHEMA_C = """{
  "dictamen": {
    "dictamen_posible": true,
    "datos_faltantes_para_dictamen": [],
    "responsabilidad_sugerida": "<ASEGURADO_RESPONSABLE | TERCERO_RESPONSABLE | RESPONSABILIDAD_COMPARTIDA | CASO_FORTUITO | INDETERMINADO>",
    "porcentaje_responsabilidad_asegurado": 0,
    "porcentaje_responsabilidad_tercero": 0,
    "cobertura_aplica": true,
    "razon_cobertura": "<explicación>",
    "franquicia_aplica": false,
    "monto_sugerido_liquidar": null,
    "infracciones_detectadas": [
      {
        "infractor": "<ASEGURADO | TERCERO_1>",
        "descripcion_infraccion": "<descripción>",
        "articulo_ley_5016": "<Art. N° o null>",
        "articulo_ordenanza": "<Art. N° y ordenanza o null>"
      }
    ],
    "analisis_narrativo": "<párrafos en español formal y jurídico>",
    "alertas_liquidador": [],
    "confianza_dictamen": 0.0
  }
}"""


def paso_c_dictamen(json_paso_b: dict) -> dict | None:
    """Genera el dictamen sugerido a partir de los datos extraídos."""
    municipio = json_paso_b.get('siniestro', {}).get('municipio', 'Paraguay')

    prompt = f"""Analiza el siguiente caso de siniestro vehicular y emite una sugerencia de dictamen.

DATOS DEL CASO (Paso B):
{json.dumps(json_paso_b, ensure_ascii=False, indent=2)[:8000]}

NORMATIVA APLICABLE (municipio: {municipio}):
{_LEY_5016}

Devuelve EXCLUSIVAMENTE este JSON:
{_SCHEMA_C}""".strip()

    respuesta = _llamar_gemini(_SYSTEM_C, prompt)
    if respuesta:
        result = _parsear_json(respuesta)
        if result:
            responsabilidad = result.get('dictamen', {}).get('responsabilidad_sugerida', '?')
            logger.info(f"Paso C — municipio: {municipio} | responsabilidad: {responsabilidad}")
        return result
    return None


# ---------------------------------------------------------------------------
# Ejecutor principal
# ---------------------------------------------------------------------------

def ejecutar_pipeline(caso_id: str, documentos_db) -> dict:
    """
    Ejecuta el pipeline completo para una carpeta.

    documentos_db: QuerySet o lista de objetos Documento de Django.
    Retorna dict con claves: paso_a, paso_b, paso_c, error.
    """
    # Preparar documentos
    docs = []
    for doc in documentos_db:
        formato = _get_formato(doc.nombre_archivo)
        if doc.contenido_texto:
            contenido = doc.contenido_texto
        else:
            contenido = extraer_texto(doc.archivo.path, doc.nombre_archivo)
            # Guardar el texto extraído para futuras referencias
            if contenido:
                doc.contenido_texto = contenido
                doc.save(update_fields=['contenido_texto'])
        docs.append({
            'nombre_archivo': doc.nombre_archivo,
            'formato': formato,
            'contenido': contenido,
        })

    if not docs:
        return {'error': 'No hay documentos para procesar'}

    try:
        logger.info(f"Pipeline iniciado — caso: {caso_id} | documentos: {len(docs)}")

        resultado_a = paso_a_clasificar(docs)
        if not resultado_a:
            return {'error': 'Paso A: sin resultados de clasificación'}

        resultado_b = paso_b_extraer(resultado_a, caso_id)
        if not resultado_b:
            return {'paso_a': resultado_a, 'error': 'Paso B: fallo en extracción'}

        resultado_c = paso_c_dictamen(resultado_b)
        if not resultado_c:
            return {'paso_a': resultado_a, 'paso_b': resultado_b, 'error': 'Paso C: fallo en dictamen'}

        logger.info(f"Pipeline completado — caso: {caso_id}")
        return {
            'paso_a': resultado_a,
            'paso_b': resultado_b,
            'paso_c': resultado_c,
            'error': None,
        }

    except Exception as e:
        logger.exception(f"Error inesperado en pipeline para caso {caso_id}: {e}")
        return {'error': str(e)}
