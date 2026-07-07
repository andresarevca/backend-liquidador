from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import Carpeta, CorreoRechazado

User = get_user_model()


class CarpetaAislamientoTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username='a@demo.com', email='a@demo.com', password='pass12345!')
        self.user_b = User.objects.create_user(username='b@demo.com', email='b@demo.com', password='pass12345!')
        self.carpeta_a = Carpeta.objects.create(caso_id='CASO-A', usuario=self.user_a, email_remitente='a@demo.com', email_asunto='x')
        self.carpeta_b = Carpeta.objects.create(caso_id='CASO-B', usuario=self.user_b, email_remitente='b@demo.com', email_asunto='y')
        self.client = APIClient()
        self.client.force_authenticate(self.user_a)

    def test_lista_solo_muestra_carpetas_propias(self):
        res = self.client.get('/api/carpetas/')
        self.assertEqual(res.status_code, 200)
        ids = {c['caso_id'] for c in res.data['results']} if 'results' in res.data else {c['caso_id'] for c in res.data}
        self.assertIn('CASO-A', ids)
        self.assertNotIn('CASO-B', ids)

    def test_detalle_de_carpeta_ajena_da_404(self):
        res = self.client.get(f'/api/carpetas/{self.carpeta_b.pk}/')
        self.assertEqual(res.status_code, 404)

    def test_detalle_de_carpeta_propia_ok(self):
        res = self.client.get(f'/api/carpetas/{self.carpeta_a.pk}/')
        self.assertEqual(res.status_code, 200)


class CambiarPasswordTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u@demo.com', email='u@demo.com', password='ViejaClave123')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_password_actual_incorrecta_falla(self):
        res = self.client.post('/api/auth/cambiar-password/', {
            'password_actual': 'incorrecta',
            'password_nueva': 'NuevaClave456',
        })
        self.assertEqual(res.status_code, 400)

    def test_cambio_exitoso(self):
        res = self.client.post('/api/auth/cambiar-password/', {
            'password_actual': 'ViejaClave123',
            'password_nueva': 'NuevaClave456',
        })
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NuevaClave456'))


class AdminNamespaceTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='staff@demo.com', email='staff@demo.com', password='pass12345!', is_staff=True)
        self.liquidador = User.objects.create_user(username='liq@demo.com', email='liq@demo.com', password='pass12345!')
        self.client = APIClient()

    def test_no_staff_no_accede_a_usuarios(self):
        self.client.force_authenticate(self.liquidador)
        res = self.client.get('/api/admin/usuarios/')
        self.assertEqual(res.status_code, 403)

    def test_staff_puede_listar_y_crear_usuarios(self):
        self.client.force_authenticate(self.staff)
        res = self.client.get('/api/admin/usuarios/')
        self.assertEqual(res.status_code, 200)

        res = self.client.post('/api/admin/usuarios/', {
            'email': 'nuevo@demo.com',
            'nombre': 'Nuevo Usuario',
            'password': 'ClaveSegura123',
            'is_staff': False,
        })
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(User.objects.filter(email='nuevo@demo.com').exists())

    def test_staff_puede_ver_metricas(self):
        self.client.force_authenticate(self.staff)
        res = self.client.get('/api/admin/metricas/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('usuarios_activos', res.data)


def _construir_email_bytes(remitente: str, asunto: str) -> bytes:
    return (
        f"From: {remitente}\r\n"
        f"Subject: Siniestro Carpeta {asunto}\r\n"
        f"Content-Type: multipart/mixed; boundary=\"BOUNDARY\"\r\n\r\n"
        f"--BOUNDARY\r\n"
        f"Content-Type: application/pdf\r\n"
        f"Content-Disposition: attachment; filename=\"doc.pdf\"\r\n\r\n"
        f"contenido-pdf\r\n"
        f"--BOUNDARY--\r\n"
    ).encode()


@override_settings(
    IMAP_HOST='imap.test', IMAP_USER='bot@test.com', IMAP_PASSWORD='x',
    IMAP_FOLDER='INBOX', IMAP_SUBJECT_FILTER='',
)
class EmailPollerFiltroRemitenteTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(
            username='registrado@demo.com', email='registrado@demo.com', password='pass12345!',
        )

    def _mock_conn(self, msgs):
        conn = MagicMock()
        conn.search.return_value = ('OK', [b' '.join(str(i).encode() for i in range(1, len(msgs) + 1))])

        def fetch(msg_id, spec):
            idx = int(msg_id) - 1
            return ('OK', [(b'1 (RFC822 {123}', msgs[idx])])

        conn.fetch.side_effect = fetch
        return conn

    @patch('core.email_poller.imaplib.IMAP4_SSL')
    def test_remitente_no_registrado_se_ignora(self, mock_imap):
        email_bytes = _construir_email_bytes('desconocido@fuera.com', 'CASO-X')
        mock_imap.return_value = self._mock_conn([email_bytes])

        from core.email_poller import poll_emails
        creadas = poll_emails()

        self.assertEqual(creadas, [])
        self.assertEqual(Carpeta.objects.count(), 0)
        self.assertEqual(CorreoRechazado.objects.count(), 1)

    @patch('core.email_poller.imaplib.IMAP4_SSL')
    def test_remitente_registrado_crea_carpeta_asociada(self, mock_imap):
        email_bytes = _construir_email_bytes('registrado@demo.com', 'CASO-Y')
        mock_imap.return_value = self._mock_conn([email_bytes])

        from core.email_poller import poll_emails
        creadas = poll_emails()

        self.assertEqual(len(creadas), 1)
        carpeta = Carpeta.objects.get(pk=creadas[0])
        self.assertEqual(carpeta.usuario, self.usuario)
        self.assertEqual(CorreoRechazado.objects.count(), 0)
