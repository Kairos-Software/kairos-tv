"""
La app de Kairos TV para PC (Windows): como la APK, la baja cualquiera y la ven todos los del panel; la suben (de a
pedazos, como el analizador) los que publican la app; las apps instaladas preguntan por la última para
actualizarse solas (/api/v1/app-pc/). Los archivos van a una carpeta temporal.
"""

import hashlib
import shutil
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from descargas import instaladores
from descargas.models import VersionPc
from usuarios.models import Rol, Usuario

CARPETA = tempfile.mkdtemp(prefix='kairos-privado-')
INSTALADOR = b'MZ' + bytes(range(256)) * 300   # ~77 KB: un "programa" de mentira
ID = 'cd' * 16


@override_settings(ARCHIVOS_PRIVADOS=Path(CARPETA))
class AppParaPcTests(TestCase):

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(CARPETA, ignore_errors=True)

    def setUp(self):
        self.admin = Usuario.objects.create_superuser('admin', 'admin@test.com', 'x')
        self.revendedor = Usuario.objects.create_user('juan', None, 'x', rol=Rol.objects.create(nombre='Revendedor'))

    def subir(self, version='2026.11.10.1530', contenido=INSTALADOR, pedazo=30000, identificador=ID):
        """Como subir_instalador.js: de a pedazos y al final publicar."""
        for desde in range(0, len(contenido), pedazo):
            respuesta = self.client.post(reverse('descargas:pc_pedazo'), {
                'id': identificador, 'desde': desde,
                'pedazo': SimpleUploadedFile('pedazo', contenido[desde:desde + pedazo])})
            self.assertEqual(respuesta.status_code, 200, respuesta.content)
        return self.client.post(reverse('descargas:pc_publicar'),
                                {'id': identificador, 'version': version, 'notas': 'Mouse y pantalla completa'})

    def test_el_revendedor_la_ve_y_la_baja_pero_no_la_sube(self):
        self.client.force_login(self.revendedor)
        respuesta = self.client.get(reverse('descargas:pagina'))
        self.assertContains(respuesta, 'App para PC')                      # la pestaña, para todos
        self.assertNotContains(respuesta, 'Analizador para PC')            # esa sigue siendo de los superusuarios
        respuesta = self.client.get(reverse('descargas:pagina') + '?ver=pc')
        self.assertContains(respuesta, 'Cómo instalarla')
        self.assertNotContains(respuesta, 'Publicar una versión nueva')
        self.assertEqual(self.client.post(reverse('descargas:pc_pedazo'), {'id': ID, 'desde': 0}).status_code, 403)
        self.assertEqual(self.client.post(reverse('descargas:pc_publicar'), {'id': ID}).status_code, 403)

    def test_se_sube_de_a_pedazos_y_se_baja_sin_sesion(self):
        self.client.force_login(self.admin)
        respuesta = self.subir()
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertEqual(respuesta.json()['url'], reverse('descargas:pagina') + '?ver=pc')
        version = VersionPc.objects.get()
        self.assertEqual(version.sha256, hashlib.sha256(INSTALADOR).hexdigest())
        self.assertEqual(version.tamanio, len(INSTALADOR))
        self.assertTrue((Path(CARPETA) / 'pc' / 'KairosTV-2026.11.10.1530.exe').exists())   # en privado/, no en media/

        self.client.logout()
        descarga = self.client.get('/descargar/pc/')
        self.assertEqual(descarga.status_code, 200)
        self.assertIn('KairosTV-2026.11.10.1530.exe', descarga['Content-Disposition'])
        self.assertEqual(b''.join(descarga.streaming_content), INSTALADOR)

    def test_sin_versiones_da_404(self):
        self.assertEqual(self.client.get('/descargar/pc/').status_code, 404)

    def test_rechaza_lo_que_no_es_un_programa_y_las_versiones_repetidas(self):
        self.client.force_login(self.admin)
        respuesta = self.subir(contenido=b'hola' * 100)
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('no es un programa de Windows', respuesta.json()['error'])
        self.subir()
        respuesta = self.subir(contenido=INSTALADOR + b'x', identificador='ef' * 16)
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('Ya se subió la versión', respuesta.json()['error'])
        self.assertEqual(VersionPc.objects.count(), 1)

    def test_la_version_sale_del_nombre_del_archivo(self):
        self.assertEqual(instaladores.version_del_nombre(instaladores.APP_PC, 'KairosTV-2026.11.10.1530.exe'),
                         '2026.11.10.1530')
        self.assertEqual(instaladores.version_del_nombre(instaladores.APP_PC, 'KairosTV-2026.11.10.1530 (1).exe'),
                         '2026.11.10.1530')
        self.assertEqual(instaladores.version_del_nombre(instaladores.APP_PC, 'KairosAnalizador-2026.11.9.1.exe'), '')

    def test_la_api_dice_cual_es_la_ultima_para_actualizarse_sola(self):
        """GET /api/v1/app-pc/: lo que consulta la app instalada (sin sesión), con la huella para revisar la bajada."""
        self.assertEqual(self.client.get('/api/v1/app-pc/').json(), {'version': None})
        self.client.force_login(self.admin)
        self.subir('2026.11.10.1530')
        otro = INSTALADOR + b'otra'
        self.subir('2026.11.11.900', contenido=otro, identificador='ef' * 16)
        nueva = VersionPc.objects.get(version='2026.11.11.900')
        self.client.logout()
        datos = self.client.get('/api/v1/app-pc/').json()
        self.assertEqual(datos['version'], '2026.11.11.900')   # 900 < 1530, pero el día 11 es más nuevo
        self.assertEqual(datos['sha256'], hashlib.sha256(otro).hexdigest())
        self.assertEqual(datos['tamanio'], len(otro))
        self.assertTrue(datos['descarga'].endswith(f'/descargar/pc/{nueva.pk}/'))
        self.assertEqual(self.client.get(datos['descarga']).status_code, 200)

        # Oculta: vuelve a anunciar la anterior, y la oculta ya no se baja
        self.client.force_login(self.admin)
        self.client.post(reverse('descargas:pc_publicada', args=[nueva.pk]))
        self.client.logout()
        self.assertEqual(self.client.get('/api/v1/app-pc/').json()['version'], '2026.11.10.1530')
        self.assertEqual(self.client.get(reverse('descargas:descargar_pc_version', args=[nueva.pk])).status_code, 404)
