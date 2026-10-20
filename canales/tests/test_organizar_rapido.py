"""
Organizar para trabajar rápido: cambiar un dato sin recargar la página (la tarjeta vuelve redibujada), el panel
de edición que guarda en JSON, las imágenes que ya existen con ese nombre, «Cambiar nombres» de a muchos, los
chips con lo que queda por hacer y pasar a la serie vecina.
"""

from django.test import TestCase
from django.urls import reverse

from canales import consultas, organizar
from canales.models import Canal, Categoria, EntradaImportada, Fuente, Importacion
from usuarios.models import Rol, Usuario

CAMBIAR = reverse('canales:organizar_cambiar')
RENOMBRAR = reverse('canales:organizar_renombrar')
JSON = {'HTTP_ACCEPT': 'application/json'}


class Base(TestCase):

    def setUp(self):
        rol = Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales'])
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=rol))
        self.deportes = Categoria.objects.create(nombre='Deportes', contenido='vivo')
        self.noticias = Categoria.objects.create(nombre='Noticias', contenido='vivo')
        self.espn = self.canal('ESPN HD', categoria=self.deportes)

    def canal(self, nombre, anda=True, **datos):
        canal = Canal.objects.create(nombre=nombre, **datos)
        Fuente.objects.create(canal=canal, url=f'https://x/{canal.pk}.m3u8',
                              estado=Fuente.Estado.FUNCIONA if anda else Fuente.Estado.CAIDA)
        return canal

    def cambiar(self, campo, valor='', **datos):
        datos.setdefault('tipo', 'canal')
        datos.setdefault('canal', self.espn.pk)
        return self.client.post(CAMBIAR, {'campo': campo, 'valor': valor, **datos})


class CambiarUnDatoTests(Base):

    def test_el_nombre_y_vuelve_la_tarjeta_redibujada(self):
        respuesta = self.cambiar('nombre', '  ESPN   Premium ')
        self.assertEqual(respuesta.status_code, 200)
        r = respuesta.json()
        self.assertTrue(r['ok'])
        self.espn.refresh_from_db()
        self.assertEqual(self.espn.nombre, 'ESPN Premium')
        self.assertIn('class="espejo-tarjeta', r['tarjeta'])
        self.assertIn(f'data-clave="c{self.espn.pk}"', r['tarjeta'])
        self.assertIn('ESPN Premium', r['tarjeta'])
        self.assertEqual(r['datos']['nombre'], 'ESPN Premium')
        self.assertIn('se cambió el nombre', r['mensaje'])

    def test_el_nombre_no_puede_quedar_vacio(self):
        respuesta = self.cambiar('nombre', '   ')
        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(respuesta.json()['ok'])
        self.espn.refresh_from_db()
        self.assertEqual(self.espn.nombre, 'ESPN HD')

    def test_la_categoria_una_que_existe_ninguna_o_una_nueva(self):
        self.cambiar('categoria', str(self.noticias.pk))
        self.espn.refresh_from_db()
        self.assertEqual(self.espn.categoria, self.noticias)
        self.cambiar('categoria', 'ninguna')
        self.espn.refresh_from_db()
        self.assertIsNone(self.espn.categoria)
        r = self.cambiar('categoria', '', nueva='Fútbol').json()
        self.espn.refresh_from_db()
        self.assertEqual((self.espn.categoria.nombre, self.espn.categoria.contenido), ('Fútbol', 'vivo'))
        self.assertEqual(r['datos']['categoria_nombre'], 'Fútbol')

    def test_no_se_pasa_a_una_categoria_de_otra_seccion(self):
        accion = Categoria.objects.create(nombre='Acción', contenido='pelicula')
        self.assertEqual(self.cambiar('categoria', str(accion.pk)).status_code, 400)
        self.espn.refresh_from_db()
        self.assertEqual(self.espn.categoria, self.deportes)

    def test_destacado_y_se_muestra_con_un_toque(self):
        self.cambiar('destacado', '1')
        self.cambiar('activo', '0')
        self.espn.refresh_from_db()
        self.assertTrue(self.espn.destacado)
        self.assertFalse(self.espn.activo)
        self.assertEqual(self.espn.motivo_quitado, 'Quitado a mano.')
        r = self.cambiar('activo', '1').json()
        self.assertIn('aria-pressed="true"', r['tarjeta'])

    def test_la_imagen_por_link_y_un_link_que_no_es(self):
        self.cambiar('logo', 'https://imagenes.ejemplo.com/espn.png')
        self.espn.refresh_from_db()
        self.assertEqual(self.espn.logo, 'https://imagenes.ejemplo.com/espn.png')
        self.assertEqual(self.cambiar('logo', 'javascript:alert(1)').status_code, 400)
        self.cambiar('logo', '')
        self.espn.refresh_from_db()
        self.assertEqual(self.espn.logo, '')

    def test_una_serie_entera(self):
        animadas = Categoria.objects.create(nombre='Animadas', contenido='serie')
        for numero in (1, 2):
            self.canal(f'Masha S01 E0{numero} Capítulo', contenido='serie')
        r = self.client.post(CAMBIAR, {'tipo': 'serie', 'serie': 'Masha', 'campo': 'categoria',
                                       'valor': str(animadas.pk)}).json()
        self.assertTrue(r['ok'])
        self.assertEqual(set(organizar.capitulos_de(['Masha']).values_list('categoria', flat=True)), {animadas.pk})
        self.assertIn('data-clave="s:Masha"', r['tarjeta'])
        r = self.client.post(CAMBIAR, {'tipo': 'serie', 'serie': 'Masha', 'campo': 'nombre',
                                       'valor': 'Masha y el Oso'}).json()
        self.assertEqual(r['datos']['nombre'], 'Masha y el Oso')
        self.assertEqual(sorted(Canal.objects.filter(contenido='serie').values_list('nombre', flat=True)),
                         ['Masha y el Oso S01 E01 Capítulo', 'Masha y el Oso S01 E02 Capítulo'])
        r = self.client.post(CAMBIAR, {'tipo': 'serie', 'serie': 'Masha y el Oso', 'campo': 'logo',
                                       'valor': 'https://imagenes.ejemplo.com/portada.jpg'}).json()
        self.assertEqual(r['datos']['logo'], 'https://imagenes.ejemplo.com/portada.jpg')

    def test_la_imagen_de_un_capitulo_desde_la_pagina_de_su_serie(self):
        capitulo = self.canal('Masha S01 E01', contenido='serie')
        r = self.cambiar('logo', 'https://imagenes.ejemplo.com/cap.jpg', canal=capitulo.pk).json()
        self.assertTrue(r['ok'])
        self.assertEqual(r['tarjeta'], '')   # un capítulo no tiene tarjeta propia en Organizar
        self.assertEqual(r['datos'], {'tipo': 'capitulo', 'pk': capitulo.pk, 'nombre': 'Masha S01 E01',
                                      'logo': 'https://imagenes.ejemplo.com/cap.jpg'})

    def test_sin_permiso_de_editar_no(self):
        self.client.force_login(Usuario.objects.create_user('mira', None, 'x', rol=Rol.objects.create(
            nombre='Mirar', permisos=['ver_canales'])))
        self.assertEqual(self.cambiar('nombre', 'Otro').status_code, 403)
        self.assertEqual(self.cambiar('campo_raro', 'x').status_code, 403)

    def test_un_campo_que_no_se_cambia_desde_aca(self):
        self.assertEqual(self.cambiar('contenido', 'pelicula').status_code, 400)


class PanelQueGuardaEnJsonTests(Base):

    def test_guarda_sin_recargar_y_contesta_la_tarjeta(self):
        respuesta = self.client.post(reverse('canales:organizar_editar'), {
            'tipo': 'canal', 'canal': self.espn.pk, 'nombre': 'ESPN', 'logo': '', 'numero': '7',
            'categoria': str(self.noticias.pk), 'contenido': 'vivo', 'activo': 'on'}, **JSON)
        r = respuesta.json()
        self.assertTrue(r['ok'])
        self.assertIn('Se guardó «ESPN»', r['mensaje'])
        self.assertEqual((r['datos']['numero'], r['datos']['categoria']), ('7', self.noticias.pk))
        self.espn.refresh_from_db()
        self.assertEqual((self.espn.nombre, self.espn.numero, self.espn.categoria), ('ESPN', '7', self.noticias))

    def test_un_logo_raro_que_vino_en_la_lista_no_impide_guardar_el_nombre(self):
        raro = 'http://servidor de la lista/logos/espn hd.png'   # con espacios: no es un link válido
        Canal.objects.filter(pk=self.espn.pk).update(logo=raro)
        datos = {'tipo': 'canal', 'canal': self.espn.pk, 'nombre': 'ESPN', 'logo': raro, 'categoria': 'ninguna',
                 'contenido': 'vivo', 'activo': 'on'}
        self.assertTrue(self.client.post(reverse('canales:organizar_editar'), datos, **JSON).json()['ok'])
        self.espn.refresh_from_db()
        self.assertEqual((self.espn.nombre, self.espn.logo), ('ESPN', raro))
        # Pero uno nuevo que no sirve, no
        respuesta = self.client.post(reverse('canales:organizar_editar'), {**datos, 'logo': 'no es un link'}, **JSON)
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('link de una imagen', respuesta.json()['error'])

    def test_un_error_vuelve_en_json(self):
        respuesta = self.client.post(reverse('canales:organizar_editar'), {
            'tipo': 'canal', 'canal': self.espn.pk, 'nombre': '', 'categoria': 'ninguna'}, **JSON)
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('Nombre', respuesta.json()['error'])

    def test_sin_json_sigue_volviendo_a_la_pagina(self):
        respuesta = self.client.post(reverse('canales:organizar_editar'), {
            'tipo': 'canal', 'canal': self.espn.pk, 'nombre': 'ESPN', 'categoria': 'ninguna', 'volver': '/canales/'})
        self.assertRedirects(respuesta, '/canales/', fetch_redirect_response=False)


class ImagenesParecidasTests(Base):

    def test_las_de_otras_listas_y_las_del_panel_con_el_mismo_nombre(self):
        lista = Importacion.objects.create(archivo='lista_amigo.m3u')
        EntradaImportada.objects.create(importacion=lista, posicion=1, nombre_original='AR: ESPN HD', nombre='ESPN HD',
                                        url='http://x/1.ts', logo='https://logos.ejemplo.com/espn.png')
        EntradaImportada.objects.create(importacion=lista, posicion=2, nombre_original='Otra', nombre='Otra cosa',
                                        url='http://x/2.ts', logo='https://logos.ejemplo.com/otra.png')
        self.canal('ESPN HD', logo='https://panel.ejemplo.com/espn.png')
        self.canal('ESPN HD', logo='data:image/png;base64,AAAA')   # no sirve como link
        respuesta = self.client.get(reverse('canales:organizar_imagenes'), {'nombre': 'ESPN HD', 'canal': self.espn.pk})
        imagenes = respuesta.json()['imagenes']
        self.assertEqual([i['url'] for i in imagenes],
                         ['https://logos.ejemplo.com/espn.png', 'https://panel.ejemplo.com/espn.png'])
        self.assertEqual(imagenes[0]['de'], 'lista_amigo.m3u')

    def test_de_una_serie_sirven_las_de_sus_capitulos(self):
        lista = Importacion.objects.create(archivo='series.m3u')
        EntradaImportada.objects.create(importacion=lista, posicion=1, nombre_original='Bluey S01 E04',
                                        nombre='Bluey S01 E04', url='http://x/b.mp4', contenido='serie',
                                        logo='https://x/bluey.jpg')
        self.assertEqual([i['url'] for i in organizar.imagenes_parecidas('Bluey', 'serie')], ['https://x/bluey.jpg'])

    def test_sin_nombre_no_busca(self):
        self.assertEqual(organizar.imagenes_parecidas(''), [])


class CambiarNombresTests(Base):

    def test_las_reglas(self):
        regla = organizar.nombre_con_reglas
        self.assertEqual(regla('ESPN HD', sacar='hd'), 'ESPN')
        self.assertEqual(regla('Canal Sports', reemplazar='sports', por='Deportes'), 'Canal Deportes')
        self.assertEqual(regla('AR: TyC Sports (FHD)', limpiar=True), 'TyC Sports')
        self.assertEqual(regla('LA CASA DE PAPEL', mayusculas=True), 'La Casa de Papel')
        self.assertEqual(regla('canal ESPN 2 en vivo', mayusculas=True), 'Canal ESPN 2 en Vivo')
        self.assertEqual(regla('HD', sacar='HD'), 'HD')   # si no queda nada, queda como estaba

    def test_vista_previa_sin_tocar_nada(self):
        tyc = self.canal('TyC Sports HD')
        r = self.client.post(RENOMBRAR, {'canal': [self.espn.pk, tyc.pk], 'sacar': ' HD', 'vista_previa': '1'},
                             **JSON).json()
        self.assertEqual(r['elegidos'], 2)
        self.assertEqual([(c['antes'], c['despues']) for c in r['cambios']],
                         [('ESPN HD', 'ESPN'), ('TyC Sports HD', 'TyC Sports')])
        self.espn.refresh_from_db()
        self.assertEqual(self.espn.nombre, 'ESPN HD')

    def test_aplicarlo_canales_y_series(self):
        for numero in (1, 2):
            self.canal(f'MASHA S01 E0{numero}', contenido='serie')
        self.client.post(RENOMBRAR, {'canal': [self.espn.pk], 'sacar': 'HD', 'volver': '/canales/organizar/'})
        self.espn.refresh_from_db()
        self.assertEqual(self.espn.nombre, 'ESPN')
        respuesta = self.client.post(RENOMBRAR, {'serie': ['MASHA'], 'mayusculas': '1'}, follow=True)
        self.assertContains(respuesta, 'Se cambió el nombre de 1.')
        self.assertEqual(sorted(Canal.objects.filter(contenido='serie').values_list('nombre', flat=True)),
                         ['Masha S01 E01', 'Masha S01 E02'])

    def test_una_serie_que_se_pisaria_con_otra_se_saltea(self):
        self.canal('Bluey S01 E01', contenido='serie')
        self.canal('Bluey HD S01 E01', contenido='serie')
        respuesta = self.client.post(RENOMBRAR, {'serie': ['Bluey HD'], 'sacar': ' HD'}, follow=True)
        self.assertContains(respuesta, 'no se cambió')
        self.assertTrue(Canal.objects.filter(nombre='Bluey HD S01 E01').exists())


class ChipsYVecinasTests(Base):

    def test_cuantos_hay_de_cada_uno(self):
        self.canal('TN', categoria=self.noticias, logo='https://x/tn.png')
        self.canal('C5N', anda=False, categoria=self.noticias)
        self.canal('Quitado', activo=False)
        Canal.objects.filter(pk=self.espn.pk).update(destacado=True)
        cuentas = consultas.cuentas_de_organizar('vivo')
        self.assertEqual((cuentas['todo'], cuentas['app'], cuentas['fuera'], cuentas['quitados'],
                          cuentas['destacados'], cuentas['sin_logo']), (4, 2, 2, 1, 1, 3))
        # Con una categoría elegida, cuenta solo lo de esa categoría
        self.assertEqual(consultas.cuentas_de_organizar('vivo', categoria=str(self.noticias.pk))['todo'], 2)

    def test_la_pagina_muestra_los_chips_y_el_panel(self):
        self.canal('TN', categoria=self.noticias)
        pagina = self.client.get(reverse('canales:organizar'), {'contenido': 'vivo'}).content.decode()
        self.assertIn('No se ven <span>0</span>', pagina)
        self.assertIn('Sin imagen <span>2</span>', pagina)
        self.assertIn('id="editor"', pagina)
        self.assertIn(f'data-url-cambiar="{CAMBIAR}"', pagina)
        self.assertIn('id="selector-categoria"', pagina)

    def test_chip_sin_imagen_filtra(self):
        self.canal('TN', logo='https://x/tn.png')
        pagina = self.client.get(reverse('canales:organizar'), {'contenido': 'vivo', 'sin_logo': '1'}).content.decode()
        self.assertIn('ESPN HD', pagina)
        self.assertNotIn('>TN<', pagina)

    def test_series_vecinas_de_la_misma_categoria(self):
        animadas = Categoria.objects.create(nombre='Animadas', contenido='serie')
        for nombre in ('Bluey', 'Masha', 'Pocoyó'):
            self.canal(f'{nombre} S01 E01', contenido='serie', categoria=animadas)
        self.canal('Otra S01 E01', contenido='serie')
        self.assertEqual(consultas.series_vecinas('Masha'), ('Bluey', 'Pocoyó'))
        self.assertEqual(consultas.series_vecinas('Bluey'), ('', 'Masha'))
        self.assertEqual(consultas.series_vecinas('No existe'), ('', ''))

    def test_la_pagina_de_la_serie_se_edita_ahi_mismo_y_lleva_a_las_de_al_lado(self):
        animadas = Categoria.objects.create(nombre='Animadas', contenido='serie')
        for nombre in ('Bluey', 'Masha', 'Pocoyó'):
            self.canal(f'{nombre} S01 E01', contenido='serie', categoria=animadas)
        pagina = self.client.get(reverse('canales:serie_detalle'), {'nombre': 'Masha'}).content.decode()
        self.assertIn('href="?nombre=Bluey"', pagina)
        self.assertIn('href="?nombre=Pocoy%C3%B3"', pagina)
        self.assertIn('data-portada', pagina)
        self.assertIn('data-serie-nombre', pagina)
        self.assertIn(f'<option value="{animadas.pk}" selected>Animadas</option>', pagina)
        self.assertIn('data-capitulo-imagen=', pagina)
        self.assertIn('js/serie_trabajo.js', pagina)
        # Volver a Series deja la tarjeta de esta serie a la vista
        self.assertIn('ir=s:Masha', pagina)

    def test_siguiente_pagina_para_el_panel(self):
        for numero in range(125):
            Canal.objects.create(nombre=f'Canal {numero:03d}')
        pagina = self.client.get(reverse('canales:organizar'), {'contenido': 'vivo'}).content.decode()
        self.assertIn('data-pagina-siguiente="/canales/organizar/?contenido=vivo&amp;pagina=2"', pagina)
        self.assertIn('data-pagina-anterior=""', pagina)
