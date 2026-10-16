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
from canales.servicios import importar_m3u
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


class EliminarCapitulosTests(TestCase):

    def setUp(self):
        self.client.force_login(Usuario.objects.create_superuser('admin', 'admin@test.com', 'x'))
        # Importados de una lista: así, al recuperarlos, sus señales se rearman con el informe
        importar_m3u('#EXTM3U\n' + ''.join(f'#EXTINF:-1 group-title="Disney",Charlie S01 E0{n} Cap {n}\n'
                                           f'https://x/charlie{n}.m3u8\n' for n in range(1, 6)), 'lista.m3u')
        Canal.objects.update(contenido=Contenido.SERIE)
        self.caps = {n: Canal.objects.get(nombre=f'Charlie S01 E0{n} Cap {n}') for n in range(1, 6)}

    def test_eliminar_renumera_sin_huecos(self):
        # Sin el capítulo 1 la temporada arrancaba en el 2 y la app escondía la serie
        organizar.eliminar_capitulos('Charlie', [self.caps[1].pk, self.caps[3].pk])
        self.assertEqual(_nombres(), ['Charlie S01 E01 Cap 2', 'Charlie S01 E02 Cap 4', 'Charlie S01 E03 Cap 5'])
        self.assertTrue(consultas.series()[0].completa)

    def test_al_recuperarlos_vuelven_a_su_lugar(self):
        organizar.eliminar_capitulos('Charlie', [self.caps[1].pk, self.caps[3].pk])
        resultado = organizar.restaurar_eliminados(organizar.eliminados_recientes()[0].muestra)
        self.assertEqual(resultado.restaurados, 2)
        self.assertEqual(_nombres(), [f'Charlie S01 E0{n} Cap {n}' for n in range(1, 6)])

    def test_solo_los_de_esa_serie(self):
        otra = Canal.objects.create(nombre='Otra S01 E01', contenido=Contenido.SERIE)
        with self.assertRaises(organizar.NoSePuede):
            organizar.eliminar_capitulos('Charlie', [otra.pk])

    def test_desde_la_pagina_de_la_serie(self):
        pagina = self.client.get(reverse('canales:serie_detalle'), {'nombre': 'Charlie'})
        self.assertContains(pagina, 'Eliminarlos')
        respuesta = self.client.post(reverse('canales:serie_eliminar_capitulos'), {
            'nombre': 'Charlie', 'elegido': [self.caps[5].pk]}, follow=True)
        self.assertContains(respuesta, 'Se eliminaron 1 capítulo(s)')
        self.assertEqual(len(_nombres()), 4)

    def test_si_eran_todos_vuelve_a_series(self):
        respuesta = self.client.post(reverse('canales:serie_eliminar_capitulos'), {
            'nombre': 'Charlie', 'elegido': [c.pk for c in self.caps.values()]}, follow=True)
        self.assertContains(respuesta, 'eran todos, la serie ya no está')
        self.assertEqual(respuesta.request['PATH_INFO'], reverse('canales:organizar'))


class OrdenarPorTitulosTests(TestCase):
    """Lo que vino mezclado de YouTube (numerado por fecha, todo en la temporada 1) se reparte según los títulos."""

    def setUp(self):
        self.client.force_login(Usuario.objects.create_superuser('admin', 'admin@test.com', 'x'))
        titulos = ['Temporada 2 Capitulo 1 La vuelta', 'Temporada 1 Capitulo 2 Segundo', 'Temporada 1 Capitulo 1 Inicio',
                   'Temporada 2 Capitulo 2 Final', 'Especial de Navidad', 'Temporada 1 Capitulo 2 Segundo (otra subida)']
        for numero, titulo in enumerate(titulos, start=1):
            _capitulo(f'Casi Angeles S01 E{numero:02d} {titulo}')

    def test_el_plan_reparte_y_avisa(self):
        plan = organizar.plan_por_titulos('Casi Angeles')
        self.assertEqual([(c.despues, c.titulo, c.problema) for c in plan.capitulos], [
            ((1, 1), 'Temporada 1 Capitulo 1 Inicio', ''),
            ((1, 2), 'Temporada 1 Capitulo 2 Segundo', ''),
            ((1, 3), 'Temporada 1 Capitulo 2 Segundo (otra subida)', 'repetido'),   # al final, para revisar
            ((1, 4), 'Especial de Navidad', 'sin_numero'),
            ((2, 1), 'Temporada 2 Capitulo 1 La vuelta', ''),
            ((2, 2), 'Temporada 2 Capitulo 2 Final', ''),
        ])
        self.assertEqual(plan.temporadas, [(1, 4, 1, 4), (2, 2, 1, 2)])
        self.assertFalse(plan.falta_el_1)
        self.assertEqual(_nombres()[0], 'Casi Angeles S01 E01 Temporada 2 Capitulo 1 La vuelta')   # todavía nada

    def test_aplicar(self):
        self.assertEqual(organizar.ordenar_por_titulos('Casi Angeles'), 5)   # el T1 C2 ya estaba en su lugar
        self.assertIn('Casi Angeles S02 E01 Temporada 2 Capitulo 1 La vuelta', _nombres())
        self.assertIn('Casi Angeles S01 E01 Temporada 1 Capitulo 1 Inicio', _nombres())
        self.assertEqual(organizar.ordenar_por_titulos('Casi Angeles'), 0)   # ya quedó así

    def test_con_huecos_y_de_corrido(self):
        Canal.objects.filter(nombre__contains='Capitulo 1 Inicio').delete()
        plan = organizar.plan_por_titulos('Casi Angeles')
        self.assertTrue(plan.falta_el_1)   # la temporada 1 arrancaría en el 2: la app no la mostraría
        corrido = organizar.plan_por_titulos('Casi Angeles', de_corrido=True)
        self.assertFalse(corrido.falta_el_1)
        self.assertEqual([c.despues for c in corrido.de_la_temporada(1)], [(1, 1), (1, 2), (1, 3)])

    def test_la_pagina_muestra_y_despues_aplica(self):
        url = reverse('canales:serie_por_titulos')
        pagina = self.client.get(url, {'nombre': 'Casi Angeles'})
        self.assertContains(pagina, 'Así quedaría')
        self.assertContains(pagina, 'Aplicar: ordenar 5 capítulos')
        self.assertContains(pagina, 'dicen un número que ya tiene otro')
        self.assertEqual(_nombres()[0], 'Casi Angeles S01 E01 Temporada 2 Capitulo 1 La vuelta')   # mirar no cambia
        respuesta = self.client.post(url, {'nombre': 'Casi Angeles'}, follow=True)
        self.assertContains(respuesta, 'Listo: 5 capítulo(s) cambiaron')
        self.assertIn('Casi Angeles S02 E02 Temporada 2 Capitulo 2 Final', _nombres())
        serie = self.client.get(reverse('canales:serie_detalle'), {'nombre': 'Casi Angeles'})
        self.assertContains(serie, 'Ordenar todo según los títulos')


class TraerSegunElTituloTests(TestCase):

    def setUp(self):
        Categoria.objects.create(nombre='Juveniles', contenido=Contenido.SERIE)

    def test_cada_video_a_su_temporada_y_capitulo(self):
        from canales import servicios, youtube
        from canales.verificacion import FUNCIONA, Resultado
        _capitulo('Casi Angeles S03 E01 Temporada 3 Capitulo 1 Ya estaba')
        titulos = ['Casi Angeles Temporada 3 Capitulo 33 UN LUGAR QUE SOLO NOSOTROS CONOCEMOS',
                   'Casi Angeles Temporada 1 Capitulo 1 El comienzo', 'Casi Angeles Temporada 3 Capitulo 1 Repetido',
                   'Casi Angeles Especial']
        listado = youtube.Listado('Casi Angeles', [youtube.Video(f'casiangele{n}', titulo, 2867)
                                                   for n, titulo in enumerate(titulos)])
        importacion = servicios.crear_importacion_de_youtube(
            listado, categoria='Juveniles', serie='Casi Angeles', temporada=2, minimo_minutos=40, segun_titulo=True)
        servicios.procesar_lote(importacion, lambda fuentes, **_: {u: Resultado(FUNCIONA, tipo=t)
                                                                   for u, t in fuentes.items()}, segundos=None)
        servicios.cargar_lote(importacion)
        nombres = _nombres()
        self.assertIn('Casi Angeles S03 E33 Temporada 3 Capitulo 33 UN LUGAR QUE SOLO NOSOTROS CONOCEMOS', nombres)
        self.assertIn('Casi Angeles S01 E01 Temporada 1 Capitulo 1 El comienzo', nombres)
        self.assertIn('Casi Angeles S03 E34 Temporada 3 Capitulo 1 Repetido', nombres)   # el 1 ya estaba: al final
        self.assertIn('Casi Angeles S02 E01 Especial', nombres)                          # no dice: la elegida
