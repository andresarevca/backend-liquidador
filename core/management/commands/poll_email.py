from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Recupera carpetas nuevas desde el correo IMAP y lanza el pipeline IA.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-pipeline',
            action='store_true',
            help='Solo descarga los correos sin lanzar el pipeline IA.',
        )

    def handle(self, *args, **options):
        from core.email_poller import poll_emails
        from core.tasks import procesar_carpeta

        self.stdout.write('Verificando correos nuevos...')
        ids = poll_emails()

        if not ids:
            self.stdout.write('No se encontraron carpetas nuevas.')
            return

        self.stdout.write(self.style.SUCCESS(f'{len(ids)} carpeta(s) nueva(s) creada(s).'))

        if options['no_pipeline']:
            self.stdout.write('Pipeline omitido (--no-pipeline).')
            return

        for pk in ids:
            procesar_carpeta.delay(pk)
            self.stdout.write(f'  Pipeline encolado para carpeta {pk}')
