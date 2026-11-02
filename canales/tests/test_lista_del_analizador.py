"""
La lista limpia del ANALIZADOR DE CANALES (el programa de la PC que mira cada
señal un minuto y medio): al importarla, las señales que anota como que no
sirven (#KAIROS-NO-SIRVE) se sacan de la app con su motivo, sin borrarse, y
"Volver a mostrar esta señal" las devuelve. Las buenas se importan como
siempre. Una lista que solo trae las que no sirven no crea una importación.
"""

import json
import re
from datetime import timedelta
from html import unescape

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from canales import senales, servicios
from canales.m3u import leer_las_que_no_sirven, leer_m3u
from canales.models import Canal, Fuente, Importacion
from usuarios.models import Rol, Usuario

NO_SIRVEN = ('# Las 2 que no sirven: el panel de Kairos TV las saca de la app al importar esta lista\n'
             '#KAIROS-NO-SIRVE url="http://cae.ejemplo.com/tn.m3u8" motivo="Se cortó a los 40 s y no volvió"\n'
             '#KAIROS-NO-SIRVE url="http://cae.ejemplo.com/a24.ts" motivo="Pantalla negra"\n')
LISTA_LIMPIA = ('#EXTM3U\n'
                '# Kairos TV · analizador de canales · 02/11/2026 18:00 · 1 canales con 1 señales\n'
                '#EXTINF:-1 tvg-name="Canal 26" group-title="Noticias" kairos-seccion="vivo",Canal 26\n'
                'https://anda.ejemplo.com/canal26.m3u8\n' + NO_SIRVEN)
SOLO_LAS_QUE_NO_SIRVEN = '#EXTM3U\n' + NO_SIRVEN


class ListaDelAnalizadorTests(TestCase):

    def setUp(self):
        rol = Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales'])
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=rol))
        self.tn = Canal.objects.create(nombre='TN')
        self.mala = Fuente.objects.create(canal=self.tn, url='http://cae.ejemplo.com/tn.m3u8', prioridad=1)
        self.buena = Fuente.objects.create(canal=self.tn, url='https://anda.ejemplo.com/tn.m3u8', prioridad=2)
        # La misma dirección en otro canal (un "TN HD" repetido): también se quita
        self.repetida = Fuente.objects.create(canal=Canal.objects.create(nombre='TN HD'),
                                              url='http://cae.ejemplo.com/tn.m3u8')
        # La había retirado la limpieza (volvería sola si el servidor la ve andar): ahora queda quitada
        self.retirada = Fuente.objects.create(canal=Canal.objects.create(nombre='A24'),
                                              url='http://cae.ejemplo.com/a24.ts', activa=False,
                                              retirada=timezone.now() - timedelta(days=2))

    def subir(self, texto, **cabeceras):
        return self.client.post(reverse('canales:inicio'), {
            'archivo': SimpleUploadedFile('kairos-noticias-limpia.m3u', texto.encode()), 'descartar_adultos': 'on',
        }, **cabeceras)

    def test_se_leen_aparte_y_no_son_canales(self):
        self.assertEqual(leer_las_que_no_sirven(LISTA_LIMPIA), {
            'http://cae.ejemplo.com/tn.m3u8': 'Se cortó a los 40 s y no volvió',
            'http://cae.ejemplo.com/a24.ts': 'Pantalla negra',
        })
        self.assertEqual([e.url for e in leer_m3u(LISTA_LIMPIA)], ['https://anda.ejemplo.com/canal26.m3u8'])

    def test_se_quitan_con_su_motivo_sin_borrarse(self):
        self.assertEqual(servicios.quitar_las_que_no_sirven(LISTA_LIMPIA), 3)
        for fuente in (self.mala, self.repetida, self.retirada):
            fuente.refresh_from_db()
            self.assertEqual((fuente.activa, fuente.retirada), (False, None))
            self.assertTrue(fuente.motivo_quitada.startswith('El analizador de canales ('))
            self.assertEqual(senales.de_fuente(fuente), 'apagadas')
        self.assertTrue(self.mala.motivo_quitada.endswith('): Se cortó a los 40 s y no volvió'))
        self.assertEqual(senales.detalle(self.retirada, 'apagadas', timezone.now()),
                         self.retirada.motivo_quitada)
        self.buena.refresh_from_db()
        self.assertTrue(self.buena.activa)
        self.assertEqual(Fuente.objects.count(), 4)
        # Otra vez la misma lista: ya estaban quitadas, no se cuentan de nuevo
        self.assertEqual(servicios.quitar_las_que_no_sirven(LISTA_LIMPIA), 0)

    def test_lo_quitado_a_mano_no_se_toca_y_volver_a_mostrar_olvida_el_motivo(self):
        servicios.quitar_fuente(self.mala)
        self.assertEqual(servicios.quitar_las_que_no_sirven(LISTA_LIMPIA), 2)
        self.mala.refresh_from_db()
        self.assertEqual(self.mala.motivo_quitada, '')
        self.assertEqual(senales.detalle(self.mala, 'apagadas', timezone.now()), 'la quitaron a mano')
        servicios.mostrar_fuente(self.retirada)
        self.retirada.refresh_from_db()
        self.assertEqual((self.retirada.activa, self.retirada.motivo_quitada), (True, ''))

    def test_al_subir_la_lista_se_quitan_y_las_buenas_se_importan(self):
        respuesta = self.subir(LISTA_LIMPIA)
        importacion = Importacion.objects.get()
        self.assertEqual(importacion.total, 1)
        self.assertTrue(importacion.de_kairos)
        aviso = [str(m) for m in respuesta.wsgi_request._messages]
        self.assertEqual(len(aviso), 1)
        self.assertIn('La lista trae 3 señal(es) que el analizador de canales dio como que no sirven', aviso[0])
        self.mala.refresh_from_db()
        self.assertFalse(self.mala.activa)

    def test_una_lista_que_solo_trae_las_que_no_sirven(self):
        respuesta = self.subir(SOLO_LAS_QUE_NO_SIRVEN)
        quitadas = reverse('canales:senales') + '?problema=apagadas'
        self.assertRedirects(respuesta, quitadas)
        self.assertFalse(Importacion.objects.exists())
        self.assertFalse(Fuente.objects.filter(url='http://cae.ejemplo.com/tn.m3u8', activa=True).exists())
        # En la pantalla de Señales, con lo que dijo el analizador
        self.assertContains(self.client.get(quitadas), 'Se cortó a los 40 s y no volvió')
        # Subida junto con otras (la página espera JSON): también sin importación
        respuesta = self.subir(SOLO_LAS_QUE_NO_SIRVEN, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(respuesta.json(), {'ok': True, 'url': quitadas, 'total': 0})
        self.assertFalse(Importacion.objects.exists())

    def test_una_lista_sin_canales_ni_nada_sigue_sin_aceptarse(self):
        respuesta = self.subir('#EXTM3U\n# nada\n')
        self.assertContains(respuesta, 'No se encontró ningún canal en el archivo.')

    def test_en_organizar_la_senal_dice_por_que_se_quito(self):
        servicios.quitar_las_que_no_sirven(LISTA_LIMPIA)
        respuesta = self.client.get(reverse('canales:organizar'), {'contenido': 'vivo', 'q': 'A24'})
        crudo = re.search(r'<article class="espejo-tarjeta[^"]*"\s+data-clave="[^"]*"\s+data-datos="([^"]+)"',
                          respuesta.content.decode()).group(1)
        senal, = json.loads(unescape(crudo))['fuentes']
        self.assertTrue(senal['quitada'].endswith('): Pantalla negra'))
        self.assertEqual(senal['retirada'], '')
