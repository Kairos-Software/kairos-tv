"""
Catálogo de permisos del sistema y roles iniciales.

Es el ÚNICO lugar donde se declaran los permisos. Para sumar los de un
módulo nuevo (ej: clientes):

  1. Agregar un bloque en MODULOS_PERMISOS con sus códigos.
  2. Si alguno solo debe poder otorgarlo un superusuario, sumarlo a
     PERMISOS_RESTRINGIDOS.
  3. En las vistas del módulo, chequear con `chequear_permiso` o el
     decorador `requiere_permiso`.

No hace falta migración: los permisos se guardan como texto (código).
"""

# (nombre del módulo, [(código, descripción), ...])
# El orden de acá es el orden en que se muestran en las pantallas.
MODULOS_PERMISOS = [
    ('Usuarios', [
        ('ver_usuarios', 'Ver la lista y el detalle de los usuarios'),
        ('crear_usuarios', 'Crear usuarios'),
        ('editar_usuarios', 'Editar datos de usuarios y activarlos / desactivarlos'),
        ('restablecer_password_usuarios', 'Asignar una contraseña nueva a otro usuario'),
        ('eliminar_usuarios', 'Eliminar usuarios'),
        ('gestionar_permisos', 'Dar o quitar permisos individuales a otros usuarios'),
    ]),
    ('Roles', [
        ('ver_roles', 'Ver los roles y sus permisos'),
        ('crear_roles', 'Crear roles'),
        ('editar_roles', 'Editar roles existentes'),
        ('eliminar_roles', 'Eliminar roles'),
    ]),
    ('Contenido', [
        ('ver_canales', 'Ver el contenido (canales, películas y series) y el estado de sus fuentes'),
        ('importar_canales', 'Importar listas (M3U), verificar las fuentes y editar o quitar contenido'),
        ('ver_estadisticas', 'Ver lo más visto: canales, películas y series (totales, sin datos de clientes)'),
    ]),
    ('Reventa', [
        ('administrar_reventa', 'Ver y gestionar a todos los revendedores y sus clientes; regalar y ajustar créditos'),
        ('gestionar_paquetes', 'Crear y editar los paquetes de créditos'),
        ('confirmar_compras', 'Confirmar o cancelar los pagos de compras de créditos'),
    ]),
    ('App Android', [
        ('publicar_app', 'Subir versiones nuevas de la app (la APK y la de PC) para descargar'),
    ]),
    ('Sistema', [
        ('ver_actividad', 'Ver el registro de actividad (quién hizo qué y cuándo)'),
    ]),
]

PERMISOS_CHOICES = [
    permiso for _, permisos in MODULOS_PERMISOS for permiso in permisos
]
CODIGOS_PERMISOS = frozenset(codigo for codigo, _ in PERMISOS_CHOICES)
DESCRIPCION_PERMISO = dict(PERMISOS_CHOICES)

# Permisos que solo un superusuario puede otorgar (a un usuario o a un rol),
# aunque quien lo intente los tenga concedidos.
PERMISOS_RESTRINGIDOS = frozenset({
    'ver_roles',
    'crear_roles',
    'editar_roles',
    'eliminar_roles',
    'ver_actividad',
    'ver_canales',
    'importar_canales',
    'ver_estadisticas',
    'administrar_reventa',
    'gestionar_paquetes',
    'confirmar_compras',
    'publicar_app',
})


# Roles que crea `python manage.py crear_roles_iniciales`. Solo se crean si
# no existen: si después se editan desde el sistema, el comando no los pisa.
# '*' = todos los permisos del catálogo.
ROLES_INICIALES = [
    {
        'nombre': 'Administrador',
        'descripcion': 'Acceso completo: gestiona usuarios, permisos y roles.',
        'permisos': '*',
    },
    {
        'nombre': 'Supervisor',
        'descripcion': 'Gestiona usuarios del día a día, sin eliminar ni tocar permisos.',
        'permisos': [
            'ver_usuarios',
            'crear_usuarios',
            'editar_usuarios',
            'restablecer_password_usuarios',
        ],
    },
    {
        'nombre': 'Consulta',
        'descripcion': 'Solo puede ver información, sin modificar nada.',
        'permisos': [
            'ver_usuarios',
        ],
    },
    {
        # Un revendedor no necesita permisos: ve SU panel de reventa porque
        # tiene un perfil de Revendedor (reventa.models.Revendedor).
        'nombre': 'Revendedor',
        'descripcion': 'Vende el servicio: gestiona sus clientes, sus créditos y sus compras.',
        'permisos': [],
    },
    {
        'nombre': 'Operador',
        'descripcion': 'Usuario básico: entra al sistema y gestiona solo su propio perfil.',
        'permisos': [],
    },
]
