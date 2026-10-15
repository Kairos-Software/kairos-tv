"""
Organizar contenido: al elegir algo se ve TODO lo suyo (panel de detalles), y
se puede borrar UNA señal de un canal (la que no anda) sin tocar las otras.
"""

import json
import re
from datetime import timedelta
from html import unescape

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from actividad.models import RegistroActividad
from canales.models import Canal, Fuente
from usuarios.models import Rol, Usuario


class DetalleYBorrarFuenteTests(TestCase):

    def setUp(self):
        rol = Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales'])
        self.marcos = Usuario.objects.create_user('marcos', None, 'x', rol=rol, first_name='Marcos', last_name='López')
        self.client.force_login(self.marcos)
        self.canal = Canal(nombre='Disney', idioma='es', pais='AR', tvg_id='Disney.ar')
        self.canal.marcar_autor(self.marcos)
        self.canal.save()
        self.buena = Fuente.objects.create(canal=self.canal, url='https://anda.ejemplo.com/disney.m3u8', prioridad=1,
                                           estado=Fuente.Estado.FUNCIONA, origen='lista_buena.m3u', calidad='1080p · H.264',
                                           segundos_en_aparatos=4 * 3600, cortes_en_aparatos=0, proporcion=1.78)
        self.mala = Fuente.objects.create(canal=self.canal, url='https://caida.ejemplo.com/disney.m3u8', prioridad=2,
                                          estado=Fuente.Estado.CAIDA, error='No respondió a tiempo.',
                                          origen='lista_vieja.m3u', falla_en_aparatos='no se puede conectar',
                                          oculta_hasta=timezone.now() + timedelta(hours=3))

    def datos_de_la_tarjeta(self, respuesta):
        """El JSON que el panel de detalles lee del botón Editar de la tarjeta."""
        crudo = re.search(r'class="espejo-editar" data-datos="([^"]+)"', respuesta.content.decode()).group(1)
        return json.loads(unescape(crudo))

    def test_con_detalles_se_ve_todo_lo_suyo(self):
        respuesta = self.client.get(reverse('canales:organizar'), {'contenido': 'vivo'})
        self.assertContains(respuesta, 'id="detalle-lateral"')
        self.assertContains(respuesta, 'js/organizar_detalle.js')
        # Elegir tarjetas no abre el panel (molestaba al trabajar con varias): lo abre «Detalles»
        self.assertContains(respuesta, 'class="espejo-ver"')
        self.assertContains(respuesta, '<strong>Detalles</strong> muestra al costado')
        self.assertNotContains(respuesta, 'data-detalle-varios')
        datos = self.datos_de_la_tarjeta(respuesta)
        filas = dict(datos['datos'])
        self.assertEqual(filas['Idioma'], 'Español')
        self.assertEqual(filas['ID de guía (tvg-id)'], 'Disney.ar')
        self.assertIn('por Marcos López', filas['Cargado'])
        buena, mala = datos['fuentes']
        # En el orden en que las prueba la app, con su link completo y de qué lista salió
        self.assertEqual((buena['orden'], buena['url'], buena['origen']),
                         (1, 'https://anda.ejemplo.com/disney.m3u8', 'lista_buena.m3u'))
        self.assertEqual(buena['calidad'], '1080p · H.264')
        self.assertEqual(buena['aparatos'], 'se vio 4,0 h · no se corta · imagen panorámica')
        self.assertTrue(buena['borrable'])
        self.assertIn('Oculta hasta el', mala['oculta'])
        self.assertEqual(mala['error'], 'No respondió a tiempo.')

    def test_borrar_una_senal_deja_las_otras_y_vuelve_con_el_detalle_abierto(self):
        volver = reverse('canales:organizar') + '?contenido=vivo'
        respuesta = self.client.post(reverse('canales:fuente_borrar', args=[self.mala.pk]), {'volver': volver})
        self.assertRedirects(respuesta, f'{volver}#ver-{self.canal.pk}', fetch_redirect_response=False)
        self.assertEqual(list(self.canal.fuentes.values_list('pk', flat=True)), [self.buena.pk])
        # Queda anotado en la actividad, con el link (por si hay que volver a ponerlo)
        self.assertTrue(RegistroActividad.objects.filter(descripcion__contains='caida.ejemplo.com').exists())

    def test_si_era_la_unica_avisa_que_no_se_va_a_ver(self):
        self.mala.delete()
        respuesta = self.client.post(reverse('canales:fuente_borrar', args=[self.buena.pk]), follow=True)
        self.assertContains(respuesta, 'Era la única')
        self.assertTrue(Canal.objects.filter(pk=self.canal.pk).exists())   # el canal queda

    def test_desde_la_pagina_del_canal_vuelve_a_ella(self):
        pagina = reverse('canales:canal_editar', args=[self.canal.pk])
        self.assertContains(self.client.get(pagina), reverse('canales:fuente_borrar', args=[self.mala.pk]))
        respuesta = self.client.post(reverse('canales:fuente_borrar', args=[self.mala.pk]), {'despues': pagina})
        self.assertRedirects(respuesta, pagina, fetch_redirect_response=False)

    def test_no_vuelve_a_otro_sitio(self):
        respuesta = self.client.post(reverse('canales:fuente_borrar', args=[self.mala.pk]),
                                     {'despues': 'https://otro-sitio.com/'})
        self.assertTrue(respuesta.url.startswith(reverse('canales:organizar')))

    def test_sin_permiso_no_se_borra(self):
        self.client.force_login(Usuario.objects.create_user('mirón', None, 'x', rol=Rol.objects.create(
            nombre='Ver', permisos=['ver_canales'])))
        self.assertEqual(self.client.post(reverse('canales:fuente_borrar', args=[self.mala.pk])).status_code, 403)
        self.assertEqual(self.canal.fuentes.count(), 2)

    def test_en_una_serie_se_borra_desde_cada_capitulo(self):
        capitulo = Canal.objects.create(nombre='Bluey S01 E01', contenido='serie')
        fuente = Fuente.objects.create(canal=capitulo, url='https://series.ejemplo.com/1.mp4', estado=Fuente.Estado.FUNCIONA)
        organizar = self.client.get(reverse('canales:organizar'), {'contenido': 'serie'})
        self.assertFalse(self.datos_de_la_tarjeta(organizar)['fuentes'][0]['borrable'])
        serie = self.client.get(reverse('canales:serie_detalle'), {'nombre': 'Bluey'})
        self.assertContains(serie, reverse('canales:fuente_borrar', args=[fuente.pk]))
