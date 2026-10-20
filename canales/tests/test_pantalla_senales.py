"""
La pantalla "Señales": todas las fuentes con problemas, una por una, aunque su canal se siga viendo con otras;
cada una con su acción ahí mismo, o varias juntas.
"""

from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from canales import senales
from canales.models import Canal, Fuente
from canales.verificacion import CAIDA, FUNCIONA, Resultado
from usuarios.models import Rol, Usuario

LISTA = reverse('canales:senales')
ACCION = reverse('canales:senales_accion')


class Base(TestCase):

    def setUp(self):
        cache.clear()
        self.ahora = timezone.now()
        self.espn = Canal.objects.create(nombre='ESPN Premium')
        # La 1 anda; la 2 falla hace 2 días; la 3 la escondieron los aparatos; la 4 la retiró la limpieza
        self.anda = self.fuente(self.espn, 1, historial='+++', anduvo=self.ahora, estado=Fuente.Estado.FUNCIONA)
        self.falla = self.fuente(self.espn, 2, historial='+-x', fallas_seguidas=2, por_que_falla='tiempo',
                                 falla_desde=self.ahora - timedelta(days=2), estado=Fuente.Estado.CAIDA)
        self.oculta = self.fuente(self.espn, 3, historial='+x', anduvo=self.ahora,
                                  oculta_hasta=self.ahora + timedelta(hours=5), falla_en_aparatos='no conecta')
        self.retirada = self.fuente(self.espn, 4, historial='-' * 9, activa=False, retirada=self.ahora,
                                    fallas_seguidas=9, falla_desde=self.ahora - timedelta(days=9),
                                    por_que_falla='no_existe')
        # Un canal que NO se ve: su única señal falla
        self.tyc = Canal.objects.create(nombre='TyC Sports')
        self.tyc_falla = self.fuente(self.tyc, 1, historial='-', fallas_seguidas=1, por_que_falla='rechaza',
                                     falla_desde=self.ahora, estado=Fuente.Estado.CAIDA)
        rol = Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales'])
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=rol))

    def fuente(self, canal, numero, **datos):
        datos.setdefault('estado', Fuente.Estado.SIN_VERIFICAR)
        return Fuente.objects.create(canal=canal, url=f'http://x/{canal.pk}/{numero}.m3u8', prioridad=numero,
                                     origen='lista.m3u', **datos)

    def filas(self, **filtros):
        return senales.armar(**filtros)[0]


class ClasificarTests(Base):

    def test_cada_senal_con_su_problema(self):
        self.assertEqual(senales.de_fuente(self.anda), '')
        self.assertEqual(senales.de_fuente(self.falla), 'fallan')
        self.assertEqual(senales.de_fuente(self.oculta), 'ocultas')
        self.assertEqual(senales.de_fuente(self.retirada), 'retiradas')
        self.assertEqual(senales.de_fuente(self.tyc_falla), 'rechazan')
        Fuente.objects.filter(pk=self.anda.pk).update(activa=False)
        self.anda.refresh_from_db()
        self.assertEqual(senales.de_fuente(self.anda), 'apagadas')

    def test_aparecen_aunque_el_canal_se_vea_con_otra(self):
        filas = self.filas()
        self.assertEqual([s.fuente for s in filas], [self.tyc_falla, self.falla, self.oculta, self.retirada])
        # Primero el canal que no se ve (lo urgente)
        self.assertFalse(filas[0].canal_se_ve)
        espn = filas[1]
        self.assertTrue(espn.canal_se_ve)
        self.assertEqual((espn.numero, espn.de, espn.otras_que_andan), (2, 4, 1))

    def test_las_cuentas_y_el_filtro(self):
        filas, cuentas = senales.armar(problema='retiradas')
        self.assertEqual([s.fuente for s in filas], [self.retirada])
        self.assertEqual((cuentas['fallan'], cuentas['rechazan'], cuentas['ocultas'], cuentas['retiradas'],
                          cuentas['todas']), (1, 1, 1, 1, 4))
        self.assertEqual(senales.contar(), 4)

    def test_solo_las_de_un_canal(self):
        filas = self.filas(problema='cualquiera', canal=self.espn.pk)
        self.assertEqual([s.numero for s in filas], [1, 2, 3, 4])
        self.assertEqual(filas[0].problema, 'anda')

    def test_las_de_un_canal_eliminado_no(self):
        self.tyc.eliminar()
        self.assertNotIn(self.tyc_falla, [s.fuente for s in self.filas()])


class PantallaTests(Base):

    def test_se_ve_con_sus_problemas_y_acciones(self):
        pagina = self.client.get(LISTA).content.decode()
        self.assertIn('ESPN Premium', pagina)
        self.assertIn('el canal no se ve', pagina)          # TyC
        self.assertIn('se ve con 1 otra', pagina)           # las de ESPN
        self.assertIn('value="mostrar:%d"' % self.retirada.pk, pagina)   # una retirada se puede devolver
        self.assertIn('value="quitar:%d"' % self.falla.pk, pagina)
        self.assertIn('Con problemas <span>4</span>', pagina)

    def test_la_barra_de_contenido_dice_cuantas(self):
        pagina = self.client.get(reverse('canales:organizar')).content.decode()
        self.assertIn('class="barra-contenido"', pagina)
        self.assertIn('aria-label="4 con problemas"', pagina)

    def test_quitar_una(self):
        respuesta = self.client.post(ACCION, {'una': f'quitar:{self.falla.pk}', 'fuente': [self.oculta.pk],
                                              'volver': LISTA})
        self.assertRedirects(respuesta, LISTA, fetch_redirect_response=False)
        self.falla.refresh_from_db()
        self.oculta.refresh_from_db()
        self.assertFalse(self.falla.activa)
        self.assertTrue(self.oculta.activa)   # lo tildado no cuenta cuando se toca el botón de una fila

    def test_volver_a_mostrar_varias(self):
        self.client.post(ACCION, {'accion': 'mostrar', 'fuente': [self.retirada.pk, self.oculta.pk]})
        self.retirada.refresh_from_db()
        self.oculta.refresh_from_db()
        self.assertTrue(self.retirada.activa)
        self.assertIsNone(self.retirada.retirada)
        self.assertIsNone(self.oculta.oculta_hasta)

    def test_borrar_varias_avisa_si_un_canal_queda_sin_senales(self):
        respuesta = self.client.post(ACCION, {'accion': 'borrar', 'fuente': [self.retirada.pk, self.tyc_falla.pk]},
                                     follow=True)
        self.assertFalse(Fuente.objects.filter(pk__in=[self.retirada.pk, self.tyc_falla.pk]).exists())
        self.assertContains(respuesta, 'Quedaron SIN señales (no se ven): TyC Sports')

    def test_probar_varias_y_la_retirada_que_anda_vuelve(self):
        def verificar(urls, **_):
            return {url: Resultado(FUNCIONA, tipo='hls') if url == self.retirada.url else Resultado(CAIDA, 'no')
                    for url in urls}

        with mock.patch('canales.views_senales.verificar_varias', side_effect=verificar):
            respuesta = self.client.post(ACCION, {'accion': 'probar', 'fuente': [self.retirada.pk, self.falla.pk]},
                                         follow=True)
        self.assertContains(respuesta, 'Se probaron 2: 1 andan ahora')
        self.retirada.refresh_from_db()
        self.assertTrue(self.retirada.activa)

    def test_sin_permiso_de_editar_no_hay_acciones(self):
        rol = Rol.objects.create(nombre='Mirar', permisos=['ver_canales'])
        self.client.force_login(Usuario.objects.create_user('mira', None, 'x', rol=rol))
        pagina = self.client.get(LISTA).content.decode()
        self.assertIn('ESPN Premium', pagina)
        self.assertNotIn('name="una"', pagina)
        self.assertEqual(self.client.post(ACCION, {'una': f'borrar:{self.falla.pk}'}).status_code, 403)
