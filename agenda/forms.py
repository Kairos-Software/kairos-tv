from django import forms

from herramientas.formularios import EstiloBootstrapMixin

from . import servicios
from .models import Evento


class CampoFechaHora(forms.DateTimeInput):
    """Fecha y hora con el selector del navegador (<input type="datetime-local">)."""

    input_type = 'datetime-local'

    def __init__(self, attrs=None):
        # El input datetime-local necesita el formato ISO (AAAA-MM-DDTHH:MM)
        super().__init__(attrs=attrs, format='%Y-%m-%dT%H:%M')


class CanalDelEvento(forms.ModelChoiceField):
    def label_from_instance(self, canal):
        return f'{canal.nombre} ({canal.numero})' if canal.numero else canal.nombre


class EventoForm(EstiloBootstrapMixin, forms.ModelForm):
    canal = CanalDelEvento(
        queryset=Evento._meta.get_field('canal').related_model.objects.none(), required=False,
        label='Canal', empty_label='— Falta el canal (no sale en la app) —',
        help_text='El canal en vivo donde se ve. Sin canal, el evento no aparece en la app.',
    )

    class Meta:
        model = Evento
        fields = ['titulo', 'detalle', 'tipo', 'canal', 'empieza', 'termina']
        widgets = {'empieza': CampoFechaHora(), 'termina': CampoFechaHora()}
        labels = {'empieza': 'Empieza', 'termina': 'Termina'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['canal'].queryset = servicios.canales_en_vivo()
        for campo in ('empieza', 'termina'):
            self.fields[campo].input_formats = ['%Y-%m-%dT%H:%M']

    def clean(self):
        datos = super().clean()
        empieza, termina = datos.get('empieza'), datos.get('termina')
        if empieza and termina and termina <= empieza:
            self.add_error('termina', 'Tiene que ser después de que empieza.')
        return datos
