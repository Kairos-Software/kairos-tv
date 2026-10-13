"""
Estabilidad de las fuentes en los aparatos: la app cuenta cuánto vio cada
fuente y cuántas veces se cortó, y la lista de canales manda primero las que
no se cortan.
"""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api import tokens
from canales.consultas import ordenadas_por_estabilidad
from canales.models import Canal, Fuente, medidas_de_calidad
from canales.servicios import (MEMORIA_DE_ESTABILIDAD, aplicar_resultado, es_hora_de_medir, medir_fuentes,
                               registrar_estabilidad)
from canales.verificacion import FUNCIONA, Resultado
from usuarios.models import Usuario


class EstabilidadTests(TestCase):

    def setUp(self):
        self.hbo = Canal.objects.create(nombre='HBO')
        self.f1, self.f2, self.f3 = (
            Fuente.objects.create(canal=self.hbo, url=f'https://x/hbo{i}.m3u8', prioridad=i) for i in (1, 2, 3)
        )
        self.app = APIClient()
        clave, _ = tokens.crear_token(Usuario.objects.create_user('cliente', None, 'x'))
        self.app.credentials(HTTP_AUTHORIZATION=f'Bearer {clave}')

    def orden(self):
        return list(ordenadas_por_estabilidad(Fuente.objects.filter(canal=self.hbo)))

    def avisar(self, fuente, segundos, cortes):
        return self.app.post(reverse('api_v1:fuente_estabilidad', args=[fuente.pk]),
                             {'segundos': segundos, 'cortes': cortes}, format='json')

    def test_sin_datos_manda_la_prioridad(self):
        self.assertEqual(self.orden(), [self.f1, self.f2, self.f3])

    def test_la_que_se_corta_va_al_final_y_la_estable_primero(self):
        # La 1 se traba (cada 30 segundos), la 3 anduvo una hora sin cortes, la 2 nunca se vio
        self.avisar(self.f1, 20 * 60, 40)
        self.avisar(self.f3, 3600, 0)
        self.assertEqual(self.orden(), [self.f3, self.f2, self.f1])
        # Lo mismo que recibe la app
        canales = self.app.get(reverse('api_v1:canales')).json()['categorias'][0]['canales']
        self.assertEqual([f['id'] for f in canales[0]['fuentes']], [self.f3.pk, self.f2.pk, self.f1.pk])

    def test_poco_visto_todavia_no_se_juzga(self):
        self.avisar(self.f1, 120, 5)   # 2 minutos: muy poco para saber
        self.assertEqual(self.orden(), [self.f1, self.f2, self.f3])
        self.assertIsNone(Fuente.objects.get(pk=self.f1.pk).cortes_por_hora)

    def test_un_corte_cada_tanto_es_tolerable(self):
        respuesta = self.avisar(self.f2, 3600, 2)   # dos cortes en una hora
        self.assertEqual(respuesta.json(), {'cortes_por_hora': 2.0})
        self.assertEqual(self.orden()[0], self.f2)

    def test_pesa_mas_lo_reciente(self):
        # Se cortaba mucho, pero después anduvo bien muchas horas: vuelve a ser estable
        registrar_estabilidad(self.f1, 3600, 60)
        for _ in range(4):
            registrar_estabilidad(self.f1, 6 * 3600, 0)
        f1 = Fuente.objects.get(pk=self.f1.pk)
        self.assertLessEqual(f1.segundos_en_aparatos, MEMORIA_DE_ESTABILIDAD)
        self.assertLess(f1.cortes_por_hora, 6)
        self.assertEqual(self.orden()[0], self.f1)

    def test_no_acepta_cualquier_cosa(self):
        self.assertEqual(self.avisar(self.f1, 'mucho', 1).status_code, 400)
        self.avisar(self.f1, 10 ** 9, 10 ** 9)   # se recorta a algo posible
        f1 = Fuente.objects.get(pk=self.f1.pk)
        self.assertLessEqual(f1.segundos_en_aparatos, MEMORIA_DE_ESTABILIDAD)
        self.assertLessEqual(f1.cortes_en_aparatos, f1.segundos_en_aparatos // 5 + 1)

    def medir(self, fuente, calidad, estado=Fuente.Estado.FUNCIONA):
        Fuente.objects.filter(pk=fuente.pk).update(calidad=calidad, estado=estado, **medidas_de_calidad(calidad))

    def test_lee_lo_que_midio_la_prueba_a_fondo(self):
        self.assertEqual(medidas_de_calidad('1080p · H.264 · audio AAC (es) · llega x3.2'),
                         {'alto': 1080, 'velocidad': 3.2})
        self.assertEqual(medidas_de_calidad('audio AAC'), {'alto': 0, 'velocidad': 0})
        self.assertEqual(medidas_de_calidad(''), {'alto': 0, 'velocidad': 0})

    def test_sin_datos_de_los_aparatos_va_primero_la_mejor_de_la_prueba(self):
        self.medir(self.f1, '720p · H.264 · llega x1.1')    # llega justa
        self.medir(self.f2, '720p · H.264 · llega x3.0')    # sobrada
        self.medir(self.f3, '1080p · H.264 · llega x2.4')   # sobrada y mejor imagen
        self.assertEqual(self.orden(), [self.f3, self.f2, self.f1])

    def test_las_que_andan_antes_que_las_sin_verificar(self):
        self.medir(self.f1, '', estado=Fuente.Estado.SIN_VERIFICAR)
        self.medir(self.f3, '')
        self.assertEqual(self.orden()[0], self.f3)

    def test_lo_de_los_aparatos_pesa_mas_que_la_prueba(self):
        self.medir(self.f1, '1080p · H.264 · llega x5.0')
        self.medir(self.f2, '480p · H.264 · llega x1.2')
        self.avisar(self.f1, 20 * 60, 40)   # en la prueba era la mejor, pero en las casas se corta
        self.avisar(self.f2, 3600, 0)
        self.assertEqual(self.orden(), [self.f2, self.f3, self.f1])

    def test_las_cuadradas_despues_de_las_que_llenan_la_pantalla(self):
        # Disney Junior: la 1 y la 2 se ven 4:3 (franjas negras a los costados), la 3 llena la pantalla
        self.medir(self.f1, '1080p · H.264 · llega x3.0')
        self.app.post(reverse('api_v1:fuente_estabilidad', args=[self.f1.pk]),
                      {'segundos': 30, 'cortes': 0, 'proporcion': 1.33}, format='json')
        self.app.post(reverse('api_v1:fuente_estabilidad', args=[self.f2.pk]),
                      {'segundos': 20, 'cortes': 0, 'proporcion': 1.25}, format='json')
        self.app.post(reverse('api_v1:fuente_estabilidad', args=[self.f3.pk]),
                      {'segundos': 20, 'cortes': 0, 'proporcion': 1.78}, format='json')
        self.assertEqual(Fuente.objects.get(pk=self.f1.pk).proporcion, 1.33)
        self.assertEqual(self.orden()[0], self.f3)   # aunque la 1 tenga mejor prueba
        self.assertEqual(set(self.orden()[1:]), {self.f1, self.f2})

    def test_una_forma_imposible_no_se_guarda(self):
        registrar_estabilidad(self.f1, 0, 0, proporcion=12)
        self.assertEqual(Fuente.objects.get(pk=self.f1.pk).proporcion, 0)

    def test_volver_a_medir_actualiza_la_calidad(self):
        resultado = Resultado(FUNCIONA, tipo='hls', a_fondo=True, alto=720, velocidad=2.5)
        aplicar_resultado(self.f1, resultado, timezone.now())
        self.f1.save()
        f1 = Fuente.objects.get(pk=self.f1.pk)
        self.assertEqual((f1.alto, f1.velocidad, f1.calidad), (720, 2.5, '720p · llega x2.5'))

    @staticmethod
    def medidor(probadas):
        def medir(fuentes, cabeceras=None, hasta=None):
            probadas.append(list(fuentes))
            return {url: Resultado(FUNCIONA, tipo='hls', a_fondo=True, alto=1080, velocidad=2.0) for url in fuentes}
        return medir

    def test_mide_solo_los_canales_con_varias_fuentes(self):
        solo = Fuente.objects.create(canal=Canal.objects.create(nombre='Telefe'), url='https://x/telefe.m3u8')
        probadas = []
        self.assertEqual(medir_fuentes(self.medidor(probadas)), 3)
        self.assertCountEqual(probadas[0], [self.f1.url, self.f2.url, self.f3.url])   # Telefe tiene una sola
        f2 = Fuente.objects.get(pk=self.f2.pk)
        self.assertEqual((f2.alto, f2.velocidad), (1080, 2.0))
        self.assertIsNotNone(f2.medida)
        self.assertEqual(Fuente.objects.get(pk=solo.pk).alto, 0)

    def test_mide_de_a_tandas_empezando_por_las_nunca_medidas(self):
        probadas = []
        medir_fuentes(self.medidor(probadas), cantidad=2)
        medir_fuentes(self.medidor(probadas), cantidad=2)
        self.assertEqual(probadas[0], [self.f1.url, self.f2.url])
        self.assertEqual(probadas[1][0], self.f3.url)   # la que faltaba, antes que repetir

    def test_mide_solo_de_madrugada(self):
        hora = timezone.make_aware(timezone.datetime(2026, 10, 13, 3, 0))
        self.assertTrue(es_hora_de_medir(hora))
        self.assertFalse(es_hora_de_medir(hora.replace(hour=21)))

    def test_hace_falta_sesion(self):
        respuesta = APIClient().post(reverse('api_v1:fuente_estabilidad', args=[self.f1.pk]),
                                     {'segundos': 60, 'cortes': 0}, format='json')
        self.assertEqual(respuesta.status_code, 401)
