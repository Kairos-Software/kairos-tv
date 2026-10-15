"""
Series: las 3 cosas que se deciden (categoría, serie y temporada) al traerlas
o editarlas. Una serie va en UNA categoría, sus capítulos se pasan de una
temporada a otra sin dejar huecos y el selector "Dónde va" ve lo que ya hay.
"""

from django.test import TestCase
from django.urls import reverse

from canales import consultas, organizar
from canales.forms import TraerDeYoutubeForm
from canales.models import Canal, Categoria, Contenido, Fuente
from usuarios.models import Usuario


def _capitulo(nombre, categoria=None):
    canal = Canal.objects.create(nombre=nombre, contenido=Contenido.SERIE, categoria=categoria)
    Fuente.objects.create(canal=canal, url=f'https://x/{canal.pk}.m3u8')
    return canal


def _nombres():
    return sorted(Canal.objects.filter(contenido=Contenido.SERIE).values_list('nombre', flat=True))


class TemporadasTests(TestCase):

    def setUp(self):
        self.disney = Categoria.objects.create(nombre='Disney', contenido=Contenido.SERIE)
        self.infantiles = Categoria.objects.create(nombre='Infantiles', contenido=Contenido.SERIE)
        self.caps = [_capitulo(f'Buena suerte Charlie S01 E0{n} Título {n}', self.disney) for n in range(1, 6)]

    def test_pasar_capitulos_a_una_temporada_nueva(self):
        # El 4 y el 5 eran de la segunda temporada: pasan a la 2 y la 1 queda 1, 2, 3
        cantidad = organizar.mover_a_temporada('Buena suerte Charlie', [self.caps[3].pk, self.caps[4].pk], 2)
        self.assertEqual(cantidad, 2)
        self.assertEqual(_nombres(), [
            'Buena suerte Charlie S01 E01 Título 1', 'Buena suerte Charlie S01 E02 Título 2',
            'Buena suerte Charlie S01 E03 Título 3',
            'Buena suerte Charlie S02 E01 Título 4', 'Buena suerte Charlie S02 E02 Título 5'])

    def test_la_temporada_de_donde_salen_queda_sin_huecos(self):
        organizar.mover_a_temporada('Buena suerte Charlie', [self.caps[1].pk], 2)   # sale el 2
        self.assertEqual(_nombres(), [
            'Buena suerte Charlie S01 E01 Título 1', 'Buena suerte Charlie S01 E02 Título 3',
            'Buena suerte Charlie S01 E03 Título 4', 'Buena suerte Charlie S01 E04 Título 5',
            'Buena suerte Charlie S02 E01 Título 2'])

    def test_a_una_temporada_que_ya_tiene_van_al_final(self):
        _capitulo('Buena suerte Charlie S02 E01 Otra', self.disney)
        organizar.mover_a_temporada('Buena suerte Charlie', [self.caps[4].pk], 2)
        self.assertIn('Buena suerte Charlie S02 E02 Título 5', _nombres())

    def test_no_se_puede_sin_elegir_o_a_la_misma(self):
        with self.assertRaises(organizar.NoSePuede):
            organizar.mover_a_temporada('Buena suerte Charlie', [], 2)
        with self.assertRaises(organizar.NoSePuede):
            organizar.mover_a_temporada('Buena suerte Charlie', [self.caps[0].pk], 1)
        with self.assertRaises(organizar.NoSePuede):
            organizar.mover_a_temporada('Buena suerte Charlie', [self.caps[0].pk], 0)

    def test_una_serie_va_en_una_sola_categoria(self):
        self.assertEqual(organizar.categoria_para_la_serie('Buena suerte Charlie', ''), 'Disney')
        self.assertEqual(organizar.categoria_para_la_serie('buena suerte charlie', 'disney'), 'Disney')
        with self.assertRaises(organizar.NoSePuede) as error:
            organizar.categoria_para_la_serie('Buena suerte Charlie', 'Infantiles')
        self.assertIn('ya está en la categoría "Disney"', str(error.exception))
        # Una serie nueva: la que se elija (sin elegir, se pide)
        self.assertEqual(organizar.categoria_para_la_serie('Pocoyó', 'Infantiles'), 'Infantiles')
        with self.assertRaises(organizar.NoSePuede):
            organizar.destino_de_serie('Pocoyó', '')

    def test_el_arbol_muestra_categoria_serie_y_temporadas(self):
        _capitulo('Buena suerte Charlie S02 E01 Otra', self.disney)
        _capitulo('Pocoyó S01 E01 El tornado')   # sin categoría
        arbol = consultas.arbol_de_series()
        self.assertEqual(arbol['categorias'], [
            {'nombre': 'Disney', 'series': [{'nombre': 'Buena suerte Charlie', 'temporadas': [[1, 5, 5], [2, 1, 1]]}]},
            {'nombre': 'Infantiles', 'series': []},
            {'nombre': '', 'series': [{'nombre': 'Pocoyó', 'temporadas': [[1, 1, 1]]}]},
        ])


class TraerSerieDeYoutubeTests(TestCase):

    def setUp(self):
        self.disney = Categoria.objects.create(nombre='Disney', contenido=Contenido.SERIE)
        Categoria.objects.create(nombre='Infantiles', contenido=Contenido.SERIE)
        _capitulo('Buena suerte Charlie S01 E01 Piloto', self.disney)

    def _form(self, **datos):
        base = {'url': 'https://www.youtube.com/@disney', 'es_serie': 'on', 'nombre_serie': 'Buena suerte Charlie',
                'temporada': '2', 'minimo_minutos': '5', 'solo_espanol': 'on'}
        return TraerDeYoutubeForm({**base, **datos})

    def test_una_serie_que_existe_va_a_su_categoria_sola(self):
        form = self._form()
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.categoria(), 'Disney')

    def test_otra_categoria_se_explica(self):
        form = self._form(categoria_destino='Infantiles')
        self.assertFalse(form.is_valid())
        self.assertIn('ya está en la categoría "Disney"', form.errors['categoria_destino'][0])

    def test_una_serie_nueva_pide_la_categoria(self):
        form = self._form(nombre_serie='Pocoyó', temporada='1')
        self.assertFalse(form.is_valid())
        self.assertIn('categoria_destino', form.errors)
        self.assertTrue(self._form(nombre_serie='Pocoyó', categoria_destino='Infantiles').is_valid())

    def test_desde_la_pagina_de_la_serie_llega_elegida(self):
        self.client.force_login(Usuario.objects.create_superuser('admin', 'admin@test.com', 'x'))
        respuesta = self.client.get(reverse('canales:youtube'), {'serie': 'Buena suerte Charlie', 'temporada': '2'})
        form = respuesta.context['form']
        self.assertEqual((form['es_serie'].value(), form['nombre_serie'].value(), form['temporada'].value(),
                          form['categoria_destino'].value()), (True, 'Buena suerte Charlie', 2, 'Disney'))
        self.assertContains(respuesta, 'data-destino-serie')
        self.assertContains(respuesta, 'id="arbol-series"')


class PaginaDeLaSerieTests(TestCase):

    def setUp(self):
        self.client.force_login(Usuario.objects.create_superuser('admin', 'admin@test.com', 'x'))
        self.disney = Categoria.objects.create(nombre='Disney', contenido=Contenido.SERIE)
        self.caps = [_capitulo(f'Charlie S01 E0{n} Cap {n}', self.disney) for n in range(1, 4)]

    def test_muestra_donde_esta_y_deja_cambiarlo(self):
        respuesta = self.client.get(reverse('canales:serie_detalle'), {'nombre': 'Charlie'})
        self.assertContains(respuesta, 'class="serie-camino"')
        self.assertContains(respuesta, f'categoria={self.disney.pk}')
        self.assertContains(respuesta, 'name="elegido"', count=3)
        self.assertContains(respuesta, 'una temporada nueva: la 2')
        self.assertContains(respuesta, '/canales/youtube/?serie=Charlie&amp;temporada=2')

    def test_pasar_de_temporada_desde_la_pagina(self):
        respuesta = self.client.post(reverse('canales:serie_temporada'), {
            'nombre': 'Charlie', 'elegido': [self.caps[2].pk], 'a_temporada': '2'}, follow=True)
        self.assertContains(respuesta, '1 capítulo(s) pasaron a la temporada 2')
        self.assertIn('Charlie S02 E01 Cap 3', _nombres())

    def test_si_la_temporada_1_queda_vacia_avisa(self):
        respuesta = self.client.post(reverse('canales:serie_temporada'), {
            'nombre': 'Charlie', 'elegido': [c.pk for c in self.caps], 'a_temporada': '2'}, follow=True)
        self.assertContains(respuesta, 'la temporada 1 quedó vacía')

    def test_cambiar_categoria_y_nombre(self):
        respuesta = self.client.post(reverse('canales:serie_editar'), {
            'nombre': 'Charlie', 'nuevo_nombre': 'Buena suerte Charlie', 'categoria': '',
            'categoria_nueva': 'Comedias'}, follow=True)
        self.assertContains(respuesta, 'Listo: la serie quedó así.')
        self.assertEqual(respuesta.context['serie'].nombre, 'Buena suerte Charlie')   # vuelve a la serie, ya renombrada
        self.assertEqual(set(Canal.objects.values_list('categoria__nombre', flat=True)), {'Comedias'})
        self.assertEqual(_nombres()[0], 'Buena suerte Charlie S01 E01 Cap 1')

    def test_el_arbol_para_organizar(self):
        respuesta = self.client.get(reverse('canales:series_arbol'))
        self.assertEqual(respuesta.json()['categorias'][0]['series'][0]['nombre'], 'Charlie')

    def test_unir_en_una_serie_que_ya_existe_respeta_su_categoria(self):
        otra = Canal.objects.create(nombre='Video suelto', contenido=Contenido.PELICULA)
        respuesta = self.client.post(reverse('canales:catalogo_contenido'), {
            'canal': [otra.pk], 'contenido': 'serie', 'nombre_serie': 'Charlie', 'temporada': '1',
            'serie_categoria_nueva': 'Otra cosa'}, follow=True)
        self.assertContains(respuesta, 'ya está en la categoría &quot;Disney&quot;')
        respuesta = self.client.post(reverse('canales:catalogo_contenido'), {
            'canal': [otra.pk], 'contenido': 'serie', 'nombre_serie': 'Charlie', 'temporada': '1'}, follow=True)
        otra.refresh_from_db()
        self.assertEqual((otra.nombre, otra.categoria), ('Charlie S01 E04 Video suelto', self.disney))
