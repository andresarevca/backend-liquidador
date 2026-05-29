# Expone la app Celery para que Django la cargue al iniciar.
from .celery import app as celery_app

__all__ = ('celery_app',)
