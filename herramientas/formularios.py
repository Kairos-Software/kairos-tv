"""
Utilidades para formularios de Django, reutilizables en cualquier app.

    from herramientas.formularios import EstiloBootstrapMixin, CampoFecha

    class ClienteForm(EstiloBootstrapMixin, forms.ModelForm):
        ...
"""

from django import forms


class CampoFecha(forms.DateInput):
    """Selector de fecha nativo del navegador (<input type="date">)."""

    input_type = 'date'

    def __init__(self, attrs=None):
        # El input type=date necesita el formato ISO (AAAA-MM-DD)
        super().__init__(attrs=attrs, format='%Y-%m-%d')


class EstiloBootstrapMixin:
    """
    Agrega a cada campo la clase de Bootstrap que le corresponde
    (form-control, form-select, form-check-input) y marca con is-invalid
    los campos con error. Así los templates no tienen que hacerlo a mano.
    """

    TEXTO_OPCION_VACIA = 'Elegir…'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            widget = campo.widget

            # La opción vacía de los desplegables viene en inglés
            # ("Select an option"): se reemplaza por un texto propio.
            if isinstance(campo, forms.ModelChoiceField):
                if campo.empty_label is not None:
                    campo.empty_label = self.TEXTO_OPCION_VACIA
            elif isinstance(campo, forms.ChoiceField):
                opciones = list(campo.choices)
                if opciones and opciones[0][0] == '':
                    campo.choices = [('', self.TEXTO_OPCION_VACIA)] + opciones[1:]

            if isinstance(widget, (forms.CheckboxInput, forms.RadioSelect, forms.CheckboxSelectMultiple)):
                clase = 'form-check-input'
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                clase = 'form-select'
            else:
                clase = 'form-control'
            widget.attrs['class'] = ' '.join(c for c in (widget.attrs.get('class', ''), clase) if c)

    def full_clean(self):
        # Se marca DESPUÉS de validar, no en __init__: si no, se validaba antes
        # de que el formulario hijo terminara de armar sus campos (por ejemplo,
        # las opciones de un desplegable) y una opción buena salía "no válida".
        super().full_clean()
        for nombre in self.errors:
            if nombre in self.fields:
                widget = self.fields[nombre].widget
                clases = widget.attrs.get('class', '').split()
                if 'is-invalid' not in clases:
                    widget.attrs['class'] = ' '.join([*clases, 'is-invalid'])
