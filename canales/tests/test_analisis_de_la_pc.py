"""
La lista limpia del analizador de canales con lo que midió (#KAIROS-ANALISIS): el panel no vuelve a juzgar ni a probar
lo que se midió en la PC. Solo revisa lo que la PC no puede saber (ya estaba cargada, el canal quitado, la serie sin el
capítulo 1, lo medido viejo o vencido, un video de YouTube que el dueño no deja ver afuera), cada cosa vuelve a su
lugar con su tipo (HLS, página web, YouTube...) y, antes de apagar o de volver a prender, muestra qué haría. Una lista
sin esos datos se importa como siempre.
"""

from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from canales import servicios
from canales.m3u import leer_analisis, leer_m3u
from canales.models import Canal, Categoria, Contenido, EntradaImportada, Fuente, Importacion
from canales.verificacion import CAIDA, FUNCIONA, Resultado
from usuarios.models import Rol, Usuario

Estado = EntradaImportada.Estado


def _lista(*sellos, no_sirven=(), por_confirmar=(), version=5):
    """
    Una lista limpia como la del analizador. Cada sello: (url, medida, estado='anda', vence='', **lo demás del sello),
    con 'extinf' para cambiar lo que dice la lista de la señal (por defecto, un canal en vivo de Noticias).
    """
    lineas = ['#EXTM3U']
    for url, *_ in sellos:
        extra = _extra(sellos, url)
        extinf = extra.get('extinf') or f'tvg-name="C" group-title="Noticias" kairos-seccion="vivo",Canal {url[-6:]}'
        lineas += [f'#EXTINF:-1 {extinf}', url]
    lineas += [f'#KAIROS-NO-SIRVE url="{url}" motivo="{motivo}" causa="{causa}"' for url, motivo, causa in no_sirven]
    lineas += [f'#KAIROS-POR-CONFIRMAR url="{url}" motivo="{motivo}" causa="{causa}"'
               for url, motivo, causa in por_confirmar]
    lineas.append(f'#KAIROS-ANALISIS version="{version}" fecha="{timezone.now().isoformat()}"')
    for url, medida, *resto in sellos:
        estado = resto[0] if resto and isinstance(resto[0], str) else 'anda'
        vence = resto[1] if len(resto) > 1 and isinstance(resto[1], str) else ''
        demas = ''.join(f' {clave}="{valor}"' for clave, valor in _extra(sellos, url).items() if clave != 'extinf')
        lineas.append(f'#KAIROS-ANDA url="{url}" medida="{medida.isoformat()}" version="{version}" estado="{estado}" '
                      f'vence="{vence}"{demas}')
    return '\n'.join(lineas) + '\n'


def _extra(sellos, url):
    sello = next(s for s in sellos if s[0] == url)
    return next((parte for parte in sello if isinstance(parte, dict)), {})


class LeerTests(TestCase):
    def test_lee_lo_que_midio(self):
        ahora = timezone.now()
        lo_medido = {'motivo': 'Se trabó una vez', 'tipo': 'hls', 'codec': 'h264', 'calidad': '1080p · H.264'}
        analisis = leer_analisis(_lista(
            ('http://a.com/a.m3u8', ahora, 'dudosa', '', lo_medido),
            no_sirven=[('http://b.com/b.ts', 'Cayó', 'proveedor')],
            por_confirmar=[('http://c.com/c.ts', 'Falló una vez', 'otro_horario')]))
        self.assertEqual(analisis['version'], 5)
        sello = analisis['anda']['http://a.com/a.m3u8']
        self.assertEqual((sello['estado'], sello['motivo'], sello['tipo'], sello['codec'], sello['calidad']),
                         ('dudosa', 'Se trabó una vez', 'hls', 'h264', '1080p · H.264'))
        self.assertEqual(analisis['no_sirven']['http://b.com/b.ts'], {'motivo': 'Cayó', 'causa': 'proveedor'})
        self.assertEqual(analisis['por_confirmar'],
                         {'http://c.com/c.ts': {'motivo': 'Falló una vez', 'causa': 'otro_horario'}})

    def test_una_lista_comun_no_trae_analisis(self):
        self.assertIsNone(leer_analisis('#EXTM3U\n#EXTINF:-1,A\nhttp://a.com/a.m3u8\n'))
        self.assertIsNone(leer_analisis('#EXTM3U\n#KAIROS-NO-SIRVE url="http://a.com/a" motivo="x"\n'))

    def test_las_lineas_del_analisis_no_se_leen_como_canales(self):
        entradas = leer_m3u(_lista(('http://a.com/a.m3u8', timezone.now())))
        self.assertEqual([entrada.url for entrada in entradas], ['http://a.com/a.m3u8'])

    def test_lee_el_tipo_que_tenia_en_el_panel(self):
        entrada, = leer_m3u('#EXTM3U\n#EXTINF:-1 kairos-seccion="vivo" kairos-tipo="web",Canal\nhttps://a.com/x\n')
        self.assertEqual(entrada.tipo_lista, 'web')


class PorQueMirarlaTests(TestCase):
    def setUp(self):
        self.ahora = timezone.now()

    def _sello(self, **campos):
        return {'medida': self.ahora.isoformat(), 'version': 4, 'estado': 'anda', 'vence': '', **campos}

    def test_medida_hace_poco_no_se_discute(self):
        self.assertEqual(servicios.por_que_mirarla(self._sello(), self.ahora), '')

    def test_vieja(self):
        vieja = (self.ahora - timedelta(days=9)).isoformat()
        self.assertIn('hace 9 días', servicios.por_que_mirarla(self._sello(medida=vieja), self.ahora))

    def test_con_una_version_vieja_del_analizador(self):
        self.assertIn('versión vieja', servicios.por_que_mirarla(self._sello(version=3), self.ahora))

    def test_le_vencio_el_permiso(self):
        vencio = (self.ahora - timedelta(hours=1)).isoformat()
        self.assertIn('Venció el permiso', servicios.por_que_mirarla(self._sello(vence=vencio), self.ahora))

    def test_sin_fecha(self):
        self.assertIn('no dice cuándo', servicios.por_que_mirarla(self._sello(medida=''), self.ahora))


class ProbarLaListaTests(TestCase):
    def _procesar(self, texto, respuestas=None, **opciones):
        importacion = servicios.preparar_importacion(texto, 'limpia.m3u', **opciones)
        self.pedidos = []

        def verificar(fuentes, cabeceras=None, hasta=None, a_fondo=None):
            self.pedidos.append((sorted(fuentes), a_fondo))
            return {url: (respuestas or {}).get(url, Resultado(FUNCIONA, tipo=fuentes[url])) for url in fuentes}

        servicios.procesar_lote(importacion, verificar)
        importacion.refresh_from_db()
        return importacion

    def test_lo_medido_en_la_pc_no_se_vuelve_a_probar_ni_a_juzgar(self):
        importacion = self._procesar(_lista(('http://a.com/a.m3u8', timezone.now(), 'anda', '',
                                             {'codec': 'h265', 'calidad': '1080p · H.265 · audio AAC (es)',
                                              'idioma': 'es'})))
        entrada = importacion.entradas.get()
        self.assertEqual(entrada.estado, Estado.APTA)
        self.assertIn('Anduvo en tu PC', entrada.motivo)
        self.assertEqual(self.pedidos, [], 'no sale a internet: lo decidió la PC')
        # Se queda con lo que midió la PC, para cargarla con eso
        self.assertEqual((entrada.estado_fuente, entrada.codec, entrada.calidad, entrada.idioma),
                         (Fuente.Estado.FUNCIONA, 'h265', '1080p · H.265 · audio AAC (es)', 'es'))

    def test_si_no_se_sabe_el_tipo_se_mira_corto_y_un_fallo_desde_el_servidor_no_la_desmiente(self):
        # Una Xtream sin extensión en una lista vieja (sin kairos-tipo ni el tipo que usó la PC)
        caida = Resultado(CAIDA, error='No respondió a tiempo.', tipo='directo')
        url = 'http://a.com:8080/ana/clave/123'
        importacion = self._procesar(_lista((url, timezone.now())), {url: caida})
        entrada = importacion.entradas.get()
        self.assertEqual(self.pedidos, [([url], False)])
        self.assertEqual((entrada.estado, entrada.tipo), (Estado.APTA, 'directo'))
        self.assertEqual(entrada.estado_fuente, Fuente.Estado.SIN_VERIFICAR)
        self.assertIn('no la desmiente', entrada.motivo)

    def test_el_tipo_que_uso_la_pc_alcanza(self):
        url = 'http://a.com:8080/ana/clave/123'
        importacion = self._procesar(_lista((url, timezone.now(), 'anda', '', {'tipo': 'directo'})))
        self.assertEqual(self.pedidos, [])
        self.assertEqual(importacion.entradas.get().tipo, 'directo')

    def test_un_video_de_youtube_se_mira_en_youtube(self):
        # Lo único que la PC no puede saber: si el dueño deja verlo fuera de YouTube (el reproductor oficial lo pide)
        pelicula = 'tvg-name="Tormenta" group-title="Acción" kairos-seccion="pelicula" kairos-tipo="yt_video",Tormenta'
        bien, privado = 'https://www.youtube.com/watch?v=aaaaaaaaaaa', 'https://www.youtube.com/watch?v=bbbbbbbbbbb'
        importacion = self._procesar(
            _lista((bien, timezone.now(), 'sin_confirmar', '', {'extinf': pelicula}),
                   (privado, timezone.now(), 'anda', '', {'extinf': pelicula.replace('Tormenta', 'Otra')})),
            {privado: Resultado(CAIDA, 'El dueño no deja verlo fuera de YouTube.', tipo='yt_video')})
        self.assertEqual(self.pedidos, [([bien, privado], False)])
        self.assertEqual(importacion.entradas.get(url=bien).estado, Estado.APTA)
        no = importacion.entradas.get(url=privado)
        self.assertEqual((no.estado, no.motivo), (Estado.CAIDA, 'El dueño no deja verlo fuera de YouTube.'))

    def test_las_dudosas_se_cargan_con_la_duda_a_la_vista(self):
        importacion = self._procesar(_lista(('http://a.com/a.m3u8', timezone.now(), 'dudosa', '',
                                             {'motivo': 'Se trabó una vez 8 s'})))
        entrada = importacion.entradas.get()
        self.assertEqual(entrada.estado, Estado.APTA)
        self.assertIn('Dudosa en tu PC', entrada.motivo)
        self.assertIn('Se trabó una vez 8 s', entrada.motivo)
        self.assertEqual(servicios.resumen_del_analisis(importacion)['dudosas'], 1)

    def test_lo_que_la_pc_no_pudo_juzgar_queda_para_mirar(self):
        importacion = self._procesar(_lista(('http://a.com/a.m3u8', timezone.now(), 'sin_juzgar', '',
                                             {'motivo': 'Sin lugar en la cuenta'})))
        entrada = importacion.entradas.get()
        self.assertEqual((entrada.estado, entrada.causa), (Estado.RECHAZADA, 'para_mirar'))
        self.assertIn('no se pudo juzgar: Sin lugar en la cuenta', entrada.motivo)

    def test_lo_viejo_queda_para_mirar_y_se_puede_cargar_igual(self):
        vieja = timezone.now() - timedelta(days=30)
        importacion = self._procesar(_lista(('http://a.com/a.m3u8', vieja)))
        entrada = importacion.entradas.get()
        self.assertEqual((entrada.estado, entrada.causa), (Estado.RECHAZADA, 'para_mirar'))
        self.assertIn(Estado.RECHAZADA, servicios.SE_PUEDEN_CARGAR_IGUAL)

    def test_las_opciones_de_la_subida_no_descartan_lo_que_salio_de_aca(self):
        # «Solo en español» descartaría un canal de EE. UU. de una lista cualquiera; este ya estaba aceptado acá
        extinf = 'tvg-name="ESPN" tvg-country="US" group-title="Deportes" kairos-seccion="vivo",ESPN'
        importacion = self._procesar(_lista(('http://a.com/a.m3u8', timezone.now(), 'anda', '', {'extinf': extinf})),
                                     solo_espanol=True, descartar_sin_logo=True)
        self.assertEqual(importacion.entradas.get().estado, Estado.APTA)

    def test_lo_que_no_trae_sello_se_prueba_como_siempre(self):
        texto = _lista(('http://a.com/a.m3u8', timezone.now()))
        texto = texto.replace('#EXTINF:-1 tvg-name="C" group-title="Noticias" kairos-seccion="vivo",Canal a.m3u8',
                              '#EXTINF:-1,Otro\nhttp://otra.com/b.m3u8\n#EXTINF:-1,Canal')
        importacion = self._procesar(texto)
        self.assertEqual(importacion.entradas.count(), 2)
        self.assertEqual(self.pedidos, [(['http://otra.com/b.m3u8'], None)])

    def test_una_lista_sin_analisis_se_prueba_como_siempre(self):
        importacion = self._procesar('#EXTM3U\n#EXTINF:-1,A\nhttp://a.com/a.m3u8\n')
        self.assertEqual(self.pedidos, [(['http://a.com/a.m3u8'], None)])
        self.assertEqual(importacion.analisis, {})


class TodoJuntoYEnSuLugarTests(TestCase):
    """Una lista que salió de este panel, pasó por la PC y vuelve: cada cosa a su sección, categoría y canal."""

    def setUp(self):
        self.deportes = Categoria.objects.create(nombre='Deportes')
        self.espn = Canal.objects.create(nombre='ESPN', categoria=self.deportes)
        Fuente.objects.create(canal=self.espn, url='http://ya.com/espn.m3u8', prioridad=1)
        ahora = timezone.now()
        espn = 'tvg-name="ESPN" group-title="Deportes" kairos-seccion="vivo" kairos-tipo="hls",ESPN'
        vivo = 'group-title="Deportes" kairos-seccion="vivo"'
        self.texto = _lista(
            ('http://nueva.com/espn.m3u8', ahora, 'anda', '', {'extinf': espn, 'codec': 'h264', 'calidad': '720p'}),
            ('http://ya.com/espn.m3u8', ahora, 'anda', '', {'extinf': espn}),
            ('https://pagina.com/eventos.html', ahora, 'anda', '',
             {'extinf': f'tvg-name="Pelota" {vivo} kairos-tipo="web",Pelota'}),
            ('https://www.youtube.com/watch?v=aaaaaaaaaaa', ahora, 'sin_confirmar', '',
             {'extinf': 'tvg-name="Tormenta" group-title="Acción" kairos-seccion="pelicula" kairos-tipo="yt_video",'
                        'Tormenta'}),
            ('http://series.com/e1.mkv', ahora, 'anda', '',
             {'extinf': 'tvg-name="Electro S01 E01" group-title="Juveniles" kairos-seccion="serie" '
                        'kairos-tipo="directo",Electro S01 E01'}))

    def test_una_sola_importacion_con_todo_y_cada_cosa_en_su_lugar(self):
        pedidos = []

        def verificar(fuentes, cabeceras=None, hasta=None, a_fondo=None):
            pedidos.append(sorted(fuentes))
            return {url: Resultado(FUNCIONA, tipo=tipo) for url, tipo in fuentes.items()}

        servicios.importar_m3u(self.texto, 'kairos-limpia.m3u', verificar=verificar)
        self.assertEqual(pedidos, [['https://www.youtube.com/watch?v=aaaaaaaaaaa']], 'solo YouTube se mira')
        importacion = Importacion.objects.get()
        self.assertTrue(importacion.de_kairos)
        self.assertIn('queda como está', importacion.entradas.get(url='http://ya.com/espn.m3u8').motivo)

        nueva = Fuente.objects.get(url='http://nueva.com/espn.m3u8')
        self.assertEqual((nueva.canal, nueva.tipo, nueva.estado, nueva.codec, nueva.alto),
                         (self.espn, 'hls', Fuente.Estado.FUNCIONA, 'h264', 720), 'se suma al canal que ya estaba')
        web = Fuente.objects.get(url='https://pagina.com/eventos.html')
        self.assertEqual((web.tipo, web.canal.nombre, web.canal.categoria, web.canal.contenido),
                         ('web', 'Pelota', self.deportes, Contenido.VIVO))
        youtube = Fuente.objects.get(url='https://www.youtube.com/watch?v=aaaaaaaaaaa')
        self.assertEqual((youtube.tipo, youtube.canal.contenido, youtube.canal.categoria.nombre),
                         ('yt_video', Contenido.PELICULA, 'Acción'))
        capitulo = Fuente.objects.get(url='http://series.com/e1.mkv')
        self.assertEqual((capitulo.tipo, capitulo.canal.contenido, capitulo.canal.categoria.nombre),
                         ('directo', Contenido.SERIE, 'Juveniles'), 'una serie de acá entra desde su capítulo 1')
        self.assertEqual(Fuente.objects.filter(url='http://ya.com/espn.m3u8').count(), 1)

    def test_un_canal_quitado_a_mano_no_vuelve(self):
        self.espn.activo = False
        self.espn.save()
        servicios.importar_m3u(self.texto, 'kairos-limpia.m3u')
        self.assertFalse(Fuente.objects.filter(url='http://nueva.com/espn.m3u8').exists())
        self.assertIn('está quitado', Importacion.objects.get().entradas.get(url='http://nueva.com/espn.m3u8').motivo)


class LaPantallaTests(TestCase):
    def setUp(self):
        rol = Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales'])
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=rol))
        self.tn = Canal.objects.create(nombre='TN')
        self.mala = Fuente.objects.create(canal=self.tn, url='http://cae.com/tn.m3u8', prioridad=1)
        self.otra = Fuente.objects.create(canal=self.tn, url='http://cae.com/tn2.m3u8', prioridad=2)
        self.no_sirven = [('http://cae.com/tn.m3u8', 'Cayó la cuenta o el proveedor', 'proveedor'),
                          ('http://cae.com/tn2.m3u8', 'Pantalla negra', 'negra'),
                          ('http://no-cargada.com/x.ts', 'Se corta', 'se_corta')]

    def subir(self, texto, **extra):
        archivo = SimpleUploadedFile('limpia.m3u', texto.encode(), content_type='audio/x-mpegurl')
        return self.client.post(reverse('canales:inicio'), {'archivo': archivo, 'descartar_adultos': 'on'}, **extra)

    def test_no_apaga_nada_hasta_que_se_decide_y_muestra_que_se_apagaria(self):
        respuesta = self.subir(_lista(('http://a.com/a.m3u8', timezone.now()), no_sirven=self.no_sirven), follow=True)
        pagina = respuesta.content.decode()
        self.mala.refresh_from_db()
        self.assertTrue(self.mala.activa)
        self.assertIn('Antes de apagar', pagina)
        self.assertIn('Cayó la cuenta o el proveedor', pagina)
        self.assertNotIn('no-cargada.com', pagina, 'lo que no está cargado no se apaga')

    def test_apaga_solo_las_marcadas(self):
        self.subir(_lista(('http://a.com/a.m3u8', timezone.now()), no_sirven=self.no_sirven))
        importacion = Importacion.objects.get()
        self.assertEqual(len(importacion.por_apagar), 2)
        self.client.post(reverse('canales:importacion_apagar', args=[importacion.pk]),
                         {'accion': 'apagar', 'urls': ['http://cae.com/tn.m3u8']})
        self.mala.refresh_from_db()
        self.otra.refresh_from_db()
        self.assertFalse(self.mala.activa)
        self.assertIn('Cayó la cuenta', self.mala.motivo_quitada)
        self.assertTrue(self.otra.activa)
        importacion.refresh_from_db()
        self.assertEqual(importacion.por_apagar, [])

    def test_lo_que_fallo_una_sola_vez_se_ofrece_sin_marcar(self):
        respuesta = self.subir(_lista(por_confirmar=[('http://cae.com/tn.m3u8', 'Falló una vez: error 403',
                                                      'otro_horario')]), follow=True)
        pagina = respuesta.content.decode()
        self.assertIn('Falló una sola vez', pagina)
        self.assertRegex(pagina, r'value="http://cae.com/tn.m3u8">')   # sin «checked»
        self.mala.refresh_from_db()
        self.assertTrue(self.mala.activa)

    def test_no_apagar_ninguna(self):
        self.subir(_lista(('http://a.com/a.m3u8', timezone.now()), no_sirven=self.no_sirven))
        importacion = Importacion.objects.get()
        self.client.post(reverse('canales:importacion_apagar', args=[importacion.pk]), {'accion': 'no'})
        self.mala.refresh_from_db()
        self.assertTrue(self.mala.activa)

    def test_una_lista_que_solo_trae_las_que_no_sirven_tambien_pregunta(self):
        respuesta = self.subir(_lista(no_sirven=self.no_sirven), follow=True)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('Antes de apagar', respuesta.content.decode())
        self.mala.refresh_from_db()
        self.assertTrue(self.mala.activa)

    def test_si_no_hay_nada_para_apagar_no_crea_una_lista_vacia(self):
        self.subir(_lista(no_sirven=[('http://no-cargada.com/x.ts', 'Se corta', 'se_corta')]))
        self.assertFalse(Importacion.objects.exists())

    def test_sin_permiso_no_se_apaga(self):
        self.subir(_lista(('http://a.com/a.m3u8', timezone.now()), no_sirven=self.no_sirven))
        importacion = Importacion.objects.get()
        rol = Rol.objects.create(nombre='Solo ver', permisos=['ver_canales'])
        self.client.force_login(Usuario.objects.create_user('ana', None, 'x', rol=rol))
        respuesta = self.client.post(reverse('canales:importacion_apagar', args=[importacion.pk]),
                                     {'accion': 'apagar', 'urls': ['http://cae.com/tn.m3u8']})
        self.assertEqual(respuesta.status_code, 403)
        self.mala.refresh_from_db()
        self.assertTrue(self.mala.activa)


class VolverAPrenderTests(TestCase):
    """Ya estaban cargadas pero apagadas, y en la PC anduvieron: se ofrecen para prender (nunca solas)."""

    def setUp(self):
        rol = Rol.objects.create(nombre='Canales', permisos=['ver_canales', 'importar_canales'])
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=rol))
        tn = Canal.objects.create(nombre='TN')
        self.del_analizador = Fuente.objects.create(canal=tn, url='http://a.com/1.m3u8', activa=False,
                                                    motivo_quitada='El analizador de canales (03/11): No abre')
        self.retirada = Fuente.objects.create(canal=tn, url='http://a.com/2.m3u8', activa=False,
                                              retirada=timezone.now(), estado=Fuente.Estado.CAIDA)
        self.a_mano = Fuente.objects.create(canal=tn, url='http://a.com/3.m3u8', activa=False)
        self.prendida = Fuente.objects.create(canal=tn, url='http://a.com/4.m3u8')
        self.dudosa = Fuente.objects.create(canal=tn, url='http://a.com/5.m3u8', activa=False,
                                            motivo_quitada='El analizador de canales (03/11): Se corta')
        ahora = timezone.now()
        self.texto = _lista(*((f'http://a.com/{n}.m3u8', ahora) for n in range(1, 5)),
                            ('http://a.com/5.m3u8', ahora, 'dudosa'))

    def subir(self):
        archivo = SimpleUploadedFile('limpia.m3u', self.texto.encode(), content_type='audio/x-mpegurl')
        return self.client.post(reverse('canales:inicio'), {'archivo': archivo}, follow=True)

    def test_ofrece_las_apagadas_que_anduvieron_y_solo_marca_las_que_no_apagaste_vos(self):
        pagina = self.subir().content.decode()
        importacion = Importacion.objects.get()
        filas = {fila['url']: fila for fila in importacion.por_prender}
        self.assertEqual(set(filas), {'http://a.com/1.m3u8', 'http://a.com/2.m3u8', 'http://a.com/3.m3u8'},
                         'ni la prendida ni la dudosa')
        self.assertTrue(filas['http://a.com/3.m3u8']['sin_marcar'])
        self.assertFalse(filas['http://a.com/1.m3u8']['sin_marcar'])
        self.assertIn('¿las volvés a prender?', pagina)
        self.assertIn('La retiró la limpieza', pagina)
        self.assertEqual(importacion.entradas.filter(estado=Estado.REPETIDA).count(), 5)
        self.del_analizador.refresh_from_db()
        self.assertFalse(self.del_analizador.activa, 'nada se prende solo')

    def test_prende_las_elegidas(self):
        self.subir()
        importacion = Importacion.objects.get()
        self.client.post(reverse('canales:importacion_prender', args=[importacion.pk]),
                         {'accion': 'prender', 'urls': ['http://a.com/1.m3u8', 'http://a.com/2.m3u8']})
        for fuente in (self.del_analizador, self.retirada, self.a_mano):
            fuente.refresh_from_db()
        self.assertEqual((self.del_analizador.activa, self.del_analizador.motivo_quitada), (True, ''))
        self.assertEqual((self.retirada.activa, self.retirada.retirada, self.retirada.estado),
                         (True, None, Fuente.Estado.SIN_VERIFICAR))
        self.assertFalse(self.a_mano.activa)
        importacion.refresh_from_db()
        self.assertEqual(importacion.por_prender, [])

    def test_no_prender_ninguna(self):
        self.subir()
        importacion = Importacion.objects.get()
        self.client.post(reverse('canales:importacion_prender', args=[importacion.pk]), {'accion': 'no'})
        self.del_analizador.refresh_from_db()
        self.assertFalse(self.del_analizador.activa)
        importacion.refresh_from_db()
        self.assertEqual(importacion.por_prender, [])

    def test_lo_medido_hace_mucho_no_alcanza(self):
        vieja = timezone.now() - timedelta(days=20)
        self.assertEqual(servicios.lo_que_se_prenderia(leer_analisis(_lista(('http://a.com/1.m3u8', vieja)))['anda']),
                         [])
