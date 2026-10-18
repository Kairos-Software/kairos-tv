import zipfile

from django import forms
from django.core.validators import URLValidator

from herramientas.formularios import EstiloBootstrapMixin

from . import organizar, secciones
from .m3u import leer_m3u
from .models import Canal, Categoria, Contenido, Fuente, Seccion

# Una lista completa de un proveedor (en vivo + películas + series: más de
# 250 000 entradas) pesa 70-80 MB. Hasta 20 MB (octubre 2026) no entraba.
# OJO: nginx también tiene que aceptarlo (client_max_body_size en despliegue/nginx).
TAMANIO_MAXIMO = 150 * 1024 * 1024


def _texto_del_archivo(archivo):
    """El texto de la lista. Si es un .zip, el de la primera lista .m3u/.m3u8 que tenga adentro."""
    if archivo.name.lower().endswith('.zip'):
        try:
            with zipfile.ZipFile(archivo) as comprimido:
                for nombre in comprimido.namelist():
                    if nombre.lower().endswith(('.m3u', '.m3u8')):
                        with comprimido.open(nombre) as adentro:
                            return adentro.read(TAMANIO_MAXIMO * 3).decode('utf-8', errors='replace')
        except zipfile.BadZipFile:
            raise forms.ValidationError('El .zip está dañado.')
        raise forms.ValidationError('El .zip no tiene ninguna lista .m3u o .m3u8 adentro.')
    return archivo.read().decode('utf-8', errors='replace')


# ── Categorías: cada una es de una sección (En vivo, Películas o Series) ──

def _elegir_categoria_con_su_seccion(campo):
    """La lista de categorías dice de qué sección es cada una ("Infantil · Películas")."""
    campo.queryset = Categoria.objects.order_by('contenido', 'orden', 'nombre')
    campo.required = False
    nombres = dict(secciones.todas())
    campo.label_from_instance = lambda c: f'{c.nombre} · {nombres.get(c.contenido, c.contenido)}'


def _elegir_seccion(campo):
    """La sección de un canal o película: las fijas y las nuevas (Música, Radio...)."""
    nuevo = forms.ChoiceField(label='Sección', choices=secciones.todas(), required=bool(campo.required),
                              initial=campo.initial)
    # Este campo se reemplaza después de que el mixin aplicó los estilos.
    nuevo.widget.attrs['class'] = 'form-select'
    return nuevo


def _categoria_de_su_seccion(datos, canal):
    """
    La categoría que queda: la nueva que se escribió, o la elegida. Siempre de
    la sección del canal (si se eligió "Infantil" de otra sección, va a la
    "Infantil" de la suya; si no existe, se crea).
    """
    contenido = datos.get('contenido') or canal.contenido
    nueva = (datos.get('nueva_categoria') or '').strip()
    elegida = datos.get('categoria')
    if nueva:
        datos['categoria'] = organizar.categoria_por_nombre(nueva, contenido)
    elif elegida is not None and elegida.contenido != contenido:
        datos['categoria'] = organizar.categoria_por_nombre(elegida.nombre, contenido)
    else:
        return
    canal.categoria = datos['categoria']


# ── Importar directo en una categoría (listas M3U y YouTube) ──

def _opciones_de_categorias(vacia, de_las_secciones):
    """
    Las categorías para elegir al importar, agrupadas por sección. El valor es
    el NOMBRE: cada cosa importada va a la categoría con ese nombre de SU
    sección (si no existe, se crea al cargar).
    """
    grupos = []
    for contenido in de_las_secciones:
        nombres = list(Categoria.objects.filter(contenido=contenido).order_by('orden', 'nombre')
                       .values_list('nombre', flat=True))
        if nombres:
            grupos.append((secciones.nombre(contenido), [(n, n) for n in nombres]))
    return [('', vacia), *grupos]


def _categoria_de_otra_seccion(form, datos, seccion):
    """La categoría elegida tiene que ser de la sección a la que va todo (si no, se explica)."""
    elegida = datos.get('categoria_destino')
    if not elegida or (datos.get('categoria_nueva') or '').strip() or not seccion:
        return
    if not Categoria.objects.filter(contenido=seccion, nombre=elegida).exists():
        form.add_error('categoria_destino', f'"{elegida}" no es una categoría de {secciones.nombre(seccion)}: '
                                            f'elegí una de esa sección, o escribí una nueva.')


def _campo_categoria_nueva():
    return forms.CharField(label='O una categoría nueva', max_length=80, required=False,
                           help_text='Si escribís acá, se crea (o se usa la que ya se llame así).')


def _nombre_de_la_categoria(datos):
    """La categoría elegida para todo lo importado: su nombre ('' = la que diga cada entrada)."""
    return ' '.join((datos.get('categoria_nueva') or datos.get('categoria_destino') or '').split())


def _no_las_dos(form, datos):
    """Elegir de la lista Y escribir una nueva confunde (¿cuál vale?): se pide una sola."""
    if datos.get('categoria_destino') and (datos.get('categoria_nueva') or '').strip():
        form.add_error('categoria_nueva', f'Elegiste "{datos["categoria_destino"]}" en la lista y además escribiste '
                                          f'una nueva: dejá solo una de las dos.')


class EditarDesdeOrganizarForm(forms.Form):
    """La edición rápida de "Organizar contenido" (la categoría se lee aparte: views._categoria_elegida)."""
    nombre = forms.CharField(max_length=120)
    logo = forms.URLField(max_length=500, required=False)
    numero = forms.CharField(max_length=10, required=False)
    contenido = forms.ChoiceField(choices=Contenido.choices, required=False)
    activo = forms.BooleanField(required=False)
    destacado = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['contenido'].choices = secciones.todas()


class TraerDeYoutubeForm(EstiloBootstrapMixin, forms.Form):
    """Traer las películas de un canal oficial de YouTube (canales/youtube.py)."""
    url = forms.CharField(
        label='Link del canal de YouTube', max_length=300,
        help_text='Ej: https://www.youtube.com/@MovieCentralEspanol. Solo canales OFICIALES, del dueño de lo que '
                  'suben (con la tilde de verificado).',
        widget=forms.TextInput(attrs={'placeholder': 'https://www.youtube.com/@canal', 'inputmode': 'url'}),
    )
    es_serie = forms.BooleanField(
        label='Es una serie: cada video es un capítulo', required=False,
        help_text='Para canales o listas de UNA serie (Masha y el Oso, Pocoyó...). Elegís 3 cosas: la categoría '
                  '(Infantiles, Disney...), la serie (una que ya existe o una nueva) y la temporada. Los capítulos '
                  'se numeran del más viejo al más nuevo, después del último que ya tenga esa temporada.',
    )
    nombre_serie = forms.CharField(label='Serie', max_length=90, required=False,
                                   help_text='Una que ya existe en esa categoría (los capítulos se suman a ella) o '
                                             '«＋ Una serie nueva», con el nombre como se va a ver en la app.')
    temporada = forms.IntegerField(
        label='Temporada', min_value=1, max_value=99, initial=1, required=False,
        help_text='Una que ya tiene (los capítulos siguen desde el último) o una nueva. Si en YouTube cada '
                  'temporada es una lista aparte, traé cada una con su link eligiendo la misma serie. La app '
                  'muestra la serie cuando tiene la temporada 1.',
    )
    segun_titulo = forms.BooleanField(
        label='Cada video va a la temporada y al capítulo que dice su título', required=False,
        help_text='Para canales con todas las temporadas mezcladas (Casi Ángeles: «Temporada 3 Capitulo 33» va a la '
                  'temporada 3, capítulo 33). La temporada de arriba queda para los que no dicen la suya; los que no '
                  'dicen su número van al final. Sin marcar, se numeran del más viejo al más nuevo.',
    )
    seccion_destino = forms.ChoiceField(
        label='Sección', required=False,
        help_text='Películas, o una sección que creaste (Música...).',
    )
    categoria_destino = forms.ChoiceField(
        label='Categoría', required=False,
        help_text='Películas: sin elegir, cada una va según el género que dice su título (Acción, Terror...). '
                  'Una serie: elegí una de Series (por ejemplo, Series Infantiles). Una sección que creaste: sin '
                  'elegir, a una con el nombre del canal (en Música, el artista).',
    )
    categoria_nueva = _campo_categoria_nueva()
    minimo_minutos = forms.IntegerField(
        label='Solo videos de al menos (minutos)', min_value=1, max_value=600, initial=60,
        help_text='Saca avances, clips y Shorts. Películas: 60. Dibujos: 20. Música: 2.',
    )
    maximo_minutos = forms.IntegerField(
        label='Y de hasta (minutos)', min_value=1, max_value=600, required=False,
        help_text='Vacío: sin límite. Música: 6 (así no entran recopilaciones ni conciertos enteros).',
    )
    solo_espanol = forms.BooleanField(label='Descartar los que dicen estar en inglés', required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        a_demanda = [s for s in secciones.nuevas() if s.forma == Seccion.Forma.A_DEMANDA]
        self.fields['seccion_destino'].choices = [('', 'Películas'), *((s.clave, s.nombre) for s in a_demanda)]
        self.fields['categoria_destino'].choices = _opciones_de_categorias(
            'Según el género de cada título', [Contenido.PELICULA, Contenido.SERIE, *(s.clave for s in a_demanda)])

    def clean(self):
        datos = super().clean()
        _no_las_dos(self, datos)
        es_serie = datos.get('es_serie')
        if es_serie:
            try:
                datos['nombre_serie'] = organizar.nombre_de_serie_valido(datos.get('nombre_serie', ''))
            except organizar.NoSePuede as error:
                self.add_error('nombre_serie', str(error))
            else:
                # Una serie que ya existe suma capítulos en SU categoría (sin elegir, se pone sola)
                try:
                    suya = organizar.categoria_para_la_serie(datos['nombre_serie'], _nombre_de_la_categoria(datos))
                except organizar.NoSePuede as error:
                    self.add_error('categoria_destino', str(error))
                else:
                    if suya and not _nombre_de_la_categoria(datos):
                        datos['categoria_destino'] = suya
            if not _nombre_de_la_categoria(datos) and 'categoria_destino' not in self.errors:
                self.add_error('categoria_destino', 'Elegí en qué categoría de Series va (por ejemplo, Series '
                                                    'Infantiles), o escribí una nueva.')
        minimo, maximo = datos.get('minimo_minutos'), datos.get('maximo_minutos')
        if minimo and maximo and maximo < minimo:
            self.add_error('maximo_minutos', f'Tiene que ser igual o más que el mínimo ({minimo}).')
        if not es_serie and datos.get('seccion_destino'):
            _categoria_de_otra_seccion(self, datos, datos['seccion_destino'])
            return datos
        elegida = datos.get('categoria_destino')
        if elegida and not datos.get('categoria_nueva'):
            seccion = Contenido.SERIE if es_serie else Contenido.PELICULA
            if not Categoria.objects.filter(contenido=seccion, nombre=elegida).exists():
                self.add_error('categoria_destino', (
                    f'"{elegida}" es una categoría de Películas: para una serie elegí una de Series (o escribí una '
                    f'nueva).' if es_serie else
                    f'"{elegida}" es una categoría de Series: si los videos son capítulos de una serie, marcá "Es una '
                    f'serie". Si son películas, elegí una de Películas.'))
        return datos

    def categoria(self):
        return _nombre_de_la_categoria(self.cleaned_data)

    def serie(self):
        """El nombre de la serie ('' = son películas)."""
        return self.cleaned_data['nombre_serie'] if self.cleaned_data.get('es_serie') else ''

    def seccion(self):
        """La sección nueva a la que va todo ('' = Películas o Series)."""
        return '' if self.cleaned_data.get('es_serie') else self.cleaned_data.get('seccion_destino') or ''


class ImportarListaForm(EstiloBootstrapMixin, forms.Form):
    archivo = forms.FileField(
        label='Lista de canales',
        help_text='Archivo .m3u, .m3u8 o un .zip que la contenga (máximo 20 MB).',
        widget=forms.FileInput(attrs={'accept': '.m3u,.m3u8,.zip'}),
    )
    descartar_vod = forms.BooleanField(
        label='Descartar películas y series', required=False, initial=False,
        help_text='Sin marcar se importa todo. Ojo: hay listas con miles y verificarlas tarda horas.',
    )
    a_fondo = forms.BooleanField(
        label='Prueba a fondo (recomendado)', required=False, initial=True,
        help_text='Además de ver si responde: que tenga sonido, el idioma del audio, la resolución, un formato que '
                  'lean todos los aparatos, que llegue fluido y, en vivo, que no esté congelada. Baja hasta 1 MB '
                  'de cada una y tarda más.',
    )
    solo_espanol = forms.BooleanField(
        label='Solo en español', required=False, initial=True,
        help_text='Descarta lo que se sabe que es de otro idioma (por país, categoría o prefijo) y, con la prueba '
                  'a fondo, lo que tiene el audio en otro idioma (si trae español entre varios, pasa).',
    )
    descartar_adultos = forms.BooleanField(label='Descartar contenido para adultos', required=False, initial=True,
                                           help_text='XXX / +18, por el nombre o la categoría.')
    descartar_sin_logo = forms.BooleanField(label='Descartar los que no tienen logo', required=False)
    seccion_destino = forms.ChoiceField(
        label='Sección', required=False,
        help_text='Sin elegir: cada uno a la que le toca (En vivo, Películas o Series). Una sección que creaste '
                  '(Radio...): todo va ahí.',
    )
    categoria_destino = forms.ChoiceField(
        label='Poner todo en la categoría', required=False,
        help_text='Sin elegir: cada canal va a la categoría que dice la lista (group-title).',
    )
    categoria_nueva = _campo_categoria_nueva()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        nuevas = secciones.nuevas()
        self.fields['seccion_destino'].choices = [('', 'La que le toca a cada uno'),
                                                  *((s.clave, s.nombre) for s in nuevas)]
        self.fields['categoria_destino'].choices = _opciones_de_categorias(
            'La que dice la lista', [Contenido.VIVO, Contenido.PELICULA, Contenido.SERIE, *(s.clave for s in nuevas)])

    def clean_archivo(self):
        archivo = self.cleaned_data['archivo']
        if not archivo.name.lower().endswith(('.m3u', '.m3u8', '.zip')):
            raise forms.ValidationError('Tiene que ser un archivo .m3u, .m3u8 o .zip.')
        if archivo.size > TAMANIO_MAXIMO:
            raise forms.ValidationError(f'El archivo pesa más de {TAMANIO_MAXIMO // (1024 * 1024)} MB. '
                                        f'Comprimilo en un .zip (una lista baja a la décima parte).')
        texto = _texto_del_archivo(archivo)
        if not leer_m3u(texto):
            raise forms.ValidationError('No se encontró ningún canal en el archivo. ¿Es una lista M3U?')
        self.texto = texto
        return archivo

    def clean(self):
        datos = super().clean()
        _no_las_dos(self, datos)
        _categoria_de_otra_seccion(self, datos, datos.get('seccion_destino'))
        return datos

    def opciones(self):
        opciones = {campo: self.cleaned_data[campo] for campo in ('descartar_vod', 'solo_espanol', 'descartar_adultos',
                                                                  'descartar_sin_logo', 'a_fondo')}
        return {**opciones, 'categoria': _nombre_de_la_categoria(self.cleaned_data),
                'seccion': self.cleaned_data.get('seccion_destino') or ''}


class QuitarCanalesForm(forms.Form):
    """Quitar de la app los canales elegidos (o todos los del filtro)."""
    motivo = forms.CharField(max_length=200, required=False)


class CanalForm(EstiloBootstrapMixin, forms.ModelForm):
    """Editar un canal desde el panel. La categoría se elige o se crea escribiéndola."""
    nueva_categoria = forms.CharField(
        label='O una categoría nueva', max_length=80, required=False,
        help_text='Si escribís acá, se crea (o se usa la que ya se llame así) en vez de la de arriba.',
    )
    nueva_fuente = forms.CharField(
        label='Agregar una fuente', max_length=1000, required=False,
        validators=[URLValidator(schemes=['http', 'https', 'rtsp', 'rtsps'])],
        help_text='Una dirección más para este canal (.m3u8, video directo, YouTube, Twitch...). '
                  'Se prueba al guardar.',
    )
    imagen = forms.FileField(
        label='O subí la imagen desde la compu', required=False,
        help_text='JPG, PNG o WEBP (se achica sola; si tiene el fondo de cuadritos pintado, se lo saca). '
                  'Si subís una, gana sobre la dirección de arriba.',
        widget=forms.FileInput(attrs={'accept': 'image/jpeg,image/png,image/webp'}),
    )

    class Meta:
        model = Canal
        fields = ['nombre', 'logo', 'numero', 'categoria', 'contenido', 'idioma', 'pais', 'orden',
                  'activo', 'motivo_quitado', 'destacado']
        labels = {'activo': 'Se muestra en la app', 'motivo_quitado': 'Si no se muestra, por qué',
                  'destacado': '★ Destacado en la TV'}
        widgets = {'logo': forms.URLInput(attrs={'placeholder': 'https://.../logo.png'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _elegir_categoria_con_su_seccion(self.fields['categoria'])
        self.fields['contenido'] = _elegir_seccion(self.fields['contenido'])
        self.fields['pais'].widget.attrs.update({'maxlength': 2, 'style': 'text-transform:uppercase'})

    def clean_pais(self):
        return self.cleaned_data['pais'].strip().upper()

    def clean_nueva_fuente(self):
        url = self.cleaned_data['nueva_fuente'].strip()
        if url and Fuente.objects.filter(canal=self.instance, url=url).exists():
            raise forms.ValidationError('Este canal ya tiene esa dirección.')
        return url

    def clean(self):
        datos = super().clean()
        if datos.get('activo'):
            datos['motivo_quitado'] = ''
        _categoria_de_su_seccion(datos, self.instance)
        return datos


FuentesFormSet = forms.modelformset_factory(
    Fuente, fields=['prioridad', 'activa'], extra=0, can_delete=True,
    widgets={'prioridad': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'width:5rem',
                                                   'min': 0, 'aria-label': 'Orden'}),
             'activa': forms.CheckboxInput(attrs={'class': 'form-check-input', 'aria-label': 'Activa'})},
)


class ProbarLinkForm(EstiloBootstrapMixin, forms.Form):
    """Una dirección para ver si anda (y, opcionalmente, cómo pedirla)."""
    url = forms.CharField(
        label='Dirección', max_length=1000,
        validators=[URLValidator(schemes=['http', 'https', 'rtsp', 'rtsps'])],
        widget=forms.URLInput(attrs={'placeholder': 'https://.../playlist.m3u8, http://servidor:8080/..., youtube.com/...',
                                     'autofocus': True}),
    )
    user_agent = forms.CharField(label='User-Agent (opcional)', max_length=300, required=False,
                                 help_text='Solo si el canal lo exige. Si no, se prueba como la app y como VLC.')
    referer = forms.CharField(label='Referer (opcional)', max_length=500, required=False)


class CanalNuevoForm(EstiloBootstrapMixin, forms.ModelForm):
    """Los datos del canal que se crea a mano con una dirección ya probada."""
    nueva_categoria = forms.CharField(label='O una categoría nueva', max_length=80, required=False)

    class Meta:
        model = Canal
        fields = ['nombre', 'logo', 'numero', 'categoria', 'contenido', 'idioma', 'pais']
        widgets = {'logo': forms.URLInput(attrs={'placeholder': 'https://.../logo.png'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _elegir_categoria_con_su_seccion(self.fields['categoria'])
        self.fields['contenido'] = _elegir_seccion(self.fields['contenido'])
        self.fields['pais'].widget.attrs.update({'maxlength': 2, 'style': 'text-transform:uppercase'})

    def clean_pais(self):
        return self.cleaned_data['pais'].strip().upper()

    def clean(self):
        datos = super().clean()
        _categoria_de_su_seccion(datos, self.instance)
        return datos
