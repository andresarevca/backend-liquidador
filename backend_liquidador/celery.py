import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend_liquidador.settings')

app = Celery('backend_liquidador')

# Lee la configuración desde settings.py usando el prefijo CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')

# Descubre tareas automáticamente en todos los INSTALLED_APPS
app.autodiscover_tasks()
