"""Películas de canales oficiales de YouTube: leer el canal, nombres, géneros, verificar e importar."""

import io
import urllib.error
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from canales import clasificar, consultas, servicios, youtube
from canales.models import Canal, Categoria, Contenido, EntradaImportada, Fuente
from canales.verificacion import CAIDA, FUNCIONA, Resultado, verificar_url
from usuarios.models import Usuario

Estado = EntradaImportada.Estado


def _todas_funcionan(fuentes, **_):
    return {url: Resultado(FUNCIONA, tipo=tipo) for url, tipo in fuentes.items()}


class NombresTests(TestCase):

    def test_id_del_video(self):
        self.assertEqual(youtube.id_de_video('https://www.youtube.com/watch?v=mclqwyG7PG8&t=3'), 'mclqwyG7PG8')
        self.assertEqual(youtube.id_de_video('https://youtu.be/mclqwyG7PG8'), 'mclqwyG7PG8')
        self.assertIsNone(youtube.id_de_video('https://www.youtube.com/@MovieCentralEspanol'))
        self.assertIsNone(youtube.id_de_video('https://vimeo.com/123'))

    def test_titulo_limpio(self):
        casos = {
            'Búnker de Venganza | Sylvia Hoeks | Película Completa De Acción En Español Latino': 'Búnker de Venganza',
            'OSCURA | ESTRENO 2023 | PELICULA DE SUSPENSO EN ESPANOL LATINO': 'Oscura',
            '¡A Bluey y a Bingo les da ganas de comer pavlova!💙🍰| Bluey Español Canal Oficial':
                'A Bluey y a Bingo les da ganas de comer pavlova',
            '🧩 POCOYÓ en ESPAÑOL - Día Mundial del Puzzle [122 min] | CARICATURAS y DIBUJOS ANIMADOS para niños':
                'Día Mundial del Puzzle',
            'Ecos del Olvido | Ciencia Ficción | Suspenso | Peliculas Completas en Español Latino': 'Ecos del Olvido',
        }
        for titulo, esperado in casos.items():
            self.assertEqual(youtube.titulo_limpio(titulo), esperado, titulo)

    def test_no_repite_el_nombre_del_canal(self):
        titulos = ['Masha y el Oso 💥 Nuevo capítulo 💥 Sin amigos', 'Masha y el Oso ⭐ Manitas Mágicas ⭐',
                   'Masha y el Oso 🎆 ¡Deja que las cosas se mezclen!', 'Masha y el Oso 🐻']
        self.assertEqual(youtube.nombres_distintos(titulos),
                         ['Sin amigos', 'Manitas Mágicas', 'Deja que las cosas se mezclen', 'Masha y el Oso'])
        self.assertEqual(youtube.nombres_distintos(['Hula Hula', 'Hula Hula']), ['Hula Hula', 'Hula Hula (2)'])

    def test_genero(self):
        self.assertEqual(youtube.genero('Su Ex Murió | Comedia de Terror'), 'Comedia')   # lo que aparece primero
        self.assertEqual(youtube.genero('Lo Atacaron de Noche | Terror'), 'Terror')
        self.assertEqual(youtube.genero('El Cruce del Bastardo | Película Completa de Western'), 'Western')
        self.assertEqual(youtube.genero('Hope Debía Decidir entre su Pasión y su Futuro | Película Completa'), '')

    def test_en_ingles(self):
        self.assertTrue(youtube.en_ingles('A Single Shot Uncovered a Criminal Network | Full Movie'))
        self.assertTrue(youtube.en_ingles("Pocoyo's Favorite Toy! | POCOYÓ in ENGLISH"))
        self.assertFalse(youtube.en_ingles('Executioner | Full Action Movie in Spanish'))
        self.assertFalse(youtube.en_ingles('Tormenta Blanca | Drama Completo Español Latino'))

    def test_capitulos_de_series(self):
        self.assertEqual(youtube.capitulo('T2 E5: Realidad | Crónicas del Metal Hurlant | Serie de Ciencia Ficción'),
                         'Crónicas del Metal Hurlant S02 E05 Realidad')
        self.assertEqual(youtube.capitulo('En la Oscuridad T1 | Serie de TERROR | Episodio 10 completo en español'),
                         'En la Oscuridad S01 E10')
        self.assertIsNone(youtube.capitulo('Masha y el Oso 💥 Tienda de lácteos (Capítulo 7)'))   # sin temporada


class LeerElCanalTests(TestCase):

    def test_el_link_del_canal(self):
        direccion = youtube._direccion_del_listado
        self.assertEqual(direccion('https://www.youtube.com/@MovieCentralEspanol'),
                         'https://www.youtube.com/@MovieCentralEspanol/videos')
        self.assertEqual(direccion('youtube.com/@Bluey/featured'), 'https://www.youtube.com/@Bluey/videos')
        self.assertEqual(direccion('https://www.youtube.com/channel/UCH6uKFPQcZLihwbnzxnw1dA'),
                         'https://www.youtube.com/channel/UCH6uKFPQcZLihwbnzxnw1dA/videos')
        self.assertEqual(direccion('https://www.youtube.com/playlist?list=PL123'),
                         'https://www.youtube.com/playlist?list=PL123')
        for malo in ('https://vimeo.com/canal', 'https://www.youtube.com/watch?v=mclqwyG7PG8'):
            with self.assertRaises(youtube.NoSePudo):
                direccion(malo)

    def test_pide_los_titulos_en_espanol(self):
        # Si no se pide el idioma, YouTube traduce los títulos al inglés ("Summer in Venice - Episode 123")
        ytdl = mock.MagicMock()
        ytdl.__enter__.return_value.extract_info.return_value = {
            'channel': 'RCN Novelas', 'entries': [{'id': 'aaaaaaaaaa1', 'title': 'Verano en Venecia - Capítulo 1',
                                                   'duration': 2700}]}
        with mock.patch('yt_dlp.YoutubeDL', return_value=ytdl) as clase:
            listado = youtube.videos_del_canal('https://www.youtube.com/@RCNNovelas')
        self.assertEqual(clase.call_args[0][0]['extractor_args'], {'youtube': {'lang': ['es']}})
        self.assertEqual(listado.videos[0].titulo, 'Verano en Venecia - Capítulo 1')


class VerificarTests(TestCase):

    def _respuesta(self, cuerpo=b'{"title": "Tormenta Blanca"}'):
        respuesta = mock.MagicMock()
        respuesta.__enter__.return_value.read.return_value = cuerpo
        return respuesta

    def test_se_puede_insertar(self):
        with mock.patch('urllib.request.urlopen', return_value=self._respuesta()) as pedido:
            resultado = verificar_url('https://www.youtube.com/watch?v=NvQqHzqClf0', 'yt_video')
        self.assertEqual((resultado.estado, resultado.tipo, resultado.titulo),
                         (FUNCIONA, 'yt_video', 'Tormenta Blanca'))
        self.assertIn('oembed', pedido.call_args[0][0].full_url)

    def test_el_duenio_no_deja_o_ya_no_existe(self):
        for codigo, motivo in ((401, 'no deja verlo fuera'), (404, 'ya no existe')):
            error = urllib.error.HTTPError('u', codigo, 'x', {}, io.BytesIO())
            with mock.patch('urllib.request.urlopen', side_effect=error):
                resultado = youtube.verificar_video('https://www.youtube.com/watch?v=NvQqHzqClf0')
            self.assertEqual(resultado.estado, CAIDA)
            self.assertIn(motivo, resultado.error)


class ImportarTests(TestCase):

    def setUp(self):
        self.listado = youtube.Listado('Movie Central', [
            youtube.Video('aaaaaaaaaa1', 'Tormenta Blanca | Drama de Supervivencia Completo Español Latino', 7725),
            youtube.Video('aaaaaaaaaa2', 'Lo Atacaron de Noche | Terror', 5591),
            youtube.Video('aaaaaaaaaa3', 'Avance de la semana', 90),
            youtube.Video('aaaaaaaaaa4', 'A Single Shot | Full Movie', 5400),
            youtube.Video('aaaaaaaaaa5', 'Estreno programado | Acción', 0),
            *[youtube.Video(f'bbbbbbbbbb{n}', f'En la Oscuridad T1 | Episodio {n} completo | Serie de TERROR', 2700)
              for n in (1, 2, 3)],
        ])

    def test_arma_la_importacion(self):
        importacion = servicios.crear_importacion_de_youtube(self.listado, minimo_minutos=40)
        self.assertEqual(importacion.archivo, 'YouTube: Movie Central')
        estados = dict(importacion.entradas.values_list('tvg_id', 'estado'))
        self.assertEqual(estados['aaaaaaaaaa1'], Estado.PENDIENTE)
        self.assertEqual(estados['aaaaaaaaaa3'], Estado.DESCARTADA)   # corto
        self.assertEqual(estados['aaaaaaaaaa4'], Estado.DESCARTADA)   # en inglés
        self.assertEqual(estados['aaaaaaaaaa5'], Estado.DESCARTADA)   # sin duración
        terror = importacion.entradas.get(tvg_id='aaaaaaaaaa2')
        self.assertEqual((terror.nombre, terror.categoria, terror.contenido, terror.tipo),
                         ('Lo Atacaron de Noche', 'Terror', Contenido.PELICULA, 'yt_video'))
        self.assertEqual(terror.logo, 'https://i.ytimg.com/vi/aaaaaaaaaa2/hqdefault.jpg')
        capitulo = importacion.entradas.get(tvg_id='bbbbbbbbbb2')
        self.assertEqual((capitulo.nombre, capitulo.contenido), ('En la Oscuridad S01 E02', Contenido.SERIE))

    def test_se_prueba_y_se_carga_como_una_lista(self):
        importacion = servicios.crear_importacion_de_youtube(self.listado, categoria='Cine', minimo_minutos=40)
        servicios.procesar_lote(importacion, _todas_funcionan, segundos=None)
        servicios.cargar_lote(importacion)
        pelicula = Canal.objects.get(nombre='Tormenta Blanca')
        self.assertEqual((pelicula.contenido, pelicula.categoria.nombre), (Contenido.PELICULA, 'Cine'))
        self.assertEqual(pelicula.fuentes.get().tipo, Fuente.Tipo.YT_VIDEO)
        self.assertEqual(Canal.objects.filter(contenido=Contenido.SERIE).count(), 3)
        # La app nueva las pide; la vieja (sin "yt_video") no las ve: no las podría reproducir
        nueva = consultas.canales_disponibles(consultas.tipos_pedidos('hls,youtube,yt_video'), Contenido.PELICULA)
        vieja = consultas.canales_disponibles(consultas.tipos_pedidos('hls,youtube'), Contenido.PELICULA)
        self.assertEqual((nueva.count(), vieja.count()), (2, 0))

    def test_no_vuelve_a_traer_lo_cargado(self):
        primera = servicios.crear_importacion_de_youtube(self.listado, minimo_minutos=40)
        servicios.procesar_lote(primera, _todas_funcionan, segundos=None)
        servicios.cargar_lote(primera)
        segunda = servicios.crear_importacion_de_youtube(self.listado, minimo_minutos=40)
        repetida = segunda.entradas.get(tvg_id='aaaaaaaaaa1')
        self.assertEqual(repetida.estado, Estado.REPETIDA)
        # Dice DÓNDE está (sin eso parecía que el video no aparecía) y cómo encontrarlo
        cargado = Canal.objects.get(tvg_id='aaaaaaaaaa1')
        self.assertIn('buscá aaaaaaaaaa1 en Organizar', repetida.motivo)
        self.assertIn(f'como «{cargado.nombre}»', repetida.motivo)

    def test_el_buscador_encuentra_un_video_por_su_link_o_su_id(self):
        importacion = servicios.crear_importacion_de_youtube(self.listado, minimo_minutos=40)
        servicios.procesar_lote(importacion, _todas_funcionan, segundos=None)
        servicios.cargar_lote(importacion)
        cargado = Canal.objects.get(tvg_id='aaaaaaaaaa1')
        for texto in ('https://www.youtube.com/watch?v=aaaaaaaaaa1', 'https://youtu.be/aaaaaaaaaa1', 'aaaaaaaaaa1'):
            self.assertEqual(list(consultas.catalogo(texto=texto)), [cargado], texto)
        self.assertEqual(list(consultas.catalogo(texto=cargado.fuentes.get().url)), [cargado])


def _masha(*ids):
    """Un canal de una serie, como lo da YouTube: del video más nuevo al más viejo."""
    return youtube.Listado('Masha y el Oso', [
        youtube.Video(video_id, f'Masha y el Oso 💥 Episodio {video_id[-1]}', 1500)
        for video_id in reversed(ids)])


class ComoUnaSerieTests(TestCase):

    def setUp(self):
        Categoria.objects.create(nombre='Series Infantiles', contenido=Contenido.SERIE)

    def _traer(self, listado, verificar=_todas_funcionan, **opciones):
        importacion = servicios.crear_importacion_de_youtube(
            listado, categoria='Series Infantiles', serie='Masha y el Oso', minimo_minutos=20, **opciones)
        servicios.procesar_lote(importacion, verificar, segundos=None)
        servicios.cargar_lote(importacion)
        return importacion

    def _capitulos(self):
        return list(Canal.objects.filter(contenido=Contenido.SERIE).order_by('nombre').values_list('nombre', 'tvg_id'))

    def test_todos_son_capitulos_del_mas_viejo_al_mas_nuevo(self):
        importacion = self._traer(_masha('mmmmmmmmmm1', 'mmmmmmmmmm2', 'mmmmmmmmmm3'))
        self.assertEqual(importacion.serie, 'Masha y el Oso')
        self.assertEqual(self._capitulos(), [('Masha y el Oso S01 E01 Episodio 1', 'mmmmmmmmmm1'),
                                             ('Masha y el Oso S01 E02 Episodio 2', 'mmmmmmmmmm2'),
                                             ('Masha y el Oso S01 E03 Episodio 3', 'mmmmmmmmmm3')])
        self.assertEqual(set(Canal.objects.values_list('categoria__nombre', 'categoria__contenido')),
                         {('Series Infantiles', Contenido.SERIE)})
        serie, = consultas.series()
        self.assertEqual((serie.nombre, serie.completa), ('Masha y el Oso', True))

    def test_una_serie_nueva_entra_con_su_primer_capitulo(self):
        self._traer(_masha('mmmmmmmmmm1'))
        self.assertEqual(self._capitulos(), [('Masha y el Oso S01 E01', 'mmmmmmmmmm1')])
        serie, = consultas.series()
        self.assertEqual((serie.nombre, serie.cantidad, serie.completa), ('Masha y el Oso', 1, True))

    def test_los_que_no_pasan_no_dejan_huecos(self):
        # El más viejo no deja verse fuera de YouTube: igual hay capítulo 1 (la app no muestra series sin él)
        def el_primero_no(fuentes, **_):
            return {url: Resultado(CAIDA if url.endswith('1') else FUNCIONA, tipo=tipo)
                    for url, tipo in fuentes.items()}
        self._traer(_masha(*[f'mmmmmmmmmm{n}' for n in range(1, 6)]), verificar=el_primero_no)
        self.assertEqual([numero for numero in (clasificar.episodio(n)[2] for n, _ in self._capitulos())],
                         [1, 2, 3, 4])
        self.assertEqual(self._capitulos()[0][1], 'mmmmmmmmmm2')

    def test_lo_nuevo_sigue_la_numeracion(self):
        self._traer(_masha('mmmmmmmmmm1', 'mmmmmmmmmm2', 'mmmmmmmmmm3'))
        # Semanas después el canal subió dos más: siguen en el 4 y el 5, los viejos no se repiten
        segunda = self._traer(_masha(*[f'mmmmmmmmmm{n}' for n in range(1, 6)]))
        self.assertEqual(segunda.entradas.filter(estado=Estado.REPETIDA).count(), 3)
        self.assertEqual([n for n, _ in self._capitulos()][-2:],
                         ['Masha y el Oso S01 E04 Episodio 4', 'Masha y el Oso S01 E05 Episodio 5'])

    def test_una_lista_de_reproduccion_va_en_su_orden(self):
        listado = _masha('mmmmmmmmmm1', 'mmmmmmmmmm2', 'mmmmmmmmmm3')
        listado.videos.reverse()
        listado.nuevos_primero = False
        self._traer(listado)
        self.assertEqual(self._capitulos()[0], ('Masha y el Oso S01 E01 Episodio 1', 'mmmmmmmmmm1'))

    def test_una_lista_al_reves_va_por_el_numero_de_capitulo(self):
        # Hay listas del último capítulo al primero (Rosario Tijeras en TV Azteca): manda el número del título
        titulos = ['Ángel le dispara a Arteaga | Rosario Tijeras | Capítulo 3 | Temporada 2',
                   'Rosario se despide | Rosario Tijeras | Capítulo 2 | Temporada 2',
                   'Arteaga quiere venganza | Rosario Tijeras | Capítulo 1 | Temporada 2']
        listado = youtube.Listado('TV Azteca', [youtube.Video(f'rrrrrrrrrr{n}', t, 2600)
                                                for n, t in zip((3, 2, 1), titulos)], nuevos_primero=False)
        self.assertEqual([v.id for v in youtube.en_orden_de_capitulos(listado)],
                         ['rrrrrrrrrr1', 'rrrrrrrrrr2', 'rrrrrrrrrr3'])
        self.assertEqual(youtube.numero_de_capitulo('AMOR CON BUENAS INTENCIONES EP20'), (0, 20))
        self.assertEqual(youtube.numero_de_capitulo('La Pola - Capítulo 98 Final - El fin'), (0, 98))
        self.assertIsNone(youtube.numero_de_capitulo('La Doña | Capítulo Final'))
        # Temporada y capítulo juntos, como numeran Transformers, Power Rangers, Yu-Gi-Oh! o 31 minutos
        self.assertEqual(youtube.numero_de_capitulo('Transformers Prime: S02 E26 | Episodio COMPLETO'), (2, 26))
        self.assertEqual(youtube.numero_de_capitulo('Día Del Basurero | Episodio Completo | S01 | E01'), (1, 1))
        self.assertEqual(youtube.numero_de_capitulo('Ataque la Gigantesca Mandy | T4 EP7 | EPISODIO COMPLETO'), (4, 7))
        self.assertEqual(youtube.numero_de_capitulo('Yu-Gi-Oh! GX 3x51 (El Regreso del Rey Supremo)'), (3, 51))
        self.assertEqual(youtube.numero_de_capitulo('31 minutos - Episodio 1*20 - Lo mejor de 31 minutos'), (1, 20))
        # Si casi ninguno dice el número, queda el orden de la lista
        sin_numero = youtube.Listado('X', [youtube.Video('ssssssssss1', 'El dilema', 2600),
                                           youtube.Video('ssssssssss2', 'Alergia mortal', 2600)],
                                     nuevos_primero=False)
        self.assertEqual([v.id for v in youtube.en_orden_de_capitulos(sin_numero)], ['ssssssssss1', 'ssssssssss2'])

    def test_no_se_carga_a_medio_probar(self):
        importacion = servicios.crear_importacion_de_youtube(
            _masha('mmmmmmmmmm1', 'mmmmmmmmmm2', 'mmmmmmmmmm3'), serie='Masha y el Oso', minimo_minutos=20)
        servicios.procesar_lote(importacion, _todas_funcionan, tamanio=1, segundos=None)
        servicios.cargar_lote(importacion)
        self.assertFalse(Canal.objects.exists())

    def test_los_capitulos_que_dice_el_titulo_van_juntos(self):
        # Sin "es una serie": la serie que numera el título queda entera en UNA categoría (la que más dicen)
        listado = youtube.Listado('V', [
            youtube.Video('nnnnnnnnnn1', 'En la Oscuridad T1 | Episodio 1 | Serie de TERROR', 2700),
            youtube.Video('nnnnnnnnnn2', 'En la Oscuridad T1 | Episodio 2 | Suspenso', 2700),
            youtube.Video('nnnnnnnnnn3', 'En la Oscuridad T1 | Episodio 3 | Serie de TERROR', 2700),
        ])
        importacion = servicios.crear_importacion_de_youtube(listado, minimo_minutos=40)
        self.assertEqual(set(importacion.entradas.values_list('categoria', flat=True)), {'Terror'})


class PantallaTests(TestCase):

    def setUp(self):
        self.client.force_login(Usuario.objects.create_superuser('admin', 'admin@test.com', 'x'))

    def test_muestra_los_canales_revisados(self):
        respuesta = self.client.get(reverse('canales:youtube'))
        self.assertContains(respuesta, 'Movie Central Español')
        self.assertContains(respuesta,
                            'data-categoria="Series Infantiles" data-minutos="20" data-serie="Masha y el Oso"')

    def test_traer_un_canal(self):
        listado = youtube.Listado('Bluey', [youtube.Video('ccccccccccc', 'Bluey en la playa | Bluey', 3600)])
        with mock.patch('canales.youtube.videos_del_canal', return_value=listado):
            respuesta = self.client.post(reverse('canales:youtube'), {
                'url': 'https://www.youtube.com/@Bluey', 'categoria_nueva': 'Infantiles', 'minimo_minutos': 20,
                'solo_espanol': 'on'})
        entrada = EntradaImportada.objects.get()
        self.assertRedirects(respuesta, reverse('canales:importacion', args=[entrada.importacion_id]) + '?empezar=1',
                             fetch_redirect_response=False)
        self.assertEqual(entrada.categoria, 'Infantiles')

    def test_elegir_una_categoria_de_la_lista(self):
        # Se validaba antes de cargar las opciones y toda categoría elegida salía "no válida"
        Categoria.objects.create(nombre='Cine', contenido=Contenido.PELICULA)
        listado = youtube.Listado('Movie Central', [youtube.Video('ddddddddddd', 'Tormenta Blanca | Drama', 6000)])
        with mock.patch('canales.youtube.videos_del_canal', return_value=listado):
            respuesta = self.client.post(reverse('canales:youtube'), {
                'url': 'https://www.youtube.com/@MovieCentralEspanol', 'categoria_destino': 'Cine',
                'minimo_minutos': 60, 'solo_espanol': 'on'})
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(EntradaImportada.objects.get().categoria, 'Cine')

    def _pedir(self, **datos):
        listado = _masha('mmmmmmmmmm1', 'mmmmmmmmmm2', 'mmmmmmmmmm3')
        with mock.patch('canales.youtube.videos_del_canal', return_value=listado):
            return self.client.post(reverse('canales:youtube'), {
                'url': 'https://www.youtube.com/@MashaYElOso', 'minimo_minutos': 20, **datos})

    def test_traer_como_serie(self):
        Categoria.objects.create(nombre='Series Infantiles', contenido=Contenido.SERIE)
        respuesta = self._pedir(es_serie='on', nombre_serie='  Masha y el Oso ', categoria_destino='Series Infantiles')
        self.assertEqual(respuesta.status_code, 302)
        importacion = EntradaImportada.objects.first().importacion
        self.assertEqual(importacion.serie, 'Masha y el Oso')
        self.assertEqual(set(importacion.entradas.values_list('contenido', flat=True)), {Contenido.SERIE})

    def test_lo_que_falta_o_no_cuadra_se_explica(self):
        Categoria.objects.create(nombre='Series Infantiles', contenido=Contenido.SERIE)
        Categoria.objects.create(nombre='Infantil', contenido=Contenido.PELICULA)
        casos = [
            ({'es_serie': 'on', 'categoria_destino': 'Series Infantiles'}, 'Escribí el nombre de la serie.'),
            ({'es_serie': 'on', 'nombre_serie': 'Masha'}, 'Elegí en qué categoría de Series va'),
            ({'es_serie': 'on', 'nombre_serie': 'Masha', 'categoria_destino': 'Infantil'},
             '&quot;Infantil&quot; es una categoría de Películas'),
            ({'categoria_destino': 'Series Infantiles'}, 'marcá &quot;Es una serie&quot;'),
            ({'categoria_destino': 'Infantil', 'categoria_nueva': 'Infantiles'}, 'dejá solo una de las dos'),
            ({'es_serie': 'on', 'nombre_serie': '4x4 Aventuras', 'categoria_nueva': 'Series Infantiles'},
             'la app confundiría con un número de capítulo'),
        ]
        for datos, mensaje in casos:
            self.assertContains(self._pedir(**datos), mensaje, msg_prefix=str(datos))
        self.assertFalse(EntradaImportada.objects.exists())

    def test_marca_en_rojo_el_campo_con_error(self):
        respuesta = self.client.post(reverse('canales:youtube'), {'url': '', 'minimo_minutos': 60})
        self.assertContains(respuesta, 'inputmode="url" maxlength="300" class="form-control is-invalid"')
        self.assertContains(respuesta, 'name="minimo_minutos" value="60" min="1" max="600" class="form-control" ')

    def test_avisa_si_no_se_pudo_leer(self):
        with mock.patch('canales.youtube.videos_del_canal', side_effect=youtube.NoSePudo('El canal no tiene videos.')):
            respuesta = self.client.post(reverse('canales:youtube'), {
                'url': 'https://www.youtube.com/@nada', 'minimo_minutos': 60})
        self.assertContains(respuesta, 'El canal no tiene videos.')
