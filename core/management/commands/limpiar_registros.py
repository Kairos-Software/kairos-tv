"""
Borra lo viejo del registro de actividad, las notificaciones ya leídas y
las sesiones de la app vencidas. Además empieza el mes de los clientes a
los que se les termina y tienen saldo (reventa.servicios.renovar_los_que_tocan),
y avisa de los que no les alcanza.

    python manage.py limpiar_registros

Los días se configuran en el .env (ACTIVIDAD_DIAS_CONSERVAR,
NOTIFICACIONES_DIAS_CONSERVAR). Conviene programarlo una vez por día en el
servidor (cron o systemd timer).
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from actividad.models import RegistroActividad
from api.tokens import borrar_vencidos
from notificaciones.models import Notificacion
from reventa.servicios import renovar_los_que_tocan


class Command(BaseCommand):
    help = 'Borra la actividad vieja y las notificaciones leídas antiguas.'

    def handle(self, *args, **options):
        ahora = timezone.now()
        limite_actividad = ahora - timedelta(days=settings.ACTIVIDAD_DIAS_CONSERVAR)
        limite_notificaciones = ahora - timedelta(days=settings.NOTIFICACIONES_DIAS_CONSERVAR)

        actividad, _ = RegistroActividad.objects.filter(fecha__lt=limite_actividad).delete()
        notificaciones, _ = Notificacion.objects.filter(
            leida_en__isnull=False, creada__lt=limite_notificaciones,
        ).delete()
        tokens = borrar_vencidos()
        renovados, sin_saldo = renovar_los_que_tocan()

        self.stdout.write(self.style.SUCCESS(
            f'Actividad borrada: {actividad} registro(s) de más de '
            f'{settings.ACTIVIDAD_DIAS_CONSERVAR} días. Notificaciones leídas borradas: '
            f'{notificaciones} de más de {settings.NOTIFICACIONES_DIAS_CONSERVAR} días. '
            f'Sesiones de la app vencidas borradas: {tokens}. Clientes con su mes nuevo: {renovados} '
            f'(sin saldo para seguir: {sin_saldo}).'
        ))
