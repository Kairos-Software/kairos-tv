"""Ordenar el contenido: categorías por sección (crear, renombrar, juntar, borrar), cambiar de sección y la pantalla."""

from django.test import TestCase
from django.urls import reverse

from canales import consultas, organizar
from canales.models import Canal, Categoria, Contenido, Fuente
from canales.servicios import importar_m3u
from usuarios.models import Rol, Usuario


def _canal(nombre, contenido=Contenido.VIVO, categoria=None):
    return Canal.objects.create(nombre=nombre, contenido=contenido, categoria=categoria)


def _con_fuente(nombre, categoria=None, contenido=Contenido.VIVO, origen='lista-prueba.m3u'):
    canal = _canal(nombre, contenido, categoria)
    Fuente.objects.create(canal=canal, url=f'https://x/{nombre.replace(" ", "")}.m3u8', origen=origen)
    return canal


class CategoriasTests(TestCase):

    def setUp(self):
        self.infantil = Categoria.objects.create(nombre='Infantil')
        self.kids = Categoria.objects.create(nombre='Kids')
        self.animation = Categoria.objects.create(nombre='Animation;Kids')
        self.zenon = _canal('Zenón', categoria=self.kids)
        self.paka = _canal('Pakapaka', categoria=self.animation)

    def test_juntar_pasa_todo_y_recuerda_los_nombres(self):
        final = organizar.juntar_categorias([self.infantil, self.kids, self.animation], 'Infantil')
        self.assertEqual(final, self.infantil)
        self.assertEqual(set(Canal.objects.values_list('categoria__nombre', flat=True)), {'Infantil'})
        self.assertEqual(list(Categoria.objects.values_list('nombre', flat=True)), ['Infantil'])
        self.assertEqual(set(final.otros_nombres.splitlines()), {'Kids', 'Animation;Kids'})

    def test_la_importacion_respeta_lo_juntado(self):
        organizar.juntar_categorias([self.infantil, self.kids], 'Infantil')
        importar_m3u('#EXTM3U\n#EXTINF:-1 group-title="KIDS",Cartoon Prueba\nhttps://x/cartoon.m3u8\n'
                     '#EXTINF:-1 group-title="Noticias",TN\nhttps://x/tn.m3u8\n')
        self.assertEqual(Canal.objects.get(nombre='Cartoon Prueba').categoria, self.infantil)   # no volvió "Kids"
        self.assertTrue(Categoria.objects.filter(nombre='Noticias').exists())                   # lo nuevo, nuevo

    def test_juntar_en_un_nombre_nuevo(self):
        final = organizar.juntar_categorias([self.kids, self.animation], 'Chicos')
        self.assertEqual((final.nombre, final.contenido), ('Chicos', Contenido.VIVO))
        self.assertEqual(set(Canal.objects.values_list('categoria__nombre', flat=True)), {'Chicos'})

    def test_juntar_necesita_dos_y_de_la_misma_seccion(self):
        with self.assertRaises(organizar.NoSePuede):
            organizar.juntar_categorias([self.kids], 'Kids')
        de_peliculas = Categoria.objects.create(nombre='Infantil', contenido=Contenido.PELICULA)
        with self.assertRaises(organizar.NoSePuede):
            organizar.juntar_categorias([self.kids, de_peliculas], 'Infantil')

    def test_cada_seccion_tiene_sus_categorias(self):
        de_peliculas = organizar.categoria_por_nombre('Infantil', Contenido.PELICULA)
        self.assertNotEqual(de_peliculas, self.infantil)
        self.assertEqual(organizar.categoria_por_nombre('infantil', Contenido.VIVO), self.infantil)
        importar_m3u('#EXTM3U\n#EXTINF:-1 group-title="Infantil",Toy Story\nhttps://x/toy.mp4\n')
        self.assertEqual(Canal.objects.get(nombre='Toy Story').categoria, de_peliculas)

    def test_renombrar_recuerda_el_nombre_viejo(self):
        organizar.renombrar_categoria(self.kids, 'Chicos')
        self.kids.refresh_from_db()
        self.assertEqual((self.kids.nombre, self.kids.otros_nombres), ('Chicos', 'Kids'))
        self.assertEqual(organizar.categoria_por_nombre('KIDS'), self.kids)

    def test_renombrar_como_otra_que_existe_las_junta(self):
        final = organizar.renombrar_categoria(self.kids, 'infantil')
        self.assertEqual(final, self.infantil)
        self.assertEqual(Canal.objects.get(nombre='Zenón').categoria, self.infantil)

    def test_crear_no_repite_en_la_misma_seccion(self):
        organizar.crear_categoria('Música')
        with self.assertRaises(organizar.NoSePuede):
            organizar.crear_categoria('MÚSICA')
        self.assertEqual(organizar.crear_categoria('Música', Contenido.PELICULA).contenido, Contenido.PELICULA)

    def test_borrar_solo_la_categoria(self):
        self.assertEqual(organizar.borrar_categoria(self.kids), 1)
        self.assertIsNone(Canal.objects.get(nombre='Zenón').categoria)
        self.assertFalse(Categoria.objects.filter(nombre='Kids').exists())

    def test_borrar_con_todo_y_poder_reimportarlo(self):
        Fuente.objects.create(canal=self.zenon, url='https://x/zenon.m3u8')
        self.assertEqual(organizar.borrar_categoria(self.kids, con_contenido=True), 1)
        self.assertFalse(Canal.objects.filter(nombre='Zenón').exists())
        importar_m3u('#EXTM3U\n#EXTINF:-1 group-title="Kids",Zenón\nhttps://x/zenon.m3u8\n')
        self.assertTrue(Canal.objects.filter(nombre='Zenón').exists())   # se importa de nuevo normalmente

    def test_sugiere_las_parecidas(self):
        Categoria.objects.create(nombre='Noticias')
        grupos = organizar.categorias_parecidas(list(Categoria.objects.all()))
        self.assertEqual(len(grupos), 1)
        self.assertEqual({c.nombre for c in grupos[0]}, {'Infantil', 'Kids', 'Animation;Kids'})
        self.assertEqual(organizar.clave_parecida('Kids'), organizar.clave_parecida('INFANTILES'))


class CambiarTipoTests(TestCase):

    def test_peliculas_a_una_serie_numerada(self):
        infantil = Categoria.objects.create(nombre='Infantil', contenido=Contenido.PELICULA)
        for nombre in ('Flash Gordon Capitulo 10 El final', 'Flash Gordon Capitulo 2 La caverna',
                       'Flash Gordon Capitulo 1 El planeta'):
            _canal(nombre, Contenido.PELICULA, infantil)
        cantidad = organizar.cambiar_contenido(Canal.objects.all(), Contenido.SERIE, nombre_serie='Flash Gordon')
        self.assertEqual(cantidad, 3)
        nombres = list(Canal.objects.order_by('nombre').values_list('nombre', 'contenido'))
        self.assertEqual(nombres, [('Flash Gordon S01 E01 Capitulo 1 El planeta', 'serie'),
                                   ('Flash Gordon S01 E02 Capitulo 2 La caverna', 'serie'),
                                   ('Flash Gordon S01 E03 Capitulo 10 El final', 'serie')])   # 10 va después de 2
        # Pasan a la "Infantil" de Series (se crea)
        self.assertEqual({(c.categoria.nombre, c.categoria.contenido) for c in Canal.objects.all()},
                         {('Infantil', Contenido.SERIE)})

    def test_a_serie_sin_nombre_no_deja_si_quedarian_series_de_un_capitulo(self):
        _canal('Arrow S01 E01', Contenido.PELICULA)
        _canal('Una película cualquiera', Contenido.PELICULA)
        with self.assertRaises(organizar.NoSePuede):
            organizar.cambiar_contenido(Canal.objects.all(), Contenido.SERIE)
        self.assertEqual(organizar.cambiar_contenido(Canal.objects.filter(nombre__startswith='Arrow'),
                                                     Contenido.SERIE), 1)

    def test_unir_series_de_un_capitulo_en_una(self):
        for titulo in ('El tornado', 'A comer', 'Bailando'):
            _canal(titulo, Contenido.SERIE)   # como quedaron los videos de Pocoyó
        organizar.unir_en_una_serie(['El tornado', 'A comer', 'Bailando'], 'Pocoyó')
        self.assertEqual(sorted(Canal.objects.values_list('nombre', flat=True)),
                         ['Pocoyó S01 E01 A comer', 'Pocoyó S01 E02 Bailando', 'Pocoyó S01 E03 El tornado'])
        [serie] = consultas.series()
        self.assertEqual((serie.nombre, serie.cantidad), ('Pocoyó', 3))

    def test_unir_en_varias_tandas_sigue_la_numeracion(self):
        # De a una página por vez (de a 120): la segunda tanda sigue donde quedó la primera, no repite el 1
        for titulo in ('A comer', 'Bailando', 'El tornado', 'La fiesta'):
            _canal(titulo, Contenido.SERIE)
        organizar.unir_en_una_serie(['A comer', 'Bailando'], 'Pocoyó')
        organizar.unir_en_una_serie(['El tornado', 'La fiesta'], 'Pocoyó')
        self.assertEqual(sorted(Canal.objects.values_list('nombre', flat=True)),
                         ['Pocoyó S01 E01 A comer', 'Pocoyó S01 E02 Bailando', 'Pocoyó S01 E03 El tornado',
                          'Pocoyó S01 E04 La fiesta'])
        # Volver a unir la serie entera la renumera desde el 1 (no se cuenta a sí misma)
        organizar.unir_en_una_serie(['Pocoyó'], 'Pocoyó')
        self.assertEqual(Canal.objects.get(nombre__contains='A comer').nombre, 'Pocoyó S01 E01 A comer')

    def test_nombres_de_serie_que_la_app_confundiria(self):
        for malo in ('4x4 Aventuras', 'Flash S2 E3', '   '):
            with self.assertRaises(organizar.NoSePuede, msg=malo):
                organizar.nombre_de_serie_valido(malo)
        self.assertEqual(organizar.nombre_de_serie_valido('  Masha  y el Oso - '), 'Masha y el Oso')
        for bueno in ('Los 4 Fantásticos', 'Flash S2', 'Héroes E5'):   # sin el par "S2 E3", la app no se confunde
            self.assertEqual(organizar.nombre_de_serie_valido(bueno), bueno)

    def test_renombrar_una_serie(self):
        for n in (1, 2, 3):
            _canal(f'Pocoyo S01 E0{n} Capítulo', Contenido.SERIE)
            _canal(f'Bluey S01 E0{n}', Contenido.SERIE)
        # Corregir solo un acento también se puede
        organizar.editar_serie('Pocoyo', nombre='Pocoyó')
        self.assertEqual(Canal.objects.filter(nombre__startswith='Pocoyó S01').count(), 3)
        # Con el nombre de OTRA serie no: se pisarían los capítulos (para eso está "Unir")
        with self.assertRaisesMessage(organizar.NoSePuede, 'Ya hay otra serie "Bluey"'):
            organizar.renombrar_serie('Pocoyó', 'Bluey')

    def test_series_enteras_a_peliculas(self):
        for n in (1, 2, 3):
            _canal(f'Arrow S01 E0{n}', Contenido.SERIE)
        _canal('Otra S01 E01', Contenido.SERIE)
        capitulos = organizar.capitulos_de(['arrow'])
        self.assertEqual(capitulos.count(), 3)
        organizar.cambiar_contenido(capitulos, Contenido.PELICULA)
        self.assertEqual(Canal.objects.filter(contenido=Contenido.PELICULA).count(), 3)

    def test_editar_no_pasa_uno_suelto_a_serie(self):
        canal = _canal('Una película', Contenido.PELICULA)
        with self.assertRaises(organizar.NoSePuede):
            organizar.editar_canal(canal, contenido=Contenido.SERIE)


class OrganizarTests(TestCase):
    """La pantalla Organizar contenido."""

    def setUp(self):
        self.client.force_login(Usuario.objects.create_superuser('admin', 'admin@test.com', 'x'))
        self.infantil = Categoria.objects.create(nombre='Infantil', orden=1)
        self.kids = Categoria.objects.create(nombre='Kids', orden=2)
        self.noticias = Categoria.objects.create(nombre='Noticias', orden=3)
        self.cine = Categoria.objects.create(nombre='Infantil', contenido=Contenido.PELICULA)

    def test_cada_seccion_muestra_solo_sus_categorias(self):
        _con_fuente('Zenón', self.infantil)
        _con_fuente('Toy Story', self.cine, Contenido.PELICULA)
        datos = consultas.organizar_contenido(Contenido.PELICULA)
        self.assertEqual([n['categoria'] for n in datos.nodos], [self.cine])
        respuesta = self.client.get(reverse('canales:organizar'), {'contenido': 'pelicula'})
        self.assertContains(respuesta, 'Categorías de Películas')
        # (la palabra "Noticias" sí está: es uno de los íconos para una sección nueva)
        self.assertNotContains(respuesta, f'value="{self.noticias.pk}"')
        self.assertNotContains(respuesta, 'data-nombre="Noticias"')

    def test_parecidas_y_juntar_desde_la_pagina(self):
        _con_fuente('Zenón', self.infantil)
        _con_fuente('Cartoon', self.kids)
        respuesta = self.client.get(reverse('canales:organizar'))
        self.assertContains(respuesta, 'Parecen la misma')
        volver = reverse('canales:organizar')
        respuesta = self.client.post(reverse('canales:categorias'), {
            'accion': 'juntar', 'elegida': [self.infantil.pk, self.kids.pk], 'destino_pk': self.infantil.pk,
            'volver': volver}, follow=True)
        self.assertContains(respuesta, 'Kids ya no existen')
        self.assertEqual(Canal.objects.get(nombre='Cartoon').categoria, self.infantil)

    def test_crear_en_la_seccion_elegida(self):
        self.client.post(reverse('canales:categorias'), {'accion': 'crear', 'nombre': 'Acción', 'seccion': 'pelicula'})
        self.assertEqual(Categoria.objects.get(nombre='Acción').contenido, Contenido.PELICULA)
        self.assertRedirects(self.client.get(reverse('canales:categorias')), reverse('canales:organizar'))

    def test_la_pagina_muestra_de_donde_salio(self):
        _con_fuente('Zenón', self.infantil, origen='YouTube: Canal Oficial')
        respuesta = self.client.get(reverse('canales:organizar'), {'categoria': self.infantil.pk})
        self.assertContains(respuesta, 'YouTube: Canal Oficial')   # en los datos de la edición rápida
        self.assertRedirects(self.client.get(reverse('canales:como_en_la_app')), reverse('canales:organizar') + '?',
                             fetch_redirect_response=False)

    def test_mover_y_pasar_de_seccion(self):
        zenon = _con_fuente('Zenón', self.kids)
        self.client.post(reverse('canales:catalogo_categoria'),
                         {'canal': [zenon.pk], 'categoria': self.infantil.pk, 'seccion': 'vivo'})
        zenon.refresh_from_db()
        self.assertEqual(zenon.categoria, self.infantil)
        self.client.post(reverse('canales:catalogo_contenido'), {'canal': [zenon.pk], 'contenido': 'pelicula'})
        zenon.refresh_from_db()
        self.assertEqual((zenon.contenido, zenon.categoria), (Contenido.PELICULA, self.cine))
        respuesta = self.client.post(reverse('canales:catalogo_contenido'), {'canal': [zenon.pk], 'contenido': 'serie'},
                                     follow=True)
        self.assertContains(respuesta, 'Escribí el nombre de la serie')

    def test_unir_en_una_serie_desde_la_pagina(self):
        for titulo in ('El tornado', 'A comer', 'Bailando'):
            _con_fuente(titulo, contenido=Contenido.SERIE)
        respuesta = self.client.post(reverse('canales:series_acciones'), {
            'serie': ['El tornado', 'A comer', 'Bailando'], 'accion': 'unir', 'nombre_serie': 'Pocoyó',
            'temporada': '1', 'serie_categoria': 'Infantiles'}, follow=True)
        self.assertContains(respuesta, 'capítulos de la serie')
        self.assertNotContains(respuesta, 'la app solo muestra series')
        self.assertEqual([(s.nombre, s.cantidad, s.completa, s.categoria) for s in consultas.series()],
                         [('Pocoyó', 3, True, 'Infantiles')])

    def test_una_serie_nueva_aparece_desde_su_primer_capitulo(self):
        _con_fuente('El tornado', contenido=Contenido.PELICULA)
        respuesta = self.client.post(reverse('canales:catalogo_contenido'), {
            'canal': [Canal.objects.get().pk], 'contenido': 'serie', 'nombre_serie': 'Pocoyó',
            'serie_categoria_nueva': 'Dibujitos'}, follow=True)
        self.assertContains(respuesta, 'quedaron como capítulos de la serie &quot;Pocoyó&quot;')
        self.assertNotContains(respuesta, 'la app solo muestra series')
        serie = consultas.series()[0]
        self.assertEqual((serie.nombre, serie.cantidad, serie.completa, serie.categoria), ('Pocoyó', 1, True, 'Dibujitos'))

    def test_una_serie_nueva_pide_su_categoria(self):
        _con_fuente('El tornado', contenido=Contenido.PELICULA)
        respuesta = self.client.post(reverse('canales:catalogo_contenido'), {
            'canal': [Canal.objects.get().pk], 'contenido': 'serie', 'nombre_serie': 'Pocoyó'}, follow=True)
        self.assertContains(respuesta, 'Elegí en qué categoría de Series va')
        self.assertEqual(Canal.objects.get().contenido, Contenido.PELICULA)   # no cambió nada

    def test_edicion_rapida(self):
        canal = _con_fuente('Zenón', self.noticias)
        self.client.post(reverse('canales:organizar_editar'), {
            'tipo': 'canal', 'canal': canal.pk, 'nombre': 'Zenón Kids', 'logo': 'https://ejemplo.com/logo.png',
            'categoria': self.infantil.pk, 'contenido': 'vivo', 'numero': '11'})   # sin "activo": se quita
        canal.refresh_from_db()
        self.assertEqual((canal.nombre, canal.logo, canal.categoria, canal.numero, canal.activo),
                         ('Zenón Kids', 'https://ejemplo.com/logo.png', self.infantil, '11', False))

    def test_edicion_rapida_de_una_serie_entera(self):
        series = Categoria.objects.create(nombre='Acción', contenido=Contenido.SERIE)
        for n in (1, 2, 3):
            _con_fuente(f'Arrow S01 E0{n} Piloto', contenido=Contenido.SERIE)
        self.client.post(reverse('canales:organizar_editar'), {
            'tipo': 'serie', 'serie': 'Arrow', 'nombre': 'Flecha', 'logo': '', 'categoria': series.pk, 'activo': 'on'})
        self.assertEqual(sorted(Canal.objects.values_list('nombre', 'categoria')),
                         [(f'Flecha S01 E0{n} Piloto', series.pk) for n in (1, 2, 3)])

    def test_borrar_la_categoria_con_todo_desde_la_pagina(self):
        _con_fuente('Zenón', self.kids)
        tn = _con_fuente('TN', self.noticias)
        self.client.post(reverse('canales:categorias'), {'accion': 'borrar', 'categoria': self.kids.pk,
                                                         'con_contenido': '1'})
        self.assertEqual(list(Canal.objects.values_list('nombre', flat=True)), ['TN'])
        self.assertEqual(Fuente.objects.get().canal, tn)

    def test_eliminar_desde_la_pagina(self):
        canal = _con_fuente('Zenón', self.infantil)
        self.client.post(reverse('canales:organizar_eliminar'), {'canal': [canal.pk]})
        self.assertFalse(Canal.objects.filter(pk=canal.pk).exists())
        self.assertTrue(Canal.todos.filter(pk=canal.pk).exists())   # queda para las estadísticas

    def test_importar_todo_en_una_categoria(self):
        importar_m3u('#EXTM3U\n#EXTINF:-1 group-title="Varios",Zenón\nhttps://x/zenon.m3u8\n'
                     '#EXTINF:-1 group-title="Varios",Toy Story\nhttps://x/toy.mp4\n', categoria='Infantil')
        self.assertEqual(Canal.objects.get(nombre='Zenón').categoria, self.infantil)      # la de En vivo
        self.assertEqual(Canal.objects.get(nombre='Toy Story').categoria, self.cine)      # la de Películas

    def test_las_pestanias_de_peliculas_y_series(self):
        _con_fuente('Tormenta Blanca', self.cine, Contenido.PELICULA, origen='YouTube: Movie Central')
        for n in (1, 2, 3):
            _con_fuente(f'Arrow S01 E0{n}', contenido=Contenido.SERIE)
        peliculas = self.client.get(reverse('canales:organizar'), {'contenido': 'pelicula', 'mostrar': 'app'})
        self.assertContains(peliculas, 'Tormenta Blanca')
        self.assertContains(peliculas, 'YouTube: Movie Central')
        series = self.client.get(reverse('canales:organizar'), {'contenido': 'serie', 'q': 'arr'})
        self.assertContains(series, 'Arrow')
        self.assertContains(series, '3 capítulos')
        self.assertContains(series, 'Unir en una sola serie')

    def test_quien_solo_mira_no_puede_tocar(self):
        _con_fuente('Zenón', self.infantil)
        solo_ve = Usuario.objects.create_user(
            'mira', None, 'x', rol=Rol.objects.create(nombre='Mira', permisos=['ver_canales']))
        self.client.force_login(solo_ve)
        respuesta = self.client.get(reverse('canales:organizar'))
        self.assertContains(respuesta, 'Zenón')
        self.assertNotContains(respuesta, 'Nueva categoría')
        self.assertNotContains(respuesta, 'class="form-check-input canal-elegir"')
        for nombre in ('organizar_editar', 'organizar_eliminar', 'categorias', 'catalogo_categoria',
                       'catalogo_contenido', 'series_acciones'):
            self.assertEqual(self.client.post(reverse(f'canales:{nombre}')).status_code, 403)


class ComoEnLaAppTests(TestCase):
    """Lo que ve la app: las categorías, con sus nombres y en su orden."""

    def setUp(self):
        self.kids = Categoria.objects.create(nombre='Kids', orden=1)

    def test_el_nombre_como_lo_muestra_la_app(self):
        self.assertEqual(consultas.nombre_en_la_app('AR | DEPORTES'), 'Deportes')
        self.assertEqual(consultas.nombre_en_la_app(''), 'Otros')

    def test_solo_cuenta_lo_que_la_app_muestra(self):
        _con_fuente('Zenón', self.kids)
        quitado = _con_fuente('Quitado', self.kids)
        Canal.objects.filter(pk=quitado.pk).update(activo=False)
        _canal('Sin fuentes', categoria=self.kids)
        grupos = consultas.como_en_la_app(Contenido.VIVO)
        self.assertEqual([(c.nombre, [x.nombre for x in items]) for c, items in grupos], [('Kids', ['Zenón'])])


class SoloLoQueSeVeTests(TestCase):
    """Con un filtro puesto (por ejemplo, "de tal lista"), nada toca lo que no se ve: otras listas."""

    def setUp(self):
        self.client.force_login(Usuario.objects.create_superuser('admin', 'admin@test.com', 'x'))
        self.infantil = Categoria.objects.create(nombre='Infantil')
        for n in range(3):
            _con_fuente(f'Nuevo {n}', self.infantil, origen='lista-nueva.m3u')
        for n in range(5):
            _con_fuente(f'Viejo {n}', self.infantil, origen='lista-vieja.m3u')
        self.filtro = {'contenido': 'vivo', 'origen': 'lista-nueva.m3u', 'mostrar': 'todo'}

    def test_la_categoria_dice_cuanto_tiene_de_verdad(self):
        pagina = self.client.get(reverse('canales:organizar'), {**self.filtro, 'categoria': self.infantil.pk})
        self.assertContains(pagina, 'Solo los 3 que ves con el filtro')
        self.assertContains(pagina, 'Con todo lo que tiene (8)')
        self.assertContains(pagina, 'TODO LO QUE TIENE: 8, DE TODAS LAS LISTAS (con el filtro ves solo 3)')

    def test_eliminar_lo_de_una_lista_no_toca_las_otras(self):
        respuesta = self.client.post(reverse('canales:categorias'), {
            'accion': 'eliminar_filtrados', 'categoria': self.infantil.pk, **self.filtro}, follow=True)
        self.assertContains(respuesta, 'Se eliminaron 3 de &quot;Infantil&quot;')
        self.assertEqual(sorted(Canal.objects.values_list('nombre', flat=True)), [f'Viejo {n}' for n in range(5)])
        self.assertTrue(Categoria.objects.filter(pk=self.infantil.pk).exists())

    def test_las_series_con_filtro_solo_tocan_sus_capitulos_que_se_ven(self):
        series = Categoria.objects.create(nombre='Series', contenido=Contenido.SERIE)
        for n in (1, 2):
            _con_fuente(f'Pocoyó S01 E0{n}', series, Contenido.SERIE, origen='lista-nueva.m3u')
        for n in (3, 4):
            _con_fuente(f'Pocoyó S01 E0{n}', series, Contenido.SERIE, origen='lista-vieja.m3u')
        filtro = {**self.filtro, 'contenido': 'serie', 'serie': 'Pocoyó'}
        self.client.post(reverse('canales:series_acciones'), {**filtro, 'accion': 'quitar'})
        self.assertEqual(sorted(Canal.objects.filter(activo=False).values_list('nombre', flat=True)),
                         ['Pocoyó S01 E01', 'Pocoyó S01 E02'])
        self.client.post(reverse('canales:organizar_eliminar'), filtro)
        self.assertEqual(sorted(Canal.objects.filter(contenido=Contenido.SERIE).values_list('nombre', flat=True)),
                         ['Pocoyó S01 E03', 'Pocoyó S01 E04'])
        # Sin filtro, la serie entera
        self.client.post(reverse('canales:organizar_eliminar'), {'serie': 'Pocoyó'})
        self.assertFalse(Canal.objects.filter(contenido=Contenido.SERIE).exists())


class RestaurarTests(TestCase):

    def setUp(self):
        self.client.force_login(Usuario.objects.create_superuser('admin', 'admin@test.com', 'x'))
        importar_m3u('#EXTM3U\n'
                     '#EXTINF:-1 group-title="Infantil",Pakapaka\nhttps://x/paka.m3u8\n'
                     '#EXTINF:-1 group-title="Infantil" tvg-logo="https://img/zenon.png",Zenón\n'
                     '#EXTVLCOPT:http-user-agent=VLC/3.0\nhttps://x/zenon.m3u8\n'
                     '#EXTINF:-1 group-title="Infantil",Zenón\nhttps://x/zenon-2.m3u8\n', 'lista.m3u')
        self.infantil = Categoria.objects.get(nombre='Infantil')

    def test_borrar_la_categoria_con_todo_y_restaurarla(self):
        organizar.borrar_categoria(self.infantil, con_contenido=True)
        self.assertFalse(Canal.objects.exists())
        self.assertFalse(Fuente.objects.exists())

        pagina = self.client.get(reverse('canales:eliminados'))
        self.assertContains(pagina, '2 eliminados')
        eliminacion, = organizar.eliminados_recientes()
        self.assertEqual((eliminacion.cantidad, eliminacion.recuperables), (2, 2))

        respuesta = self.client.post(reverse('canales:eliminados'), {'muestra': eliminacion.muestra}, follow=True)
        self.assertContains(respuesta, 'Se restauraron 2')
        zenon = Canal.objects.get(nombre='Zenón')
        self.assertEqual((zenon.categoria.nombre, zenon.logo), ('Infantil', 'https://img/zenon.png'))
        self.assertTrue(Categoria.objects.filter(pk=self.infantil.pk).exists())   # la categoría volvió
        self.assertEqual(list(zenon.fuentes.values_list('url', 'user_agent', 'estado', 'origen')),
                         [('https://x/zenon.m3u8', 'VLC/3.0', Fuente.Estado.SIN_VERIFICAR, 'lista.m3u'),
                          ('https://x/zenon-2.m3u8', '', Fuente.Estado.SIN_VERIFICAR, 'lista.m3u')])
        self.assertEqual(organizar.eliminados_recientes(), [])

    def test_lo_que_ya_volvio_o_se_agrego_a_mano_no_se_duplica(self):
        _con_fuente('A mano', self.infantil)
        organizar.borrar_categoria(self.infantil, con_contenido=True)
        importar_m3u('#EXTM3U\n#EXTINF:-1 group-title="Infantil",Pakapaka\nhttps://x/paka.m3u8\n', 'otra.m3u')
        resultado = organizar.restaurar_eliminados(organizar.eliminados_recientes()[0].muestra)
        self.assertEqual((resultado.restaurados, resultado.ya_estaban, resultado.sin_senales), (1, 1, 1))
        self.assertEqual(Canal.objects.filter(nombre='Pakapaka').count(), 1)
        # La categoría ya existía de nuevo (la creó la otra lista): Zenón va a esa
        self.assertEqual(Canal.objects.get(nombre='Zenón').categoria, Categoria.objects.get(nombre='Infantil'))
