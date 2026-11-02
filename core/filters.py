"""Filtros de listado por query params (?search=, ?estado=) compartidos por las vistas."""

from django.db.models import Q

from .models import Carpeta

ESTADOS_VALIDOS = {valor for valor, _ in Carpeta.ESTADO_CHOICES}


def _terminos(params):
    return (params.get('search') or '').split()


def filtrar_carpetas(qs, params, extra_campos=()):
    """Aplica ?estado= y ?search= (cada palabra debe coincidir en algún campo)."""
    estado = params.get('estado')
    if estado in ESTADOS_VALIDOS:
        qs = qs.filter(estado=estado)
    campos = ('caso_id', 'email_remitente', 'email_asunto', *extra_campos)
    for termino in _terminos(params):
        qs = qs.filter(_any(campos, termino))
    return qs


def filtrar_documentos(qs, params):
    campos = ('nombre_archivo', 'tipo_doc', 'carpeta__caso_id')
    for termino in _terminos(params):
        qs = qs.filter(_any(campos, termino))
    return qs


def _any(campos, termino):
    cond = Q()
    for campo in campos:
        cond |= Q(**{f'{campo}__icontains': termino})
    return cond
