"""La Agenda: qué le llega a la app, la API y el panel (cargar, editar, eliminar)."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from agenda import servicios
from agenda.models import Evento
from api import tokens
from canales.models import Canal
from usuarios.models import Rol, Usuario


def _canal(nombre='TyC Sports', **datos):
    return Canal.objects.create(nombre=nombre, **datos)


class LoQueLlegaALaAppTests(TestCase):

    def setUp(self):
        self.ahora = timezone.now()
        self.canal = _canal()

    def _evento(self, titulo, empieza, termina=None, canal=True):
        return Evento.objects.create(titulo=titulo, canal=self.canal if canal else None,
                                     empieza=self.ahora + empieza,
                                     termina=self.ahora + termina if termina is not None else None)

    def test_va_lo_que_viene_y_lo_que_se_esta_dando(self):
        self._evento('Mañana', timedelta(days=1))
        self._evento('Ahora', timedelta(minutes=-30), timedelta(minutes=60))
        self._evento('Sin fin, empezó hace una hora', timedelta(hours=-1))
        titulos = [e.titulo for e in servicios.para_la_app(self.ahora)]
        self.assertEqual(titulos, ['Sin fin, empezó hace una hora', 'Ahora', 'Mañana'])

    def test_no_va_lo_que_termino_lo_sin_canal_ni_lo_muy_lejano(self):
        self._evento('Terminó', timedelta(hours=-3), timedelta(hours=-1))
        self._evento('Sin fin, hace 3 horas', timedelta(hours=-3))
        self._evento('Sin canal', timedelta(hours=2), canal=False)
        self._evento('En un mes', timedelta(days=30))
        self.assertEqual(list(servicios.para_la_app(self.ahora)), [])

    def test_si_el_canal_se_borra_no_va(self):
        self._evento('Partido', timedelta(hours=2))
        self.canal.eliminar()
        self.assertEqual(list(servicios.para_la_app(self.ahora)), [])

    def test_la_api_lo_manda_con_el_canal_y_las_horas(self):
        evento = self._evento('Boca vs River', timedelta(hours=5))
        app = APIClient()
        self.assertEqual(app.get(reverse('api_v1:agenda')).status_code, 401)   # sin sesión, nada
        clave, _ = tokens.crear_token(Usuario.objects.create_user('cliente', None, 'x'))
        app.credentials(HTTP_AUTHORIZATION=f'Bearer {clave}')
        datos = app.get(reverse('api_v1:agenda')).json()
        self.assertEqual(datos['eventos'], [{
            'id': evento.pk, 'titulo': 'Boca vs River', 'detalle': '', 'tipo': 'futbol', 'canal': self.canal.pk,
            'empieza': evento.empieza.isoformat(), 'termina': (evento.empieza + timedelta(hours=2)).isoformat(),
        }])


class AgendaEnElPanelTests(TestCase):

    def setUp(self):
        rol = Rol.objects.create(nombre='Contenido', permisos=['ver_canales', 'importar_canales'])
        self.client.force_login(Usuario.objects.create_user('marcos', None, 'x', rol=rol))
        self.canal = _canal(numero='101')
        self.radio_de_peliculas = _canal('Una película', contenido='pelicula')

    def test_cargar_un_evento(self):
        respuesta = self.client.get(reverse('agenda:nuevo'))
        self.assertContains(respuesta, 'TyC Sports (101)')
        self.assertNotContains(respuesta, 'Una película')   # solo se eligen canales en vivo
        respuesta = self.client.post(reverse('agenda:nuevo'), {
            'titulo': 'Boca vs River', 'tipo': 'futbol', 'canal': self.canal.pk,
            'empieza': '2026-10-18T21:00', 'termina': '',
        })
        self.assertRedirects(respuesta, reverse('agenda:lista'))
        evento = Evento.objects.get()
        self.assertEqual(timezone.localtime(evento.empieza).strftime('%d/%m %H:%M'), '18/10 21:00')
        self.assertEqual(evento.fin - evento.empieza, timedelta(hours=2))

    def test_termina_tiene_que_ser_despues(self):
        respuesta = self.client.post(reverse('agenda:nuevo'), {
            'titulo': 'Al revés', 'tipo': 'futbol', 'canal': self.canal.pk,
            'empieza': '2026-10-18T21:00', 'termina': '2026-10-18T20:00',
        })
        self.assertContains(respuesta, 'Tiene que ser después de que empieza.')
        self.assertFalse(Evento.objects.exists())

    def test_guardar_y_cargar_otro_igual_copia_canal_y_tipo(self):
        respuesta = self.client.post(reverse('agenda:nuevo'), {
            'titulo': 'Fecha 1', 'detalle': 'Torneo', 'tipo': 'deporte', 'canal': self.canal.pk,
            'empieza': '2026-10-18T21:00', 'y_otro': '',
        })
        primero = Evento.objects.get()
        self.assertRedirects(respuesta, f"{reverse('agenda:nuevo')}?copiar={primero.pk}")
        formulario = self.client.get(respuesta.url).context['form']
        self.assertEqual(formulario.initial['canal'], self.canal.pk)
        self.assertEqual(formulario.initial['tipo'], 'deporte')

    def test_la_lista_avisa_lo_que_no_tiene_canal(self):
        Evento.objects.create(titulo='Sin canal', empieza=timezone.now() + timedelta(hours=3))
        Evento.objects.create(titulo='Con canal', canal=self.canal, empieza=timezone.now() + timedelta(hours=4))
        respuesta = self.client.get(reverse('agenda:lista'))
        self.assertContains(respuesta, '1 evento sin canal')
        self.assertContains(respuesta, 'Falta el canal')
        self.assertContains(respuesta, 'Hoy')

    def test_eliminar(self):
        evento = Evento.objects.create(titulo='Partido', canal=self.canal, empieza=timezone.now())
        self.client.post(reverse('agenda:eliminar', args=[evento.pk]))
        self.assertFalse(Evento.objects.exists())
        self.assertTrue(Evento.todos.filter(pk=evento.pk).exists())   # baja lógica

    def test_sin_permiso_de_contenido_no_entra(self):
        self.client.force_login(Usuario.objects.create_user('otro', None, 'x', rol=Rol.objects.create(
            nombre='Ventas', permisos=[])))
        self.assertEqual(self.client.get(reverse('agenda:lista')).status_code, 403)

    def test_quien_solo_ve_no_puede_cargar(self):
        self.client.force_login(Usuario.objects.create_user('mira', None, 'x', rol=Rol.objects.create(
            nombre='Mira', permisos=['ver_canales'])))
        respuesta = self.client.get(reverse('agenda:lista'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, 'Nuevo evento')
        self.assertEqual(self.client.get(reverse('agenda:nuevo')).status_code, 403)
