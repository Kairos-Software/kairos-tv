from datetime import timedelta

from django.db import models

from herramientas.modelos import ModeloBase

# Cuánto dura un evento si no se dice cuándo termina (un partido, con la previa)
DURACION_SIN_FIN = timedelta(hours=2)


class Evento(ModeloBase):
    """
    Algo que va a pasar en un canal en vivo a una hora: un partido, un
    programa especial, una entrega de premios. La app lo muestra en "Agenda"
    y, si la persona toca "Avisarme", le avisa cuando empieza.

    `canal` es OBLIGATORIO para que salga en la app (es donde se ve). Puede
    quedar vacío ("Falta el canal") para lo que se carga antes de saber el
    canal, o si el canal se borra: así no se pierde, pero no se muestra.
    """

    class Tipo(models.TextChoices):
        FUTBOL = 'futbol', 'Fútbol'
        DEPORTE = 'deporte', 'Otro deporte'
        ESPECIAL = 'especial', 'Programa especial'
        NOTICIAS = 'noticias', 'Noticias'
        OTRO = 'otro', 'Otro'

    titulo = models.CharField('título', max_length=120, help_text='Ej: Boca vs River.')
    detalle = models.CharField(
        max_length=160, blank=True, help_text='Opcional. Ej: Liga Profesional · Fecha 14.',
    )
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.FUTBOL)
    canal = models.ForeignKey(
        'canales.Canal', on_delete=models.SET_NULL, null=True, blank=True, related_name='eventos',
        help_text='El canal en vivo donde se ve. Sin canal, no aparece en la app.',
    )
    empieza = models.DateTimeField()
    termina = models.DateTimeField(
        null=True, blank=True, help_text='Opcional. Si no se pone, se toma que dura 2 horas.',
    )

    class Meta:
        verbose_name = 'evento de la agenda'
        verbose_name_plural = 'agenda'
        ordering = ['empieza', 'titulo']

    def __str__(self):
        return self.titulo

    @property
    def fin(self):
        """Cuándo termina (si no se dijo, 2 horas después de empezar)."""
        return self.termina or self.empieza + DURACION_SIN_FIN
