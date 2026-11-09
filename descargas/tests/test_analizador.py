"""
El analizador de canales para PC: solo superusuarios lo ven, lo suben (de a pedazos) y lo bajan; los analizadores
instalados preguntan por la última versión con la huella de su instalador. Los archivos van a una carpeta temporal.
"""

import hashlib
import shutil
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from descargas import analizador
from descargas.models import PcConAnalizador, VersionAnalizador
from usuarios.models import Rol, Usuario

CARPETA = tempfile.mkdtemp(prefix='kairos-privado-')
INSTALADOR = b'MZ' + bytes(range(256)) * 300   # ~77 KB: un "programa" de mentira
ID = 'ab' * 16


@override_settings(ARCHIVOS_PRIVADOS=Path(CARPETA))
class AnalizadorParaPcTests(TestCase):

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(CARPETA, ignore_errors=True)

    def setUp(self):
        self.admin = Usuario.objects.create_superuser('admin', 'admin@test.com', 'x')
        self.revendedor = Usuario.objects.create_user('juan', None, 'x', rol=Rol.objects.create(nombre='Revendedor'))

    def subir(self, version='2026.11.9.1530', contenido=INSTALADOR, pedazo=30000, identificador=ID):
        """Como subir_analizador.js: de a pedazos y al final publicar."""
        for desde in range(0, len(contenido), pedazo):
            respuesta = self.client.post(reverse('descargas:analizador_pedazo'), {
                'id': identificador, 'desde': desde,
                'pedazo': SimpleUploadedFile('pedazo', contenido[desde:desde + pedazo])})
            self.assertEqual(respuesta.status_code, 200, respuesta.content)
            self.assertEqual(respuesta.json()['recibido'], min(desde + pedazo, len(contenido)))
        return self.client.post(reverse('descargas:analizador_publicar'),
                                {'id': identificador, 'version': version, 'notas': 'Arreglos'})

    def preguntar(self, huella, instalacion='1' * 8 + '-2222-3333-4444-' + '5' * 12, version='2026.11.9.1530',
                  pc='PC-OFICINA', ruta='/api/v1/analizador/'):
        return self.client.get(ruta, HTTP_X_KAIROS_INSTALADOR=huella, HTTP_X_KAIROS_INSTALACION=instalacion,
                               HTTP_X_KAIROS_VERSION=version, HTTP_X_KAIROS_PC=pc)

    # ── Quién lo ve ──

    def test_solo_los_superusuarios_ven_el_analizador(self):
        self.client.force_login(self.revendedor)
        respuesta = self.client.get(reverse('descargas:pagina') + '?ver=analizador')
        self.assertContains(respuesta, 'Cómo instalarla')          # la página de la app, como siempre
        self.assertNotContains(respuesta, 'Analizador para PC')
        self.assertNotContains(respuesta, 'Analizador de canales')
        self.assertEqual(self.client.post(reverse('descargas:analizador_pedazo'), {'id': ID, 'desde': 0}).status_code,
                         403)
        self.assertEqual(self.client.get(reverse('descargas:analizador_descargar')).status_code, 403)
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse('descargas:pagina') + '?ver=analizador')
        self.assertContains(respuesta, 'Analizador para PC')
        self.assertContains(respuesta, 'Publicar una versión nueva')
        self.assertContains(respuesta, 'Ninguna todavía')

    def test_sin_sesion_pide_entrar(self):
        self.assertEqual(self.client.get(reverse('descargas:analizador_descargar')).status_code, 302)

    # ── Subir ──

    def test_se_sube_de_a_pedazos_y_queda_publicada(self):
        self.client.force_login(self.admin)
        respuesta = self.subir()
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertEqual(respuesta.json()['url'], reverse('descargas:pagina') + '?ver=analizador')
        version = VersionAnalizador.objects.get()
        self.assertEqual((version.version, version.tamanio, version.sha256, version.subida_por),
                         ('2026.11.9.1530', len(INSTALADOR), hashlib.sha256(INSTALADOR).hexdigest(), self.admin))
        guardado = Path(CARPETA) / 'analizador' / 'KairosAnalizador-2026.11.9.1530.exe'
        self.assertEqual(guardado.read_bytes(), INSTALADOR)
        self.assertEqual(list((Path(CARPETA) / 'analizador' / 'subiendo').glob('*.part')), [])
        descarga = self.client.get(reverse('descargas:analizador_descargar'))
        self.assertEqual(b''.join(descarga.streaming_content), INSTALADOR)
        self.assertIn('KairosAnalizador-2026.11.9.1530.exe', descarga['Content-Disposition'])

    def test_un_pedazo_repetido_se_reemplaza_y_uno_salteado_no_se_acepta(self):
        self.client.force_login(self.admin)
        url = reverse('descargas:analizador_pedazo')
        self.client.post(url, {'id': ID, 'desde': 0, 'pedazo': SimpleUploadedFile('p', INSTALADOR[:1000])})
        otra_vez = self.client.post(url, {'id': ID, 'desde': 0, 'pedazo': SimpleUploadedFile('p', INSTALADOR[:1000])})
        self.assertEqual(otra_vez.json()['recibido'], 1000)
        salteado = self.client.post(url, {'id': ID, 'desde': 5000, 'pedazo': SimpleUploadedFile('p', b'x')})
        self.assertEqual(salteado.status_code, 400)
        self.assertIn('Se perdió un pedazo', salteado.json()['error'])

    def test_rechaza_lo_que_no_es_un_programa_y_las_versiones_repetidas(self):
        self.client.force_login(self.admin)
        respuesta = self.subir(contenido=b'hola, no soy un programa' * 100)
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('no es un programa de Windows', respuesta.json()['error'])
        self.assertEqual(self.subir(version='nueva').json()['error'][:31], 'La versión tiene que ser como l')
        self.assertEqual(self.subir().status_code, 200)
        self.assertIn('Ya se subió la versión', self.subir(contenido=INSTALADOR + b'1').json()['error'])
        self.assertIn('ya está subido', self.subir(version='2026.11.9.1600').json()['error'])
        self.assertEqual(VersionAnalizador.objects.count(), 1)

    def test_la_version_sale_del_nombre_del_archivo(self):
        self.assertEqual(analizador.version_del_nombre('KairosAnalizador-2026.11.9.1530.exe'), '2026.11.9.1530')
        self.assertEqual(analizador.version_del_nombre('KairosAnalizador-2026.11.9.1530 (1).exe'), '2026.11.9.1530')
        self.assertEqual(analizador.version_del_nombre('setup.exe'), '')

    # ── Los analizadores instalados ──

    def test_el_analizador_instalado_pregunta_con_la_huella_de_su_instalador(self):
        self.client.force_login(self.admin)
        self.subir()
        self.subir(version='2026.11.10.0900', contenido=INSTALADOR + b'nueva', identificador='cd' * 16)
        self.client.logout()
        vieja = VersionAnalizador.objects.get(version='2026.11.9.1530')
        nueva = VersionAnalizador.objects.get(version='2026.11.10.0900')
        datos = self.preguntar(vieja.sha256).json()
        self.assertEqual((datos['version'], datos['sha256'], datos['tamanio']),
                         (nueva.version, nueva.sha256, nueva.tamanio))
        self.assertTrue(datos['descarga'].endswith(f'/api/v1/analizador/descargar/{nueva.pk}/'))
        pc = PcConAnalizador.objects.get()
        self.assertEqual((pc.nombre, pc.version), ('PC-OFICINA', '2026.11.9.1530'))
        # La baja con la misma huella
        descarga = self.preguntar(vieja.sha256, ruta=datos['descarga'].split('testserver')[1])
        self.assertEqual(b''.join(descarga.streaming_content), INSTALADOR + b'nueva')
        # Ya actualizada, pregunta con la huella nueva y queda al día
        self.preguntar(nueva.sha256, version='2026.11.10.0900')
        pc.refresh_from_db()
        self.assertEqual(pc.version, '2026.11.10.0900')
        self.assertTrue(analizador.al_dia(pc, VersionAnalizador.ultima()))
        self.assertEqual(PcConAnalizador.objects.count(), 1)

    def test_sin_una_huella_del_panel_no_se_le_dice_nada(self):
        self.client.force_login(self.admin)
        self.subir()
        self.client.logout()
        for huella in ('', 'f' * 64, 'no-es-una-huella'):
            respuesta = self.preguntar(huella)
            self.assertEqual(respuesta.status_code, 403)
            self.assertIn('no salió de un instalador del panel', respuesta.json()['detail'])
        version = VersionAnalizador.objects.get()
        self.assertEqual(self.preguntar('f' * 64, ruta=f'/api/v1/analizador/descargar/{version.pk}/').status_code,
                         403)
        self.assertEqual(PcConAnalizador.objects.count(), 0)

    def test_una_pc_desconectada_ya_no_recibe_versiones(self):
        self.client.force_login(self.admin)
        self.subir()
        huella = VersionAnalizador.objects.get().sha256
        self.preguntar(huella)
        pc = PcConAnalizador.objects.get()
        self.client.post(reverse('descargas:analizador_pc', args=[pc.pk]))
        respuesta = self.preguntar(huella)
        self.assertEqual(respuesta.status_code, 403)
        self.assertIn('desconectada', respuesta.json()['detail'])
        self.client.post(reverse('descargas:analizador_pc', args=[pc.pk]))
        self.assertEqual(self.preguntar(huella).status_code, 200)

    def test_instala_la_publicada_de_numero_mas_alto(self):
        self.client.force_login(self.admin)
        self.subir('2026.11.10.0900')
        self.subir('2026.11.9.1530', contenido=INSTALADOR + b'vieja', identificador='cd' * 16)
        self.assertEqual(VersionAnalizador.ultima().version, '2026.11.10.0900')   # aunque se subió después
        nueva = VersionAnalizador.objects.get(version='2026.11.10.0900')
        self.client.post(reverse('descargas:analizador_publicada', args=[nueva.pk]))   # ocultarla
        self.assertEqual(VersionAnalizador.ultima().version, '2026.11.9.1530')
        self.client.logout()
        # La oculta ya no se anuncia ni se baja, pero su huella sigue valiendo (las PCs que ya la tienen)
        self.assertEqual(self.preguntar(nueva.sha256).json()['version'], '2026.11.9.1530')
        self.assertEqual(self.preguntar(nueva.sha256, ruta=f'/api/v1/analizador/descargar/{nueva.pk}/').status_code,
                         404)

    def test_la_pagina_muestra_las_pcs_y_si_estan_al_dia(self):
        self.client.force_login(self.admin)
        self.subir()
        self.subir(version='2026.11.10.0900', contenido=INSTALADOR + b'nueva', identificador='cd' * 16)
        huella = VersionAnalizador.objects.get(version='2026.11.9.1530').sha256
        self.preguntar(huella, pc='PC-OFICINA')
        self.preguntar(huella, instalacion='9' * 8 + '-2222-3333-4444-' + '5' * 12, pc='NOTEBOOK',
                       version='2026.11.10.0900')
        respuesta = self.client.get(reverse('descargas:pagina') + '?ver=analizador')
        self.assertContains(respuesta, 'PC-OFICINA')
        self.assertContains(respuesta, 'Por actualizarse')
        self.assertContains(respuesta, 'NOTEBOOK')
        self.assertContains(respuesta, 'Al día')
