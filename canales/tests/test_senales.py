"""
Cada SEÑAL por separado: la limpieza retira las que no andan de un canal que
sigue andando con otras (y las devuelve si vuelven a andar), y desde
Organizar → Detalles se puede quitar, volver a mostrar o probar UNA señal,
aunque el canal se vea. Para revisar junta las retiradas para borrarlas.
"""

import json
import re
from datetime import timedelta
from html import unescape
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from canales import bandeja, recorrido, salud, servicios
from canales.models import Canal, Fuente
from canales.verificacion import CAIDA, FUNCIONA, Resultado
from usuarios.models import Rol, Usuario

Estado = Fuente.Estado
AHORA = timezone.now()


def _muerta(**datos):
    return {'estado': Estado.CAIDA, 'falla_desde': AHORA - timedelta(days=9), 'fallas_seguidas': salud.FALLAS_PARA_QUITAR,
            'por_que_falla': 'no_existe', **datos}


def _anda(**datos):
    return {'estado': Estado.FUNCIONA, 'anduvo': AHORA, 'historial': '+', **datos}


class Base(TestCase):

    def setUp(self):
        cache.clear()

    def canal(self, nombre, *fuentes, **datos):
        canal = Canal.objects.create(nombre=nombre, **datos)
        for numero, campos in enumerate(fuentes, start=1):
            Fuente.objects.create(canal=canal, url=f'https://x/{canal.pk}/{numero}.m3u8', prioridad=numero,
                                  origen=campos.pop('origen', 'lista.m3u'), **campos)
        return canal

    @staticmethod
    def senales(canal):
        return list(canal.fuentes.order_by('prioridad'))


class LimpiezaDeSenalesTests(Base):

    def test_retira_la_muerta_si_el_canal_tiene_otra_que_anda(self):
        canal = self.canal('Telefe', _anda(), _muerta(), _muerta(fallas_seguidas=2))   # la 3: todavía no
        resultado = salud.limpiar(AHORA)
        self.assertEqual(resultado['senales_retiradas'], ['Telefe'])
        buena, muerta, todavia = self.senales(canal)
        self.assertEqual((buena.activa, muerta.activa, todavia.activa), (True, False, True))
        self.assertEqual(muerta.retirada, AHORA)
        canal.refresh_from_db()
        self.assertTrue(canal.activo)   # el canal sigue

    def test_si_estan_todas_muertas_se_quita_el_canal_no_se_retiran(self):
        canal = self.canal('Muerto', _muerta(), _muerta())
        resultado = salud.limpiar(AHORA)
        self.assertEqual((resultado['quitados'], resultado['senales_retiradas']), (['Muerto'], []))
        self.assertTrue(all(f.activa for f in self.senales(canal)))

    def test_si_vuelve_a_andar_vuelve_sola_y_lo_apagado_a_mano_no(self):
        canal = self.canal('Telefe', _anda(), _muerta(), _muerta(activa=False))
        salud.limpiar(AHORA)
        _, retirada, a_mano = self.senales(canal)
        for fuente in (retirada, a_mano):
            servicios.aplicar_resultado(fuente, Resultado(FUNCIONA, tipo='hls'), AHORA)
            fuente.save()
        self.assertEqual(salud.limpiar(AHORA)['senales_devueltas'], 1)
        retirada.refresh_from_db()
        a_mano.refresh_from_db()
        self.assertEqual((retirada.activa, retirada.retirada), (True, None))
        self.assertFalse(a_mano.activa)

    def test_si_la_que_quedaba_tambien_muere_se_quita_el_canal_y_vuelve_con_cualquiera(self):
        canal = self.canal('Telefe', _anda(), _muerta())
        salud.limpiar(AHORA)
        buena, retirada = self.senales(canal)
        Fuente.objects.filter(pk=buena.pk).update(**_muerta())
        self.assertEqual(salud.limpiar(AHORA)['quitados'], ['Telefe'])
        # Revive la que estaba retirada: vuelve ella y vuelve el canal
        servicios.aplicar_resultado(retirada, Resultado(FUNCIONA, tipo='hls'), AHORA)
        retirada.save()
        self.assertEqual(salud.limpiar(AHORA)['volvieron'], ['Telefe'])
        retirada.refresh_from_db()
        self.assertTrue(retirada.activa)

    def test_volver_a_mostrar_el_canal_devuelve_sus_senales_retiradas(self):
        canal = self.canal('Telefe', _anda(), _muerta())
        salud.limpiar(AHORA)
        self.assertEqual(servicios.mostrar_canales(Canal.objects.filter(pk=canal.pk)), 1)
        self.assertTrue(all(f.activa for f in self.senales(canal)))

    def test_el_modo_revision_prueba_las_retiradas_primero_y_las_devuelve(self):
        canal = self.canal('Telefe', _anda(anduvo=AHORA - timedelta(days=2)), _muerta(tipo='directo'))
        self.canal('Otro sin datos', {})
        salud.limpiar(AHORA)
        retirada = self.senales(canal)[1]
        self.assertEqual(recorrido.pendientes(5, ahora=AHORA)[0], retirada)
        recorrido.anotar([{'id': retirada.pk, 'anduvo': True}], AHORA)
        retirada.refresh_from_db()
        self.assertEqual((retirada.activa, retirada.retirada), (True, None))


class UnaSenalTests(Base):

    def setUp(self):
        super().setUp()
        rol = Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales'])
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=rol))
        self.disney = self.canal('Disney', _anda(), _muerta(oculta_hasta=AHORA + timedelta(hours=3)),
                                 _anda(activa=False))
        self.buena, self.caida, self.apagada = self.senales(self.disney)

    def accion(self, fuente, cual):
        return self.client.post(reverse('canales:fuente_accion', args=[fuente.pk]), {
            'accion': cual, 'volver': reverse('canales:organizar') + '?contenido=vivo'})

    def test_quitar_una_senal_aunque_el_canal_se_vea(self):
        respuesta = self.accion(self.buena, 'quitar')
        self.assertTrue(respuesta.url.endswith(f'#ver-{self.disney.pk}'))   # vuelve con el detalle abierto
        self.buena.refresh_from_db()
        self.assertEqual((self.buena.activa, self.buena.retirada), (False, None))

    def test_volver_a_mostrar_una_senal_aunque_el_canal_se_vea(self):
        self.accion(self.caida, 'mostrar')
        self.accion(self.apagada, 'mostrar')
        self.caida.refresh_from_db()
        self.apagada.refresh_from_db()
        self.assertEqual((self.caida.estado, self.caida.oculta_hasta, self.caida.fallas_seguidas, self.caida.activa),
                         (Estado.SIN_VERIFICAR, None, 0, True))
        self.assertTrue(self.apagada.activa)

    def test_probar_ahora(self):
        retirada = self.senales(self.canal('Telefe', _anda(), _muerta()))[1]
        salud.limpiar(AHORA)
        with mock.patch('canales.views_revisar.verificar_url', return_value=Resultado(FUNCIONA, tipo='hls')):
            respuesta = self.client.post(reverse('canales:fuente_accion', args=[retirada.pk]), {'accion': 'probar'},
                                         follow=True)
        self.assertContains(respuesta, 'anda ahora')
        retirada.refresh_from_db()
        self.assertEqual((retirada.activa, retirada.estado), (True, Estado.FUNCIONA))
        with mock.patch('canales.views_revisar.verificar_url', return_value=Resultado(CAIDA, 'No respondió a tiempo.')):
            respuesta = self.client.post(reverse('canales:fuente_accion', args=[retirada.pk]), {'accion': 'probar'},
                                         follow=True)
        self.assertContains(respuesta, 'no anda desde el servidor')

    def test_sin_permiso_no(self):
        rol = Rol.objects.create(nombre='Mirar', permisos=['ver_canales'])
        self.client.force_login(Usuario.objects.create_user('miron', None, 'x', rol=rol))
        self.assertEqual(self.accion(self.buena, 'quitar').status_code, 403)

    def test_organizar_las_encuentra_y_el_detalle_tiene_los_botones(self):
        self.canal('Todo bien', _anda())
        respuesta = self.client.get(reverse('canales:organizar'), {'contenido': 'vivo', 'mostrar': 'senales'})
        self.assertContains(respuesta, 'Disney')
        self.assertNotContains(respuesta, 'Todo bien')
        self.assertContains(respuesta, '1 de 3 señales')
        self.assertContains(respuesta, 'id="form-accion-senal"')
        crudo = re.search(r'<article class="espejo-tarjeta[^"]*"\s+data-clave="[^"]*"\s+data-datos="([^"]+)"', respuesta.content.decode()).group(1)
        senales = json.loads(unescape(crudo))['fuentes']
        self.assertEqual([s['se_puede_mostrar'] for s in senales], [False, True, True])
        salud.limpiar(AHORA)   # la caída (muerta) se retira
        crudo = re.search(r'<article class="espejo-tarjeta[^"]*"\s+data-clave="[^"]*"\s+data-datos="([^"]+)"',
                          self.client.get(reverse('canales:organizar'), {'contenido': 'vivo'}).content.decode()).group(1)
        self.assertIn('Retirada sola el', json.loads(unescape(crudo))['fuentes'][1]['retirada'])


class BandejaDeSenalesTests(Base):

    def test_las_retiradas_en_para_revisar_y_borrarlas(self):
        canal = self.canal('Telefe', _anda(), _muerta(), _muerta(origen='vieja.m3u'))
        self.canal('Sin retiradas', _anda())
        salud.limpiar(AHORA)
        grupos, _ = bandeja.armar(ahora=AHORA)
        senales = next(g for g in grupos if g.clave == 'senales')
        self.assertEqual([c.nombre for c in senales.casos], ['Telefe'])
        self.assertIn('Se retiraron 2 de sus 3 señales', senales.casos[0].detalle)
        lista = next(l for l in bandeja.listas(ahora=AHORA) if l.origen == 'vieja.m3u')
        self.assertEqual((lista.muertas, lista.apagadas), (1, 0))

        self.assertEqual(bandeja.borrar_retiradas(Canal.objects.filter(pk=canal.pk)), 2)
        self.assertEqual(canal.fuentes.count(), 1)   # la buena queda
