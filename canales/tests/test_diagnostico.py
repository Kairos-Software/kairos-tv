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
        self.avisar(Resultado(FUNCIONA, tipo='directo'), detalle='x' * 600)
        self.fuente.refresh_from_db()
        # La app manda hasta 250; con el motivo adelante, nunca pasa de lo que entra en la base (300)
        self.assertEqual(self.fuente.problema_en_aparato, 'no se puede conectar con la señal: ' + 'x' * 250)

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
        crudo = re.search(r'class="espejo-editar" data-datos="([^"]+)"', pagina).group(1)
        senal = json.loads(unescape(crudo))['fuentes'][0]
        self.assertTrue(senal['problema'].startswith('Último problema en un aparato ('))
        self.assertIn('el servidor de la señal la cortó', senal['problema'])
