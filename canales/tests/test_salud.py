"""
La salud con memoria (canales/salud.py): cada fuente recuerda sus últimas
pruebas, del servidor y de los aparatos, y la limpieza automática quita los
canales que no anduvieron en una semana (y los devuelve si vuelven a andar).
"""

import json
import re
from datetime import timedelta
from html import unescape
from io import StringIO
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from canales import salud, servicios
from canales.models import Canal, Fuente
from canales.salud import Salud
from canales.verificacion import CAIDA, FUNCIONA, SIN_VERIFICAR, Resultado
from usuarios.models import Rol, Usuario

Estado = Fuente.Estado


def _anda():
    return Resultado(FUNCIONA, tipo='hls')


def _falla(error='No respondió a tiempo.'):
    return Resultado(CAIDA, error)


class MemoriaTests(TestCase):

    def setUp(self):
        cache.clear()
        self.canal = Canal.objects.create(nombre='Canal 26')
        self.fuente = Fuente.objects.create(canal=self.canal, url='https://x/26.m3u8')

    def probar(self, *resultados):
        for resultado in resultados:
            servicios.aplicar_resultado(self.fuente, resultado, timezone.now())
        self.fuente.save()
        self.fuente.refresh_from_db()

    def test_el_servidor_anota_cada_prueba_y_cualquier_vez_que_anda_deja_de_fallar(self):
        self.probar(_anda(), _falla(), _falla('El servidor respondió con error 404 al pedir la lista.'))
        self.assertEqual(self.fuente.historial, '+--')
        self.assertEqual((self.fuente.fallas_seguidas, self.fuente.por_que_falla), (2, 'no_existe'))
        self.assertIsNotNone(self.fuente.falla_desde)
        self.assertEqual(salud.de_fuente(self.fuente), Salud.FALLA)
        self.probar(_anda())
        self.assertEqual((self.fuente.fallas_seguidas, self.fuente.falla_desde, self.fuente.por_que_falla),
                         (0, None, ''))
        self.assertIsNotNone(self.fuente.anduvo)

    def test_lo_que_el_servidor_no_puede_saber_no_cuenta_en_contra(self):
        # Xtream en vivo que bloquea al VPS: queda "sin verificar", y eso no es una falla
        self.probar(Resultado(SIN_VERIFICAR, 'No se pudo verificar desde el servidor.'))
        self.assertEqual((self.fuente.historial, self.fuente.fallas_seguidas), ('?', 0))
        self.assertEqual(salud.de_fuente(self.fuente), Salud.SIN_DATOS)
        self.assertIn('Xtream', salud.texto_de_fuente(self.fuente))

    def test_el_motivo_de_la_falla(self):
        casos = {
            'El canal no entrega la lista al reproductor (error 403).': 'rechaza',
            'Responde, pero con una página web, no con video.': 'rechaza',
            'El servidor rechazó la conexión.': 'conexion',
            'No respondió a tiempo.': 'tiempo',
            'La lista no tiene video (está vacía).': 'error',
        }
        for error, motivo in casos.items():
            with self.subTest(error):
                self.probar(_falla(error))
                self.assertEqual(self.fuente.por_que_falla, motivo)
        self.assertEqual(salud.de_fuente(self.fuente), Salud.FALLA)

    def test_rechaza(self):
        self.probar(_falla('El canal no entrega la lista al reproductor (error 403).'))
        self.assertEqual(salud.de_fuente(self.fuente), Salud.RECHAZA)

    def test_inestable_a_veces_si_y_a_veces_no(self):
        self.probar(_anda(), _falla(), _anda(), _anda(), _falla(), _anda())
        self.assertEqual(salud.de_fuente(self.fuente), Salud.INESTABLE)
        self.assertIn('anduvo 4 de las últimas 6', salud.texto_de_fuente(self.fuente))

    def test_un_corte_suelto_no_la_hace_inestable(self):
        self.probar(*[_anda()] * 8, _falla(), _anda())
        self.assertEqual(salud.de_fuente(self.fuente), Salud.ANDA)

    def test_el_historial_recuerda_las_ultimas(self):
        self.probar(*[_anda()] * 30)
        self.assertEqual(len(self.fuente.historial), salud.LARGO_DEL_HISTORIAL)

    def test_muerta_solo_si_falla_sin_parar_una_semana_y_varias_veces(self):
        ahora = timezone.now()
        self.fuente.falla_desde = ahora - timedelta(days=8)
        self.fuente.fallas_seguidas = salud.FALLAS_PARA_QUITAR - 1
        self.assertEqual(salud.de_fuente(self.fuente, ahora), Salud.FALLA)   # pocas veces: puede ser un corte
        self.fuente.fallas_seguidas = salud.FALLAS_PARA_QUITAR
        self.assertEqual(salud.de_fuente(self.fuente, ahora), Salud.MUERTA)
        self.fuente.falla_desde = ahora - timedelta(days=3)
        self.assertEqual(salud.de_fuente(self.fuente, ahora), Salud.FALLA)   # todavía no pasó la semana


class AparatosTests(TestCase):

    def setUp(self):
        cache.clear()
        self.canal = Canal.objects.create(nombre='HBO')
        self.fuente = Fuente.objects.create(canal=self.canal, url='http://x/live/u/c/1.ts', tipo='directo',
                                            estado=Estado.SIN_VERIFICAR, falla_desde=timezone.now(),
                                            fallas_seguidas=3, por_que_falla='rechaza', historial='-x-')

    def test_verla_un_minuto_en_un_aparato_es_que_anda(self):
        servicios.registrar_estabilidad(self.fuente, 90, 0)
        self.fuente.refresh_from_db()
        self.assertEqual((self.fuente.fallas_seguidas, self.fuente.historial[-1]), (0, '*'))
        self.assertEqual(salud.de_fuente(self.fuente), Salud.INESTABLE)   # falló 3 de 4: todavía no es confiable
        servicios.registrar_estabilidad(self.fuente, 90, 0)
        self.fuente.refresh_from_db()
        self.assertEqual(self.fuente.historial, '-x-*')   # lo de muchos aparatos juntos entra una vez

    def test_unos_segundos_no_alcanzan(self):
        servicios.registrar_estabilidad(self.fuente, 20, 0)
        self.fuente.refresh_from_db()
        self.assertEqual(self.fuente.fallas_seguidas, 3)

    def test_la_falla_de_un_aparato_cuenta_una_vez_cada_tanto(self):
        servicios.registrar_falla_en_aparato(self.fuente, 'a', 'tiempo')
        servicios.registrar_falla_en_aparato(self.fuente, 'b', 'tiempo')
        self.fuente.refresh_from_db()
        self.assertEqual((self.fuente.historial, self.fuente.fallas_seguidas), ('-x-x', 4))
        self.assertEqual(self.fuente.por_que_falla, 'tiempo')

    def test_si_el_aparato_no_puede_leer_el_video_no_es_que_el_link_este_muerto(self):
        fuente = Fuente.objects.create(canal=self.canal, url='https://x/hevc.m3u8', anduvo=timezone.now(),
                                       historial='+')
        servicios.registrar_falla_en_aparato(fuente, 'a', 'formato')
        fuente.refresh_from_db()
        self.assertEqual((fuente.historial, fuente.fallas_seguidas), ('+f', 0))
        self.assertEqual(salud.de_fuente(fuente), Salud.FORMATO)
        # El canal está como su mejor fuente
        self.assertEqual(salud.de_canal([self.fuente, fuente]), Salud.FORMATO)


class LimpiezaTests(TestCase):

    def setUp(self):
        cache.clear()
        self.ahora = timezone.now()

    def canal(self, nombre, *fuentes):
        canal = Canal.objects.create(nombre=nombre)
        for numero, datos in enumerate(fuentes):
            Fuente.objects.create(canal=canal, url=f'https://x/{nombre}/{numero}.m3u8', **datos)
        return canal

    def muerta(self, dias=8, veces=salud.FALLAS_PARA_QUITAR, **datos):
        return {'estado': Estado.CAIDA, 'falla_desde': self.ahora - timedelta(days=dias), 'fallas_seguidas': veces,
                'por_que_falla': 'no_existe', **datos}

    def test_quita_solo_los_que_no_anduvieron_en_una_semana(self):
        muerto = self.canal('Muerto', self.muerta(), self.muerta(dias=20))
        una_viva = self.canal('Una viva', self.muerta(), {'estado': Estado.FUNCIONA})
        hace_poco = self.canal('Hace poco', self.muerta(dias=3))
        pocas_veces = self.canal('Pocas veces', self.muerta(veces=2))
        sin_datos = self.canal('Sin datos', {'historial': '????'})
        apagada = self.canal('Viva pero apagada', self.muerta(), {'estado': Estado.FUNCIONA, 'activa': False})

        resultado = salud.limpiar(self.ahora)

        self.assertEqual(resultado, {'quitados': ['Muerto', 'Viva pero apagada'], 'volvieron': [],
                                     # "Una viva" sigue, pero su señal muerta se retira (test_senales.py)
                                     'senales_retiradas': ['Una viva'], 'senales_devueltas': 0})
        muerto.refresh_from_db()
        self.assertFalse(muerto.activo)
        self.assertTrue(muerto.motivo_quitado.startswith(salud.QUITADO_POR_LA_LIMPIEZA))
        self.assertIn('la dirección ya no existe', muerto.motivo_quitado)
        for canal in (una_viva, hace_poco, pocas_veces, sin_datos):
            canal.refresh_from_db()
            self.assertTrue(canal.activo, canal.nombre)
        self.assertEqual(Fuente.objects.filter(canal=muerto).count(), 2)   # nunca se borra nada
        apagada.refresh_from_db()
        self.assertFalse(apagada.activo)   # lo apagado a mano no cuenta: sus fuentes prendidas no andan

    def test_si_vuelve_a_andar_vuelve_solo(self):
        canal = self.canal('Revive', self.muerta())
        salud.limpiar(self.ahora)
        self.assertEqual(salud.limpiar(self.ahora)['volvieron'], [])   # sigue muerto
        fuente = canal.fuentes.get()
        servicios.aplicar_resultado(fuente, _anda(), self.ahora)
        fuente.save()
        self.assertEqual(salud.limpiar(self.ahora)['volvieron'], ['Revive'])
        canal.refresh_from_db()
        self.assertEqual((canal.activo, canal.motivo_quitado), (True, ''))

    def test_lo_quitado_a_mano_no_vuelve_solo(self):
        canal = self.canal('A mano', {'estado': Estado.FUNCIONA, 'anduvo': self.ahora})
        servicios.quitar_canales(Canal.objects.filter(pk=canal.pk), 'No interesa')
        self.assertEqual(salud.limpiar(self.ahora)['volvieron'], [])
        canal.refresh_from_db()
        self.assertFalse(canal.activo)

    def test_volver_a_mostrar_da_otra_semana_entera(self):
        canal = self.canal('Otra oportunidad', self.muerta())
        salud.limpiar(self.ahora)
        servicios.mostrar_canales(Canal.objects.filter(pk=canal.pk))
        self.assertEqual(salud.limpiar(self.ahora)['quitados'], [])
        canal.refresh_from_db()
        self.assertTrue(canal.activo)

    def test_el_resumen_cuenta_cada_canal_por_su_mejor_fuente(self):
        self.canal('Anda', {'anduvo': self.ahora}, self.muerta())
        self.canal('Falla', self.muerta(dias=1))
        self.canal('Sin datos', {})
        cuentas = salud.resumen(self.ahora)
        self.assertEqual((cuentas[Salud.ANDA], cuentas[Salud.FALLA], cuentas[Salud.SIN_DATOS]), (1, 1, 1))
        self.assertIn('se da por muerta', salud.texto_de_fuente(Fuente.objects.get(canal__nombre='Falla')))

    def test_el_cron_hace_la_limpieza_despues_de_verificar(self):
        self.canal('Muerto', self.muerta())
        salida = StringIO()
        with mock.patch('canales.management.commands.verificar_fuentes.verificar_fuentes_guardadas',
                        return_value='nada'), \
                mock.patch('canales.imagenes.emparejar_logos', return_value='nada'), \
                mock.patch('canales.management.commands.verificar_fuentes.es_hora_de_medir', return_value=False):
            call_command('verificar_fuentes', stdout=salida)
        self.assertIn('Limpieza: quitó 1 canal(es) muertos', salida.getvalue())
        self.assertFalse(Canal.objects.get(nombre='Muerto').activo)


class CargaTests(TestCase):

    def test_lo_que_entra_de_una_lista_ya_probado_arranca_con_su_prueba(self):
        ahora = timezone.now()
        self.assertEqual(salud.al_cargar(Estado.FUNCIONA, ahora), {'historial': '+', 'anduvo': ahora})
        self.assertEqual(salud.al_cargar(Estado.SIN_VERIFICAR, ahora), {})


class DetallesTests(TestCase):

    def test_el_panel_de_detalles_muestra_la_salud_del_canal_y_de_cada_senal(self):
        rol = Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales'])
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=rol))
        canal = Canal.objects.create(nombre='Disney')
        Fuente.objects.create(canal=canal, url='https://x/disney.m3u8', estado=Estado.CAIDA, historial='+--',
                              falla_desde=timezone.now() - timedelta(days=2), fallas_seguidas=2,
                              por_que_falla='tiempo')
        respuesta = self.client.get(reverse('canales:organizar'), {'contenido': 'vivo'})
        crudo = re.search(r'<article class="espejo-tarjeta[^"]*"\s+data-clave="[^"]*"\s+data-datos="([^"]+)"', respuesta.content.decode()).group(1)
        datos = json.loads(unescape(crudo))
        self.assertIn(['Salud', salud.TEXTOS_DE_CANAL[Salud.FALLA]], datos['datos'])
        senal = datos['fuentes'][0]
        self.assertTrue(senal['salud_mal'])
        self.assertIn('Falla hace 2 días (no responde a tiempo)', senal['salud'])
        self.assertIn('Últimas pruebas: ✓✗✗.', senal['salud'])
