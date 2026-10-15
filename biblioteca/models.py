"""
Lo que cada CUENTA guarda en la app: favoritos, "Continuar viendo" y los
últimos canales vistos. Antes quedaba en cada aparato: si en una TV entraba
otro cliente, veía lo del anterior; y lo que se miraba en la TV no aparecía
en el celular.

De quién es (ver servicios.cuenta_de):
  - un cliente que entra con SU código: del cliente (lo comparten la TV y el
    celular de la casa);
  - una pantalla con código propio: de esa pantalla (es otra persona: su
    titular);
  - un usuario del panel que usa la app: de ese usuario.
Cada fila tiene uno solo de los tres.

Lo que es del APARATO (qué calidad de YouTube aguanta, qué señales fallan
ahí, el modo de video, volver al último canal al abrir) sigue en el aparato.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from canales.models import Canal
from reventa.models import Cliente, Pantalla

UNO_SOLO = (Q(cliente__isnull=False, pantalla__isnull=True, usuario__isnull=True)
            | Q(cliente__isnull=True, pantalla__isnull=False, usuario__isnull=True)
            | Q(cliente__isnull=True, pantalla__isnull=True, usuario__isnull=False))


def unico_por_cuenta(campo, nombre):
    """Que `campo` no se repita dentro de una misma cuenta (una regla por cada clase de cuenta)."""
    return [models.UniqueConstraint(fields=[dueno, campo], condition=Q(**{f'{dueno}__isnull': False}),
                                    name=f'{nombre}_unico_por_{dueno}')
            for dueno in ('cliente', 'pantalla', 'usuario')]


class DeLaCuenta(models.Model):
    """De quién es: un cliente, una pantalla con código propio o un usuario del panel (uno solo)."""
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, null=True, blank=True, related_name='+')
    pantalla = models.ForeignKey(Pantalla, on_delete=models.CASCADE, null=True, blank=True, related_name='+')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
                                related_name='+')

    class Meta:
        abstract = True


class Favorito(DeLaCuenta):
    """Mi lista: un canal o película ("c:<id>") o una serie ("s:<nombre>"), como los guarda la app."""
    clave = models.CharField(max_length=120)
    agregado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'favorito'
        verbose_name_plural = 'favoritos'
        ordering = ['agregado']
        constraints = [
            models.CheckConstraint(condition=UNO_SOLO, name='favorito_de_una_cuenta'),
            *unico_por_cuenta('clave', 'favorito'),
        ]

    def __str__(self):
        return self.clave


class Progreso(DeLaCuenta):
    """Por dónde va una película o capítulo ("Continuar viendo"), y en qué aparato se miró."""
    canal = models.ForeignKey(Canal, on_delete=models.CASCADE, related_name='+')
    posicion = models.PositiveIntegerField('posición (segundos)')
    duracion = models.PositiveIntegerField('duración (segundos)')
    cuando = models.DateTimeField()
    aparato = models.CharField(max_length=100, blank=True, help_text='Dónde se miró. Ej: "Smart TV Philips".')

    class Meta:
        verbose_name = 'progreso'
        verbose_name_plural = 'progresos'
        ordering = ['-cuando']
        constraints = [
            models.CheckConstraint(condition=UNO_SOLO, name='progreso_de_una_cuenta'),
            *unico_por_cuenta('canal', 'progreso'),
        ]

    def __str__(self):
        return f'{self.canal} · {self.posicion} de {self.duracion} s'


class Visto(DeLaCuenta):
    """Un canal en vivo que se miró hace poco ("Últimos canales vistos"), y en qué aparato."""
    canal = models.ForeignKey(Canal, on_delete=models.CASCADE, related_name='+')
    cuando = models.DateTimeField()
    aparato = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = 'canal visto'
        verbose_name_plural = 'canales vistos'
        ordering = ['-cuando']
        constraints = [
            models.CheckConstraint(condition=UNO_SOLO, name='visto_de_una_cuenta'),
            *unico_por_cuenta('canal', 'visto'),
        ]

    def __str__(self):
        return f'{self.canal} · {self.cuando:%d/%m %H:%M}'
