"""
Serializers = cómo se convierte cada objeto a JSON (lo que la app RECIBE).

Son el equivalente a las plantillas de la web: deciden qué datos se
muestran y con qué nombre. Lo que la app ENVÍA no se valida acá sino con
los mismos formularios de la web (usuarios/forms.py), para no repetir
validaciones.
"""

from rest_framework import serializers

from canales.models import Canal, Fuente
from canales.verificacion import USER_AGENT_REPRODUCTOR, url_xtream_para_reproductor
from notificaciones.models import Notificacion
from usuarios.catalogo_permisos import MODULOS_PERMISOS
from usuarios.forms import CAMPOS_PERFIL, CAMPOS_USUARIO, SECCIONES_PERFIL_SOLO_LECTURA
from usuarios.models import Rol, Usuario
from usuarios.permisos import chequear_permiso, permisos_efectivos


class RolResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rol
        fields = ['id', 'nombre']


class _UsuarioBaseSerializer(serializers.ModelSerializer):
    nombre_completo = serializers.CharField(source='get_full_name')
    rol = RolResumenSerializer()
    activo = serializers.BooleanField(source='is_active')
    tipo_documento_texto = serializers.CharField(source='get_tipo_documento_display')
    genero_texto = serializers.CharField(source='get_genero_display')


class UsuarioListaSerializer(_UsuarioBaseSerializer):
    """Lo justo para una fila de la lista."""

    class Meta:
        model = Usuario
        fields = ['id', 'username', 'nombre_completo', 'iniciales', 'email', 'rol', 'descripcion_rol',
                  'activo', 'foto']


class UsuarioDetalleSerializer(_UsuarioBaseSerializer):
    """Todos los datos, para quien gestiona usuarios. `acciones`: qué puede hacer con él quien pregunta."""
    creado_por = serializers.StringRelatedField()
    acciones = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = ['id', 'nombre_completo', 'iniciales', 'descripcion_rol', 'activo', 'debe_cambiar_password',
                  *CAMPOS_USUARIO, 'tipo_documento_texto', 'genero_texto',
                  'date_joined', 'last_login', 'creado_por', 'acciones']

    def get_acciones(self, usuario):
        solicitante = self.context['request'].user
        return {
            'editar': chequear_permiso(solicitante, 'editar_usuarios'),
            'restablecer_password': chequear_permiso(solicitante, 'restablecer_password_usuarios'),
            'eliminar': chequear_permiso(solicitante, 'eliminar_usuarios'),
        }


_CAMPOS_SOLO_LECTURA = [c for _, campos in SECCIONES_PERFIL_SOLO_LECTURA for c in campos]


class PerfilSerializer(_UsuarioBaseSerializer):
    """Los datos propios. Nunca incluye notas_internas (son solo para la administración)."""
    es_superusuario = serializers.BooleanField(source='is_superuser')
    permisos = serializers.SerializerMethodField()
    permisos_por_modulo = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = ['id', 'nombre_completo', 'iniciales', 'rol', 'descripcion_rol', 'es_superusuario',
                  'debe_cambiar_password', 'permisos', 'permisos_por_modulo',
                  *dict.fromkeys(_CAMPOS_SOLO_LECTURA + CAMPOS_PERFIL),
                  'tipo_documento_texto', 'genero_texto', 'last_login']

    def get_permisos(self, usuario):
        """Los códigos: la app los usa para decidir qué mostrar."""
        return sorted(permisos_efectivos(usuario))

    def get_permisos_por_modulo(self, usuario):
        """Lo mismo pero legible, como en "Mi perfil" de la web: solo los módulos donde tiene algo."""
        propios = permisos_efectivos(usuario)
        resultado = []
        for modulo, permisos in MODULOS_PERMISOS:
            descripciones = [descripcion for codigo, descripcion in permisos if codigo in propios]
            if descripciones:
                resultado.append({'modulo': modulo, 'permisos': descripciones})
        return resultado


class NotificacionSerializer(serializers.ModelSerializer):
    leida = serializers.BooleanField()

    class Meta:
        model = Notificacion
        fields = ['id', 'titulo', 'mensaje', 'nivel', 'url', 'creada', 'leida', 'leida_en']


class FuenteSerializer(serializers.ModelSerializer):
    """
    Una fuente, con las cabeceras con que la app tiene que pedirla: el
    User-Agent propio de la fuente o, si no tiene, el de siempre (así se puede
    cambiar desde el servidor sin publicar otra versión de la app).
    """
    url = serializers.SerializerMethodField()
    user_agent = serializers.SerializerMethodField()

    class Meta:
        model = Fuente
        fields = ['id', 'url', 'tipo', 'codec', 'user_agent', 'referer']

    def get_user_agent(self, fuente):
        return fuente.user_agent or USER_AGENT_REPRODUCTOR

    def get_url(self, fuente):
        return url_xtream_para_reproductor(fuente.url)


class CanalSerializer(serializers.ModelSerializer):
    """
    Un canal con sus fuentes activas, en orden de prioridad (la app prueba la
    primera y sigue). `destacado`: el modo reposo de la TV lo muestra más seguido.
    `logo`: si en el contexto vienen `logos` (imagenes.logos_parejos), la copia
    pareja del logo (sin borde de más: todos quedan centrados igual), o '' si
    el original está roto (la app muestra las iniciales).
    """
    fuentes = FuenteSerializer(source='fuentes_activas', many=True)
    logo = serializers.SerializerMethodField()

    class Meta:
        model = Canal
        fields = ['id', 'nombre', 'numero', 'logo', 'destacado', 'fuentes']

    def get_logo(self, canal):
        parejos = self.context.get('logos') or {}
        if canal.logo not in parejos:
            return canal.logo
        mostrar = parejos[canal.logo]
        pedido = self.context.get('request')
        return pedido.build_absolute_uri(mostrar) if mostrar and pedido else mostrar

