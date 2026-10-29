"""
El diagnóstico de por qué un canal no conecta: el último problema que tuvo
cada señal en un aparato, con el detalle técnico que manda la app (qué pasó,
el error del reproductor, a los cuántos segundos), queda guardado y se ve en
Organizar → Detalles, aunque después vuelva a andar.
"""

import json
import re
from html import unescape
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from api import tokens
from canales import recorrido
from canales.models import Canal, Fuente
from canales.verificacion import CAIDA, FUNCIONA, Resultado
from usuarios.models import Rol, Usuario

DETALLE = ('la transmisión terminó: el servidor de la señal la cortó · a los 1,2 s de empezar a conectar · '
           'llegó imagen 1920x1080')


class DiagnosticoTests(TestCase):

    def setUp(self):
        cache.clear()
        self.canal = Canal.objects.create(nombre='ESPN Premium')
        self.fuente = Fuente.objects.create(canal=self.canal, url='http://x/play/a0r2', tipo='directo',
                                            estado=Fuente.Estado.FUNCIONA)
        self.app = APIClient()
        clave, _ = tokens.crear_token(Usuario.objects.create_user('cliente', None, 'x'))
        self.app.credentials(HTTP_AUTHORIZATION=f'Bearer {clave}')

    def avisar(self, resultado_del_servidor, detalle=DETALLE):
        with mock.patch('api.v1.canales.verificar_url', return_value=resultado_del_servidor):
            return self.app.post(reverse('api_v1:fuente_falla', args=[self.fuente.pk]),
                                 {'motivo': 'conexion', 'detalle': detalle}, format='json')

    def test_el_aviso_de_la_app_queda_con_su_detalle(self):
        self.avisar(Resultado(FUNCIONA, tipo='directo'))
        self.fuente.refresh_from_db()
        self.assertEqual(self.fuente.problema_en_aparato, f'no se puede conectar con la señal: {DETALLE}')
        self.assertIsNotNone(self.fuente.problema_en)

    def test_queda_aunque_al_servidor_tambien_le_falle(self):
        self.avisar(Resultado(CAIDA, 'No respondió a tiempo.'))
        self.fuente.refresh_from_db()
        self.assertIn('el servidor de la señal la cortó', self.fuente.problema_en_aparato)

    def test_queda_aunque_despues_vuelva_a_andar(self):
        self.avisar(Resultado(FUNCIONA, tipo='directo'))
        self.app.post(reverse('api_v1:fuente_estabilidad', args=[self.fuente.pk]), {'segundos': 600, 'cortes': 0},
                      format='json')
        self.fuente.refresh_from_db()
        self.assertEqual(self.fuente.falla_en_aparatos, '')   # se perdonó...
        self.assertIn('la cortó', self.fuente.problema_en_aparato)   # ...pero el diagnóstico queda

    def test_un_detalle_largo_se_recorta(self):
        self.avisar(Resultado(FUNCIONA, tipo='directo'), detalle='x' * 900)
        self.fuente.refresh_from_db()
        # La app manda hasta 500; con el motivo adelante, nunca pasa de lo que entra en la base (600)
        self.assertEqual(self.fuente.problema_en_aparato, 'no se puede conectar con la señal: ' + 'x' * 500)

    def avisar_del_aparato(self, quien):
        """Un aviso de la app 1.2.40+ desde otra sesión: el video llegó y ese aparato no lo mostró."""
        app = APIClient()
        clave, _ = tokens.crear_token(Usuario.objects.create_user(quien, None, 'x'))
        app.credentials(HTTP_AUTHORIZATION=f'Bearer {clave}')
        return app.post(reverse('api_v1:fuente_falla', args=[self.fuente.pk]),
                        {'motivo': 'aparato', 'detalle': 'el video llegó y el decodificador del aparato no lo mostró · '
                                                         'deco OMX.MTK.VIDEO.DECODER.AVC: entraron 8, salieron 0 · '
                                                         '[app 1.2.40 · Lenovo TB-X505F · Android 10]'},
                        format='json')

    def test_lo_que_es_del_aparato_queda_en_el_diagnostico_pero_no_esconde_la_senal(self):
        with mock.patch('api.v1.canales.verificar_url') as verificar_url:
            # Aunque avisen muchos aparatos (dos avisos de otra cosa la esconden)
            estados = [self.avisar_del_aparato(quien).json()['estado'] for quien in ('a', 'b', 'c')]
        self.assertEqual(estados, [FUNCIONA] * 3)
        verificar_url.assert_not_called()   # no es la señal: no hace falta volver a probarla
        self.fuente.refresh_from_db()
        self.assertIsNone(self.fuente.oculta_desde)
        self.assertEqual(self.fuente.avisos_de_aparatos, 0)
        self.assertTrue(self.fuente.problema_en_aparato.startswith('ese aparato no pudo mostrar el video'))
        self.assertIn('Lenovo TB-X505F · Android 10', self.fuente.problema_en_aparato)
        # En el historial, como "un aparato no la lee" (no cuenta como falla)
        self.assertEqual(self.fuente.historial[-1:], 'f')
        self.assertEqual(self.fuente.fallas_seguidas, 0)
        self.assertFalse(self.fuente.oculta_por_aparatos)

    def test_el_modo_revision_tambien_entiende_lo_del_aparato(self):
        recorrido.anotar([{'id': self.fuente.pk, 'anduvo': False, 'motivo': 'aparato',
                           'detalle': 'entraron 8, salieron 0'}])
        self.fuente.refresh_from_db()
        self.assertEqual(self.fuente.historial[-1:], 'f')
        self.assertEqual(self.fuente.fallas_seguidas, 0)

    def test_el_modo_revision_tambien_lo_anota(self):
        recorrido.anotar([{'id': self.fuente.pk, 'anduvo': False, 'motivo': 'rechazo',
                           'detalle': 'Response code: 403 · a los 0,4 s de empezar a conectar'}])
        self.fuente.refresh_from_db()
        self.assertEqual(self.fuente.problema_en_aparato, 'el servidor de la señal rechaza al aparato: modo revisión: '
                                                          'Response code: 403 · a los 0,4 s de empezar a conectar')

    def test_se_ve_en_el_detalle_de_organizar(self):
        self.avisar(Resultado(FUNCIONA, tipo='directo'))
        rol = Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales'])
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=rol))
        pagina = self.client.get(reverse('canales:organizar'), {'contenido': 'vivo'}).content.decode()
        crudo = re.search(r'<article class="espejo-tarjeta[^"]*"\s+data-clave="[^"]*"\s+data-datos="([^"]+)"', pagina).group(1)
        senal = json.loads(unescape(crudo))['fuentes'][0]
        self.assertTrue(senal['problema'].startswith('Último problema en un aparato ('))
        self.assertIn('el servidor de la señal la cortó', senal['problema'])
