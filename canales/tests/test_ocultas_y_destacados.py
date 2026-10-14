"""
Lo que falla en los aparatos se oculta UN RATO (cada vez más si sigue
fallando) y vuelve solo; cuando un aparato lo ve bien, se olvida. Y lo
"destacado en la TV", que el modo reposo de la app muestra más seguido.
"""

import importlib
from datetime import timedelta

from django.apps import apps
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api import tokens
from canales import consultas
from canales.models import Canal, Fuente
from canales.servicios import registrar_estabilidad, registrar_falla_en_aparato
from usuarios.models import Rol, Usuario


def _canal(nombre='Disney', contenido='vivo'):
    canal = Canal.objects.create(nombre=nombre, contenido=contenido)
    Fuente.objects.create(canal=canal, url=f'https://senal.ejemplo.com/{canal.pk}.m3u8', estado=Fuente.Estado.FUNCIONA)
    return canal


class OcultarUnRatoTests(TestCase):

    def setUp(self):
        cache.clear()
        self.canal = _canal()
        self.fuente = self.canal.fuentes.get()

    def fallar_en_dos_aparatos(self, motivo='conexion'):
        cache.clear()   # cada vez, aparatos "nuevos"
        registrar_falla_en_aparato(self.fuente, 'a', motivo)
        oculta = registrar_falla_en_aparato(self.fuente, 'b', motivo)
        self.fuente.refresh_from_db()
        return oculta

    def tiempo_oculta(self):
        return round((self.fuente.oculta_hasta - self.fuente.oculta_desde).total_seconds() / 3600)

    def pasa_el_tiempo(self):
        Fuente.objects.filter(pk=self.fuente.pk).update(oculta_hasta=timezone.now() - timedelta(minutes=1))
        self.fuente.refresh_from_db()

    def test_un_aparato_solo_no_la_oculta(self):
        self.assertFalse(registrar_falla_en_aparato(self.fuente, 'a', 'conexion'))
        self.assertFalse(self.fuente.oculta_por_aparatos)

    def test_la_primera_vez_solo_3_horas_y_despues_vuelve_sola(self):
        self.assertTrue(self.fallar_en_dos_aparatos())
        self.assertEqual(self.tiempo_oculta(), 3)
        self.assertFalse(consultas.canales_disponibles().filter(pk=self.canal.pk).exists())
        self.pasa_el_tiempo()
        self.assertTrue(consultas.canales_disponibles().filter(pk=self.canal.pk).exists())

    def test_si_sigue_fallando_cada_vez_mas(self):
        horas = []
        for _ in range(4):
            self.fallar_en_dos_aparatos()
            horas.append(self.tiempo_oculta())
            self.pasa_el_tiempo()
        self.assertEqual(horas, [3, 24, 7 * 24, 7 * 24])

    def test_si_los_aparatos_no_leen_el_formato_va_directo_a_la_semana(self):
        self.fallar_en_dos_aparatos('formato')
        self.assertEqual(self.tiempo_oculta(), 7 * 24)

    def test_cuando_un_aparato_la_ve_bien_se_olvida_y_vuelve_ya(self):
        self.fallar_en_dos_aparatos()
        self.pasa_el_tiempo()
        self.fallar_en_dos_aparatos()   # segunda vez: un día
        self.assertEqual(self.tiempo_oculta(), 24)
        registrar_estabilidad(self.fuente, segundos=30, cortes=0)   # muy poco: no alcanza
        self.fuente.refresh_from_db()
        self.assertTrue(self.fuente.oculta_por_aparatos)
        # Un aparato que todavía la tenía la vio bien un rato: anda
        registrar_estabilidad(self.fuente, segundos=300, cortes=0)
        self.fuente.refresh_from_db()
        self.assertFalse(self.fuente.oculta_por_aparatos)
        self.assertEqual((self.fuente.veces_oculta, self.fuente.avisos_de_aparatos, self.fuente.falla_en_aparatos),
                         (0, 0, ''))
        # Si vuelve a fallar, empieza de nuevo por lo más corto
        self.fallar_en_dos_aparatos()
        self.assertEqual(self.tiempo_oculta(), 3)

    def test_el_panel_dice_cuando_vuelve(self):
        self.fallar_en_dos_aparatos()
        canal = consultas.catalogo().get(pk=self.canal.pk)
        motivo = consultas.por_que_no_se_ve(canal)
        vuelve = timezone.localtime(self.fuente.oculta_hasta)
        self.assertIn('Oculto un rato', motivo)
        self.assertIn(f'Vuelve solo a la app el {vuelve:%d/%m} a las {vuelve:%H:%M}', motivo)

    def test_las_que_estaban_ocultas_pasan_a_la_regla_nueva(self):
        migracion = importlib.import_module('canales.migrations.0022_destacados_y_ocultas_un_rato')
        hace_un_dia = timezone.now() - timedelta(days=1)
        Fuente.objects.filter(pk=self.fuente.pk).update(oculta_desde=hace_un_dia,
                                                        falla_en_aparatos='no se puede conectar con la señal')
        de_formato = _canal('Otro').fuentes.get()
        Fuente.objects.filter(pk=de_formato.pk).update(
            oculta_desde=hace_un_dia, falla_en_aparatos='el aparato no puede leer el formato del video')
        migracion.pasar_a_ocultas_un_rato(apps, None)
        self.fuente.refresh_from_db()
        de_formato.refresh_from_db()
        self.assertFalse(self.fuente.oculta_por_aparatos)   # Disney: ya pasaron las 3 horas, vuelve
        self.assertTrue(de_formato.oculta_por_aparatos)     # formato: sigue la semana
        self.assertEqual(self.fuente.veces_oculta, 1)


class DestacadosTests(TestCase):

    def setUp(self):
        rol = Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales'])
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=rol))
        self.pelicula = _canal('Toy Story (1995)', 'pelicula')
        self.capitulos = [_canal(f'Bluey S01 E0{n}', 'serie') for n in (1, 2)]

    def editar(self, **datos):
        return self.client.post(reverse('canales:organizar_editar'), {
            'nombre': 'Toy Story (1995)', 'activo': 'on', 'categoria': 'ninguna', 'contenido': 'pelicula',
            'canal': self.pelicula.pk, 'tipo': 'canal', **datos})

    def test_se_marca_y_se_desmarca_desde_organizar(self):
        self.editar(destacado='on')
        self.pelicula.refresh_from_db()
        self.assertTrue(self.pelicula.destacado)
        self.editar()   # la casilla sin marcar
        self.pelicula.refresh_from_db()
        self.assertFalse(self.pelicula.destacado)

    def test_una_serie_marca_todos_sus_capitulos(self):
        self.client.post(reverse('canales:organizar_editar'), {
            'tipo': 'serie', 'serie': 'Bluey', 'nombre': 'Bluey', 'activo': 'on', 'categoria': 'ninguna',
            'destacado': 'on'})
        self.assertEqual(Canal.objects.filter(contenido='serie', destacado=True).count(), 2)

    def test_el_panel_los_muestra_y_los_filtra(self):
        Canal.objects.filter(pk=self.pelicula.pk).update(destacado=True)
        _canal('Cars (2006)', 'pelicula')
        pagina = self.client.get(reverse('canales:organizar'), {'contenido': 'pelicula', 'mostrar': 'destacados'})
        self.assertContains(pagina, 'Toy Story')
        self.assertNotContains(pagina, 'Cars (2006)')
        self.assertContains(pagina, 'title="Destacado en la TV"')
        self.assertContains(pagina, '★ Destacado en la TV')   # la casilla del cuadro de edición

    def test_la_app_recibe_cuales_son(self):
        Canal.objects.filter(pk=self.pelicula.pk).update(destacado=True)
        app = APIClient()
        clave, _ = tokens.crear_token(Usuario.objects.create_user('cliente', None, 'x'))
        app.credentials(HTTP_AUTHORIZATION=f'Bearer {clave}')
        canales = app.get(reverse('api_v1:canales'), {'contenido': 'pelicula', 'formatos': 'hls'}).json()
        self.assertEqual([c['destacado'] for c in canales['categorias'][0]['canales']], [True])
