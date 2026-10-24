"""
Lógica central de permisos. Cualquier parte del sistema que necesite saber
si un usuario puede hacer algo, pregunta acá.

Cómo se decide si un usuario tiene un permiso:
  1. Superusuario            -> siempre sí.
  2. Usuario inactivo        -> nunca.
  2b. Revendedor             -> nunca, tenga el rol o los permisos que tenga: ve
                                SU panel de reventa (sus clientes, créditos,
                                estadísticas) por su perfil de Revendedor, y nada
                                de otros. Un rol con "administrar_reventa" le
                                mostraba todos los clientes y revendedores.
  3. Permiso individual      -> si existe, manda (sí o no).
  4. Rol                     -> si no hay permiso individual, manda el rol.
  5. Sin rol ni individual   -> no.

Reglas para OTORGAR permisos (a un usuario o a un rol):
  - Nadie puede dar un permiso que no tiene él mismo.
  - Los PERMISOS_RESTRINGIDOS solo los puede dar un superusuario.

Uso:
    from usuarios.permisos import chequear_permiso
    if chequear_permiso(request.user, 'crear_usuarios'): ...
"""

from .catalogo_permisos import (
    CODIGOS_PERMISOS, MODULOS_PERMISOS, PERMISOS_RESTRINGIDOS,
)

# Atributo donde se guarda el resultado en el objeto usuario, para no
# consultar la base más de una vez por request.
_CACHE = '_permisos_efectivos_cache'


def permisos_efectivos(usuario):
    """Set con todos los códigos que el usuario tiene concedidos ahora."""
    if usuario is None or not usuario.is_authenticated or not usuario.is_active:
        return frozenset()
    if usuario.is_superuser:
        return CODIGOS_PERMISOS

    cache = getattr(usuario, _CACHE, None)
    if cache is not None:
        return cache

    if es_revendedor(usuario):
        setattr(usuario, _CACHE, frozenset())
        return frozenset()

    resultado = set(usuario.rol.get_permisos()) if usuario.rol_id else set()
    for permiso, concedido in usuario.permisos_individuales.values_list('permiso', 'concedido'):
        if concedido:
            resultado.add(permiso)
        else:
            resultado.discard(permiso)

    resultado = frozenset(resultado & CODIGOS_PERMISOS)
    setattr(usuario, _CACHE, resultado)
    return resultado


def es_revendedor(usuario):
    """True si `usuario` tiene un perfil de revendedor (no borrado)."""
    # Import acá: reventa usa este módulo (sería circular arriba)
    from reventa.models import Revendedor
    return Revendedor.objects.filter(usuario_id=usuario.pk).exists()


def limpiar_cache_permisos(usuario):
    """Llamar después de cambiar el rol o los permisos individuales de `usuario`."""
    if hasattr(usuario, _CACHE):
        delattr(usuario, _CACHE)


def chequear_permiso(usuario, codigo):
    """True si el usuario tiene el permiso `codigo`."""
    return codigo in permisos_efectivos(usuario)


def tiene_algun_permiso(usuario, *codigos):
    """True si tiene al menos uno de los permisos indicados."""
    return bool(permisos_efectivos(usuario) & set(codigos))


def filtrar_otorgables(codigos, solicitante):
    """
    De los `codigos` que `solicitante` quiere otorgar, devuelve solo los
    que realmente puede otorgar (ver reglas arriba).
    """
    codigos = set(codigos) & CODIGOS_PERMISOS
    if solicitante is None:
        return set()
    if solicitante.is_superuser:
        return codigos
    propios = permisos_efectivos(solicitante)
    return {c for c in codigos if c in propios and c not in PERMISOS_RESTRINGIDOS}


def puede_otorgar_rol(rol, solicitante):
    """True si `solicitante` puede asignar `rol` a alguien (tiene todos sus permisos)."""
    permisos_rol = rol.get_permisos()
    return filtrar_otorgables(permisos_rol, solicitante) == permisos_rol


def estado_permisos(usuario, solicitante):
    """
    Estado de cada permiso de `usuario`, agrupado por módulo, para la
    pantalla de permisos individuales.

    [
      ('Usuarios', [
        {
          'codigo': 'ver_usuarios', 'descripcion': '...',
          'concedido': True,
          'origen': 'superusuario' | 'rol' | 'individual_si' | 'individual_no' | 'ninguno',
          'en_rol': True,
          'editable': True,
          'motivo_bloqueo': None | 'restringido' | 'sin_permiso_propio',
        }, ...
      ]), ...
    ]
    """
    permisos_rol = usuario.rol.get_permisos() if usuario.rol_id else set()
    individuales = dict(usuario.permisos_individuales.values_list('permiso', 'concedido'))
    otorgables = filtrar_otorgables(CODIGOS_PERMISOS, solicitante)

    resultado = []
    for modulo, permisos in MODULOS_PERMISOS:
        filas = []
        for codigo, descripcion in permisos:
            en_rol = codigo in permisos_rol
            if usuario.is_superuser:
                concedido, origen = True, 'superusuario'
            elif codigo in individuales:
                concedido = individuales[codigo]
                origen = 'individual_si' if concedido else 'individual_no'
            elif en_rol:
                concedido, origen = True, 'rol'
            else:
                concedido, origen = False, 'ninguno'

            if usuario.is_superuser:
                editable, motivo = False, None
            elif codigo in otorgables:
                editable, motivo = True, None
            elif codigo in PERMISOS_RESTRINGIDOS:
                editable, motivo = False, 'restringido'
            else:
                editable, motivo = False, 'sin_permiso_propio'

            filas.append({
                'codigo': codigo,
                'descripcion': descripcion,
                'concedido': concedido,
                'origen': origen,
                'en_rol': en_rol,
                'editable': editable,
                'motivo_bloqueo': motivo,
            })
        resultado.append((modulo, filas))
    return resultado


def grilla_permisos_rol(permisos_rol, solicitante):
    """
    Permisos de un rol agrupados por módulo, para la pantalla de roles.
    `permisos_rol` = set de códigos que el rol tiene (o que se marcaron).

    [('Usuarios', [{'codigo', 'descripcion', 'concedido', 'editable', 'motivo_bloqueo'}, ...]), ...]
    """
    permisos_rol = set(permisos_rol)
    otorgables = filtrar_otorgables(CODIGOS_PERMISOS, solicitante)
    resultado = []
    for modulo, permisos in MODULOS_PERMISOS:
        filas = []
        for codigo, descripcion in permisos:
            if codigo in otorgables:
                editable, motivo = True, None
            elif codigo in PERMISOS_RESTRINGIDOS:
                editable, motivo = False, 'restringido'
            else:
                editable, motivo = False, 'sin_permiso_propio'
            filas.append({
                'codigo': codigo,
                'descripcion': descripcion,
                'concedido': codigo in permisos_rol,
                'editable': editable,
                'motivo_bloqueo': motivo,
            })
        resultado.append((modulo, filas))
    return resultado
