from django import forms
from django.contrib.auth.password_validation import validate_password

from herramientas.formularios import EstiloBootstrapMixin
from usuarios.models import Usuario

from .models import Cliente, Paquete, Pantalla, Revendedor


class RevendedorNuevoForm(EstiloBootstrapMixin, forms.Form):
    """Crea el usuario del panel y su perfil de revendedor de una sola vez."""

    username = forms.CharField(label='Usuario (para entrar al panel)', max_length=150)
    first_name = forms.CharField(label='Nombre', max_length=150)
    last_name = forms.CharField(label='Apellido', max_length=150, required=False)
    telefono = forms.CharField(label='Teléfono', max_length=30, required=False)
    password = forms.CharField(label='Contraseña inicial', widget=forms.PasswordInput(render_value=True),
                               help_text='Se le va a pedir que la cambie al entrar por primera vez.')

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if Usuario.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('Ya existe un usuario con ese nombre.')
        return username

    def clean_password(self):
        password = self.cleaned_data['password']
        validate_password(password)
        return password


class PrecioForm(EstiloBootstrapMixin, forms.ModelForm):
    """El precio que el revendedor les propone a sus clientes por pantalla y por mes (lo pone él)."""

    class Meta:
        model = Revendedor
        fields = ['precio_pantalla']
        labels = {'precio_pantalla': 'Tu precio por pantalla, por mes'}


class CreditosForm(EstiloBootstrapMixin, forms.Form):
    """Regalar (cantidad > 0) o ajustar (+/−) créditos."""

    cantidad = forms.IntegerField(label='Cantidad')
    detalle = forms.CharField(label='Motivo / nota', max_length=200, required=False)


class PaqueteForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Paquete
        fields = ['nombre', 'creditos', 'precio', 'activo']

    def clean_creditos(self):
        creditos = self.cleaned_data['creditos']
        if creditos < 1:
            raise forms.ValidationError('Tiene que tener al menos 1 crédito.')
        return creditos


class ElegirPaqueteForm(EstiloBootstrapMixin, forms.Form):
    paquete = forms.ModelChoiceField(label='Paquete', queryset=Paquete.objects.filter(activo=True))


class ClienteForm(EstiloBootstrapMixin, forms.ModelForm):
    """Para el administrador aparece además el campo revendedor (al crear)."""

    class Meta:
        model = Cliente
        fields = ['revendedor', 'nombre', 'telefono', 'notas', 'suspendido']
        widgets = {'notas': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, elegir_revendedor=False, **kwargs):
        # Los campos que no van se sacan de la clase antes de armar el formulario
        # (así ni se dibujan ni se validan). Lo que se ajusta después de
        # super().__init__ (la lista de revendedores, si es obligatorio) también
        # cuenta al validar: EstiloBootstrapMixin valida recién en full_clean.
        instancia = kwargs.get('instance')
        sacar = set()
        if not elegir_revendedor:
            sacar.add('revendedor')
        if instancia is None or instancia.pk is None:
            sacar.add('suspendido')   # recién creado no tiene sentido
        self.base_fields = {nombre: campo for nombre, campo in type(self).base_fields.items() if nombre not in sacar}
        super().__init__(*args, **kwargs)
        if elegir_revendedor:
            campo = self.fields['revendedor']
            campo.queryset = Revendedor.objects.select_related('usuario')
            campo.required = False
            campo.label = 'Revendedor (opcional)'
            campo.empty_label = '— Ninguno: cliente directo de la empresa —'
            campo.help_text = ('Dejalo en «Ninguno» para tus clientes propios (familia, pruebas): sus créditos los '
                               'pone la empresa. Si un día paga a través de un revendedor, se lo pasás desde su ficha.')



class CobroForm(EstiloBootstrapMixin, forms.Form):
    """
    Lo que tiene toda carga de créditos a un cliente: cuánto se le cobró (o
    si es un regalo) y, para el administrador con un cliente de revendedor,
    si los créditos los pone la empresa en vez del revendedor.
    """

    monto_cobrado = forms.DecimalField(label='Monto cobrado', min_value=0, decimal_places=2, required=False,
                                       help_text='Vacío = el precio sugerido.')
    cortesia = forms.BooleanField(label='Es una cortesía (regalo: no se cobra)', required=False)
    de_la_empresa = forms.BooleanField(label='Los pone la empresa (no gasta créditos del revendedor)',
                                       required=False)

    def __init__(self, *args, con_empresa=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not con_empresa:
            del self.fields['de_la_empresa']

    def datos_del_cobro(self):
        datos = self.cleaned_data
        return {'monto_cobrado': None if datos['cortesia'] else datos['monto_cobrado'],
                'cortesia': datos['cortesia'], 'de_la_empresa': datos.get('de_la_empresa', False)}


class ActivarForm(CobroForm):
    """Activar: cuántas pantallas y por cuántos meses (pantallas × meses créditos)."""

    dispositivos = forms.IntegerField(label='Pantallas (aparatos a la vez)', min_value=1, max_value=20, initial=1)
    meses = forms.IntegerField(label='Meses', min_value=1, max_value=24, initial=1,
                               help_text='Se descuentan solos, uno por mes.')
    field_order = ['dispositivos', 'meses', 'monto_cobrado', 'cortesia', 'de_la_empresa']


class CargarMesesForm(CobroForm):
    """Pagar más meses de las pantallas que ya tiene."""

    meses = forms.IntegerField(label='Meses', min_value=1, max_value=24, initial=1)
    field_order = ['meses', 'monto_cobrado', 'cortesia', 'de_la_empresa']


class PantallaForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Pantalla
        fields = ['nombre', 'titular']


class PasarClienteForm(EstiloBootstrapMixin, forms.Form):
    """El administrador pasa un cliente a un revendedor (o lo deja directo)."""

    revendedor = forms.ModelChoiceField(label='Pasarlo a', queryset=Revendedor.objects.select_related('usuario'),
                                        required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['revendedor'].empty_label = '— Directo de la empresa —'
