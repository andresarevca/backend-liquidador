import logging

from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_delete

logger = logging.getLogger(__name__)


def _limpiar_corpus_de_usuario(sender, instance, **kwargs):
    """Al eliminar un usuario, borra su corpus privado y sus precedentes del vector store."""
    from .ia_client import eliminar_dueno_corpus

    try:
        eliminar_dueno_corpus(str(instance.pk))
    except Exception:
        # No bloquear el borrado del usuario si el servicio de IA no responde.
        logger.warning("No se pudo limpiar el corpus del usuario %s", instance.pk, exc_info=True)


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        post_delete.connect(
            _limpiar_corpus_de_usuario,
            sender=settings.AUTH_USER_MODEL,
            dispatch_uid='limpiar_corpus_de_usuario',
        )
