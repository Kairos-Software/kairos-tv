"""
Vuelve a probar todas las fuentes y actualiza su estado.

    python manage.py verificar_fuentes

Lo mismo que el botón "Volver a verificar todas" del panel (de a tandas de 50,
hasta terminar). También averigua el formato real de cada una. En producción
lo corre el cron solo, cada 6 horas (ver despliegue/README.md).

Además, de madrugada (servicios.es_hora_de_medir), MIDE a fondo una tanda
de fuentes de los canales que tienen más de una (resolución y velocidad con
que llega cada una): así la app arranca por la mejor de cada canal. No hay
que hacer nada a mano: tanda a tanda quedan todas medidas y se renuevan solas.
--medir lo hace a cualquier hora.

Mientras corre, el panel lo muestra arriba ("Verificación automática...") y
los trabajos pesados del panel (probar o cargar una lista) esperan a que
termine (ver core/trabajos.py).
"""

from datetime import timedelta
from functools import partial

from django.core.management.base import BaseCommand

from canales.servicios import SEGUNDOS_PARA_MEDIR, es_hora_de_medir, medir_fuentes, verificar_fuentes_guardadas
from canales.verificacion import verificar_varias
from core import trabajos

CLAVE = 'verificacion_programada'
# Una tanda sin límite de tiempo puede tardar varios minutos (lo da por cortado si no avisa en esto)
MARGEN = timedelta(minutes=15)


class Command(BaseCommand):
    help = 'Vuelve a probar todas las fuentes de los canales y actualiza su estado.'

    def add_arguments(self, parser):
        parser.add_argument('--medir', action='store_true',
                            help='Medir una tanda de fuentes aunque no sea de madrugada.')

    def handle(self, *args, **options):
        try:
            self.stdout.write('Verificando las fuentes (puede tardar)...')
            trabajos.anotar(CLAVE, 'Verificación automática de las fuentes', margen=MARGEN)
            resultado = verificar_fuentes_guardadas(verificar_varias, al_avanzar=self._avance)
            self.stdout.write(self.style.SUCCESS(f'Listo: {resultado}'))
            if options['medir'] or es_hora_de_medir():
                self.stdout.write('Midiendo una tanda de fuentes de los canales con varias...')
                trabajos.anotar(CLAVE, 'Midiendo las fuentes (cuál es la mejor de cada canal)',
                                margen=timedelta(seconds=SEGUNDOS_PARA_MEDIR + 5 * 60))
                medidas = medir_fuentes(partial(verificar_varias, a_fondo=True))
                self.stdout.write(self.style.SUCCESS(f'Medidas: {medidas}'))
        finally:
            trabajos.terminar(CLAVE)

    @staticmethod
    def _avance(avance):
        trabajos.avance(CLAVE, avance['porcentaje'],
                        f'{avance["verificadas"]:,} de {avance["total"]:,} fuentes'.replace(',', '.'), margen=MARGEN)
