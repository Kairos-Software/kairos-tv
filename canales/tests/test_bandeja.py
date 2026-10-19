"""
"Para revisar" (canales/bandeja.py): solo lo que necesita una decisión, lo
más visto primero, con la acción ahí mismo; y cómo está cada lista de origen.
"""

from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from canales import bandeja, salud
from canales.models import Canal, Contenido, Fuente, Visto
from canales.salud import Salud
from canales.verificacion import FUNCIONA, Resultado
from usuarios.models import Rol, Usuario

Estado = Fuente.Estado
AHORA = timezone.now()


def _falla(dias=2, motivo='tiempo'):
    return {'estado': Estado.CAIDA, 'falla_desde': AHORA - timedelta(days=dias), 'fallas_seguidas': 3,
            'por_que_falla': motivo}


class Base(TestCase):

    def setUp(self):
        cache.clear()

    def canal(self, nombre, *fuentes, contenido=Contenido.VIVO, origen='lista.m3u', **datos):
        canal = Canal.objects.create(nombre=nombre, contenido=contenido, **datos)
        for numero, campos in enumerate(fuentes):
            Fuente.objects.create(canal=canal, url=f'https://x/{canal.pk}/{numero}.m3u8',
                                  origen=campos.pop('origen', origen), **campos)
        return canal

    def grupos(self, contenido=Contenido.VIVO):
        grupos, cuentas = bandeja.armar(contenido, AHORA)
        return {g.clave: [c.nombre for c in g.casos] for g in grupos}, cuentas


class ArmarTests(Base):

    def test_cada_cosa_en_su_grupo_y_lo_que_anda_no_aparece(self):
        self.canal('Anda', {'anduvo': AHORA, 'historial': '+'})
        self.canal('Rechaza', _falla(motivo='rechaza'))
        self.canal('Falla', _falla())
        self.canal('Inestable', {'anduvo': AHORA, 'historial': '+-+-+'})
        self.canal('Formato', {'anduvo': AHORA, 'historial': '+f', 'por_que_falla': 'formato'})
        self.canal('Sin datos', {'historial': '??'})
        self.canal('Quitado por la limpieza', _falla(10), activo=False,
                   motivo_quitado=f'{salud.QUITADO_POR_LA_LIMPIEZA}: ninguna fuente anduvo en 7 días.')
        self.canal('Quitado a mano', _falla(), activo=False, motivo_quitado='No interesa')
        grupos, cuentas = self.grupos()
        self.assertEqual(grupos, {'rechaza': ['Rechaza'], 'falla': ['Falla'], 'inestable': ['Inestable'],
                                  'formato': ['Formato'], 'quitados': ['Quitado por la limpieza'], 'senales': []})
        self.assertEqual((cuentas[Salud.ANDA], cuentas[Salud.SIN_DATOS], cuentas[None]), (1, 1, 1))

    def test_lo_mas_visto_primero(self):
        poco = self.canal('A poco visto', _falla())
        mucho = self.canal('Z muy visto', _falla())
        self.canal('M nadie', _falla())
        hoy = timezone.localdate()
        Visto.objects.create(canal=poco, fecha=hoy, segundos=60)
        Visto.objects.create(canal=mucho, fecha=hoy - timedelta(days=3), segundos=3600)
        Visto.objects.create(canal=poco, fecha=hoy - timedelta(days=40), segundos=99999)   # muy viejo: no cuenta
        self.assertEqual(self.grupos()[0]['falla'], ['Z muy visto', 'A poco visto', 'M nadie'])

    def test_dejar_asi_lo_saca_hasta_que_cambia(self):
        canal = self.canal('Inestable', {'anduvo': AHORA, 'historial': '+-+-+'})
        self.assertEqual(bandeja.dejar_asi(Canal.objects.filter(pk=canal.pk), ahora=AHORA), 1)
        self.assertEqual(self.grupos()[0]['inestable'], [])
        # Ahora falla: vuelve a aparecer (en otro grupo) y se olvida el "dejado así"
        Fuente.objects.filter(canal=canal).update(**_falla())
        self.assertEqual(self.grupos()[0]['falla'], ['Inestable'])
        canal.refresh_from_db()
        self.assertEqual(canal.revisado, '')

    def test_en_series_un_caso_por_serie(self):
        for numero in (1, 2, 3):
            self.canal(f'Pocoyó S01 E0{numero}', _falla(), contenido=Contenido.SERIE)
        self.canal('Pocoyó S01 E04', {'anduvo': AHORA}, contenido=Contenido.SERIE)
        grupos, _ = bandeja.armar(Contenido.SERIE, AHORA)
        falla = next(g for g in grupos if g.clave == 'falla')
        self.assertEqual([c.nombre for c in falla.casos], ['Pocoyó · 3 capítulos'])
        self.assertEqual(len(falla.casos[0].pks), 3)


class ListasTests(Base):

    def test_como_esta_cada_lista_y_la_casi_toda_caida_primero(self):
        for numero in range(10):
            self.canal(f'Mala {numero}', _falla() if numero < 7 else {'anduvo': AHORA}, origen='mala.m3u')
        self.canal('Buena', {'anduvo': AHORA}, {'anduvo': AHORA, 'activa': False}, origen='buena.m3u')
        mala, buena = bandeja.listas(Contenido.VIVO, AHORA)
        self.assertEqual((mala.origen, mala.fuentes, mala.andan, mala.fallan, mala.parte_caida), ('mala.m3u', 10, 3, 7, 70))
        self.assertTrue(mala.casi_toda_caida)
        self.assertEqual((buena.origen, buena.andan, buena.apagadas, buena.parte_que_anda), ('buena.m3u', 1, 1, 100))
        self.assertFalse(buena.casi_toda_caida)

    def test_apagar_y_volver_a_prender_una_lista(self):
        self.canal('Uno', {'anduvo': AHORA}, origen='mala.m3u')
        self.canal('Otro', {'anduvo': AHORA}, origen='otra.m3u')
        self.assertEqual(bandeja.prender_o_apagar_lista('mala.m3u', False), 1)
        self.assertEqual(Fuente.objects.filter(activa=False).count(), 1)
        self.assertEqual(bandeja.prender_o_apagar_lista('mala.m3u', True), 1)
        self.assertFalse(Fuente.objects.filter(activa=False).exists())


class PantallaTests(Base):

    def setUp(self):
        super().setUp()
        rol = Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales'])
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=rol))
        self.falla = self.canal('Disney', _falla())

    def decidir(self, accion, *canales):
        return self.client.post(reverse('canales:revisar_decidir'), {
            'accion': accion, 'contenido': 'vivo', 'canal': [c.pk for c in canales]}, follow=True)

    def test_la_pantalla(self):
        respuesta = self.client.get(reverse('canales:revisar'))
        self.assertContains(respuesta, 'Fallan ahora')
        self.assertContains(respuesta, 'Disney')
        self.assertContains(respuesta, 'Cómo está cada lista')
        self.assertContains(self.client.get(reverse('canales:inicio')), reverse('canales:revisar'))

    def test_nada_para_revisar(self):
        Fuente.objects.update(falla_desde=None, fallas_seguidas=0, anduvo=AHORA)
        self.assertContains(self.client.get(reverse('canales:revisar')), 'Nada para revisar')

    def test_quitar_y_volver_a_mostrar(self):
        self.assertContains(self.decidir('quitar', self.falla), 'Se quitaron 1')
        self.falla.refresh_from_db()
        self.assertFalse(self.falla.activo)
        self.decidir('mostrar', self.falla)
        self.falla.refresh_from_db()
        self.assertTrue(self.falla.activo)

    def test_dejar_asi(self):
        self.decidir('dejar', self.falla)
        self.assertNotContains(self.client.get(reverse('canales:revisar')), 'Fallan ahora')

    def test_probar_de_nuevo(self):
        def verificar(fuentes, cabeceras=None, hasta=None):
            return {url: Resultado(FUNCIONA, tipo='hls') for url in fuentes}
        with mock.patch('canales.views_revisar.verificar_varias', side_effect=verificar):
            respuesta = self.decidir('probar', self.falla)
        self.assertContains(respuesta, '1 andan ahora')
        fuente = self.falla.fuentes.get()
        self.assertEqual((fuente.estado, fuente.fallas_seguidas, fuente.historial), (Estado.FUNCIONA, 0, '+'))

    def test_apagar_una_lista_desde_la_pantalla(self):
        respuesta = self.client.post(reverse('canales:revisar_lista'),
                                     {'accion': 'apagar', 'origen': 'lista.m3u', 'contenido': 'vivo'}, follow=True)
        self.assertContains(respuesta, 'Se apagaron 1 fuentes')

    def test_sin_permiso_de_cambiar_solo_mira(self):
        rol = Rol.objects.create(nombre='Mirar', permisos=['ver_canales'])
        self.client.force_login(Usuario.objects.create_user('miron', None, 'x', rol=rol))
        self.assertNotContains(self.client.get(reverse('canales:revisar')), 'Probar de nuevo')
        self.assertEqual(self.client.post(reverse('canales:revisar_decidir'), {'accion': 'quitar'}).status_code, 403)
