"""
Separar en otra serie lo que vino mezclado en una (un canal de YouTube "Yu-Gi-Oh"
con los capítulos de GX y 5D's): buscar por lo que dice el título, el nombre
sugerido, pasarlos (a una nueva o a una que existe) y que no queden huecos.
"""

from django.test import TestCase
from django.urls import reverse

from canales import organizar
from canales.models import Canal, Categoria, Contenido, Fuente
from usuarios.models import Rol, Usuario


def _capitulo(nombre, categoria=None):
    canal = Canal.objects.create(nombre=nombre, contenido=Contenido.SERIE, categoria=categoria)
    Fuente.objects.create(canal=canal, url=f'https://x/{canal.pk}.m3u8')
    return canal


def _serie(nombre):
    return sorted(c.nombre for c in organizar.capitulos_de([nombre]))


class SepararTests(TestCase):

    def setUp(self):
        self.anime = Categoria.objects.create(nombre='Anime', contenido=Contenido.SERIE)
        titulos = ['Duel Monsters Episodio 1', 'Yu-Gi-Oh! GX Episodio 1 - La llegada', 'Duel Monsters Episodio 2',
                   'Yu-Gi-Oh! GX Episodio 2', "Yu-Gi-Oh! 5D's Capitulo 1", 'yu-gi-oh! gx episodio 3']
        self.caps = [_capitulo(f'Yu-Gi-Oh en español S01 E{n:02d} {t}', self.anime) for n, t in enumerate(titulos, 1)]

    def test_encuentra_por_el_titulo_sin_mayusculas(self):
        encontrados = organizar.capitulos_que_dicen('Yu-Gi-Oh en español', 'gx')
        self.assertEqual([c.pk for c, _, _, _ in encontrados], [self.caps[1].pk, self.caps[3].pk, self.caps[5].pk])
        self.assertEqual(organizar.capitulos_que_dicen('Yu-Gi-Oh en español', '  '), [])

    def test_sugiere_el_nombre_como_empiezan_los_titulos(self):
        titulos = [t for _, _, _, t in organizar.capitulos_que_dicen('Yu-Gi-Oh en español', 'GX')]
        self.assertEqual(organizar.nombre_sugerido(titulos, 'GX'), 'Yu-Gi-Oh! GX')
        self.assertEqual(organizar.nombre_sugerido(["Yu-Gi-Oh! 5D's Capitulo 1"], '5d'), "Yu-Gi-Oh! 5D's")
        # Si los títulos empiezan por el número, no sirven: "<serie> <lo buscado>"
        self.assertEqual(organizar.nombre_sugerido(['Capitulo 5 Zeta'], 'Zeta', 'Dragon Ball'), 'Dragon Ball Zeta')

    def test_pasar_a_una_serie_nueva_y_lo_que_queda_sin_huecos(self):
        cantidad, destino = organizar.mover_a_otra_serie(
            'Yu-Gi-Oh en español', [self.caps[1].pk, self.caps[3].pk, self.caps[5].pk], 'Yu-Gi-Oh! GX')
        self.assertEqual((cantidad, destino), (3, 'Yu-Gi-Oh! GX'))
        self.assertEqual(_serie('Yu-Gi-Oh! GX'), [
            'Yu-Gi-Oh! GX S01 E01 Yu-Gi-Oh! GX Episodio 1 - La llegada',
            'Yu-Gi-Oh! GX S01 E02 Yu-Gi-Oh! GX Episodio 2',
            'Yu-Gi-Oh! GX S01 E03 yu-gi-oh! gx episodio 3'])
        self.assertEqual(_serie('Yu-Gi-Oh en español'), [
            'Yu-Gi-Oh en español S01 E01 Duel Monsters Episodio 1',
            'Yu-Gi-Oh en español S01 E02 Duel Monsters Episodio 2',
            "Yu-Gi-Oh en español S01 E03 Yu-Gi-Oh! 5D's Capitulo 1"])
        # Serie nueva: en la misma categoría que de donde salió
        self.assertEqual(set(organizar.capitulos_de(['Yu-Gi-Oh! GX']).values_list('categoria', flat=True)),
                         {self.anime.pk})

    def test_a_una_serie_que_ya_existe_van_al_final_y_quedan_en_su_categoria(self):
        otra = Categoria.objects.create(nombre='Clásicos', contenido=Contenido.SERIE)
        _capitulo("Yu-Gi-Oh! 5D's S01 E01 El primero", otra)
        organizar.mover_a_otra_serie('Yu-Gi-Oh en español', [self.caps[4].pk], "yu-gi-oh! 5d's")
        self.assertEqual(_serie("Yu-Gi-Oh! 5D's"), [
            "Yu-Gi-Oh! 5D's S01 E01 El primero", "Yu-Gi-Oh! 5D's S01 E02 Yu-Gi-Oh! 5D's Capitulo 1"])
        self.assertEqual(Canal.objects.get(pk=self.caps[4].pk).categoria, otra)

    def test_a_otra_temporada_de_la_otra_serie(self):
        organizar.mover_a_otra_serie('Yu-Gi-Oh en español', [self.caps[1].pk], 'Yu-Gi-Oh! GX', temporada=2)
        self.assertEqual(_serie('Yu-Gi-Oh! GX'), ['Yu-Gi-Oh! GX S02 E01 Yu-Gi-Oh! GX Episodio 1 - La llegada'])

    def test_no_se_puede_a_la_misma_sin_elegir_ni_con_un_nombre_que_confunde(self):
        with self.assertRaisesMessage(organizar.NoSePuede, 'esta misma serie'):
            organizar.mover_a_otra_serie('Yu-Gi-Oh en español', [self.caps[0].pk], 'yu-gi-oh en español')
        with self.assertRaises(organizar.NoSePuede):
            organizar.mover_a_otra_serie('Yu-Gi-Oh en español', [], 'Yu-Gi-Oh! GX')
        with self.assertRaises(organizar.NoSePuede):
            organizar.mover_a_otra_serie('Yu-Gi-Oh en español', [self.caps[0].pk], 'Flash S2 E3')


class SepararEnElPanelTests(TestCase):

    def setUp(self):
        rol = Rol.objects.create(nombre='Contenido', permisos=['ver_canales', 'importar_canales'])
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=rol))
        self.caps = [_capitulo(f'Yu-Gi-Oh en español S01 E0{n} {t}')
                     for n, t in enumerate(['Duel Monsters 1', 'Yu-Gi-Oh! GX 1', 'Yu-Gi-Oh! GX 2'], 1)]

    def test_la_pagina_de_la_serie_ofrece_separar(self):
        respuesta = self.client.get(reverse('canales:serie_detalle'), {'nombre': 'Yu-Gi-Oh en español'})
        self.assertContains(respuesta, '¿Tiene otras series mezcladas?')
        self.assertContains(respuesta, 'Pasar a esa serie')

    def test_ver_cuales_y_separar(self):
        url = reverse('canales:serie_separar')
        respuesta = self.client.get(url, {'nombre': 'Yu-Gi-Oh en español', 'dice': 'gx'})
        self.assertEqual(len(respuesta.context['encontrados']), 2)
        self.assertEqual(respuesta.context['sugerido'], 'Yu-Gi-Oh! GX')
        self.assertContains(respuesta, 'value="Yu-Gi-Oh! GX"')

        respuesta = self.client.post(url, {'nombre': 'Yu-Gi-Oh en español', 'a_serie': 'Yu-Gi-Oh! GX',
                                           'elegido': [self.caps[1].pk, self.caps[2].pk]})
        # Vuelve a la serie de donde salieron (para seguir separando)
        self.assertRedirects(respuesta, f"{reverse('canales:serie_detalle')}?nombre=Yu-Gi-Oh%20en%20espa%C3%B1ol")
        self.assertEqual(len(_serie('Yu-Gi-Oh! GX')), 2)
        self.assertEqual(_serie('Yu-Gi-Oh en español'), ['Yu-Gi-Oh en español S01 E01 Duel Monsters 1'])

    def test_si_pasan_todos_va_a_la_nueva(self):
        respuesta = self.client.post(reverse('canales:serie_separar'), {
            'nombre': 'Yu-Gi-Oh en español', 'a_serie': 'Yu-Gi-Oh', 'elegido': [c.pk for c in self.caps]})
        self.assertRedirects(respuesta, f"{reverse('canales:serie_detalle')}?nombre=Yu-Gi-Oh")

    def test_sin_nombre_de_serie_avisa(self):
        respuesta = self.client.post(reverse('canales:serie_separar'), {
            'nombre': 'Yu-Gi-Oh en español', 'a_serie': ' ', 'elegido': [self.caps[1].pk]}, follow=True)
        self.assertContains(respuesta, 'Escribí a qué serie pasan')
        self.assertEqual(len(_serie('Yu-Gi-Oh en español')), 3)

    def test_quien_solo_ve_no_puede(self):
        self.client.force_login(Usuario.objects.create_user('mira', None, 'x', rol=Rol.objects.create(
            nombre='Mira', permisos=['ver_canales'])))
        respuesta = self.client.get(reverse('canales:serie_separar'), {'nombre': 'Yu-Gi-Oh en español', 'dice': 'gx'})
        self.assertEqual(respuesta.status_code, 403)
