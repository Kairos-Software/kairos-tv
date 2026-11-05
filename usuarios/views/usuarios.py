"""
Pantallas de gestión de usuarios: lista, alta, detalle, edición,
activar/desactivar, restablecer contraseña y eliminar.

Las vistas solo reciben el pedido, llaman a consultas/servicios y muestran
el resultado. Las reglas del negocio están en servicios.py.
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .. import consultas, servicios
from ..decoradores import requiere_permiso
from ..forms import RestablecerPasswordForm, UsuarioCrearForm, UsuarioForm, datos_usuario
from ..permisos import chequear_permiso, estado_permisos

USUARIOS_POR_PAGINA = 20


def _destino_despues_de_guardar(request, usuario, mensaje):
    """
    Si el usuario quedó con permisos personalizados (sin rol) y quien guarda
    puede gestionar permisos, lo lleva directo a elegírselos. Si no, al detalle.
    """
    if usuario.tiene_permisos_personalizados and chequear_permiso(request.user, 'gestionar_permisos'):
        messages.success(request, f'{mensaje} Ahora elegí sus permisos.')
        return redirect('usuarios:permisos', pk=usuario.pk)
    messages.success(request, mensaje)
    return redirect('usuarios:detalle', pk=usuario.pk)


def _obtener_usuario(request, pk):
    # Siempre desde usuarios_gestionables: así nadie puede tocar a un
    # superusuario (ni a sí mismo) armando la URL a mano.
    return get_object_or_404(consultas.usuarios_gestionables(request.user), pk=pk)


@requiere_permiso('ver_usuarios')
def lista(request):
    filtros = {
        'texto': request.GET.get('q', '').strip(),
        'rol': request.GET.get('rol', ''),
        'estado': request.GET.get('estado', ''),
    }
    usuarios = consultas.buscar_usuarios(request.user, **filtros)
    pagina = Paginator(usuarios, USUARIOS_POR_PAGINA).get_page(request.GET.get('pagina'))

    # Para que la paginación conserve los filtros
    parametros = request.GET.copy()
    parametros.pop('pagina', None)

    return render(request, 'usuarios/lista.html', {
        'pagina': pagina,
        'filtros': filtros,
        'hay_filtros': any(filtros.values()),
        'roles': consultas.roles_para_filtro(),
        'parametros': parametros.urlencode(),
    })


@requiere_permiso('crear_usuarios')
def crear(request):
    form = UsuarioCrearForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        try:
            usuario = servicios.crear_usuario(form, request.user)
        except servicios.OperacionNoPermitida as error:
            form.add_error('rol', str(error))
        else:
            return _destino_despues_de_guardar(request, usuario, f'Usuario {usuario.username} creado.')

    return render(request, 'usuarios/formulario.html', {'form': form, 'creando': True})


@requiere_permiso('ver_usuarios')
def detalle(request, pk):
    usuario = _obtener_usuario(request, pk)
    return render(request, 'usuarios/detalle.html', {
        'usuario': usuario,
        'secciones': datos_usuario(usuario),
        'puede_editar': chequear_permiso(request.user, 'editar_usuarios'),
        'puede_restablecer': chequear_permiso(request.user, 'restablecer_password_usuarios'),
        'puede_eliminar': chequear_permiso(request.user, 'eliminar_usuarios'),
        'puede_gestionar_permisos': chequear_permiso(request.user, 'gestionar_permisos'),
        'cantidad_excepciones': usuario.permisos_individuales.count(),
    })


@requiere_permiso('editar_usuarios')
def editar(request, pk):
    usuario = _obtener_usuario(request, pk)
    form = UsuarioForm(request.POST or None, request.FILES or None, instance=usuario)
    if request.method == 'POST' and form.is_valid():
        rol_anterior_id = form.initial.get('rol')
        try:
            servicios.actualizar_usuario(form, request.user)
        except servicios.OperacionNoPermitida as error:
            form.add_error('rol', str(error))
        else:
            if rol_anterior_id and usuario.rol_id is None:
                # Se le quitó el rol: pasa a permisos personalizados
                return _destino_despues_de_guardar(request, usuario, 'Cambios guardados.')
            messages.success(request, 'Cambios guardados.')
            return redirect('usuarios:detalle', pk=usuario.pk)

    return render(request, 'usuarios/formulario.html', {'form': form, 'usuario': usuario})


@require_POST
@requiere_permiso('editar_usuarios')
def cambiar_estado(request, pk):
    usuario = _obtener_usuario(request, pk)
    activar = not usuario.is_active
    servicios.cambiar_estado(usuario, activar, request.user)
    if activar:
        messages.success(request, f'{usuario.get_full_name()} fue activado y ya puede ingresar.')
    else:
        messages.success(request, f'{usuario.get_full_name()} fue desactivado y ya no puede ingresar.')
    return redirect('usuarios:detalle', pk=usuario.pk)


@requiere_permiso('restablecer_password_usuarios')
def restablecer_password(request, pk):
    usuario = _obtener_usuario(request, pk)
    form = RestablecerPasswordForm(usuario, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        servicios.restablecer_password(
            usuario, form.cleaned_data['password1'], form.cleaned_data['obligar_cambio'], request.user,
        )
        messages.success(request, f'Se asignó una contraseña nueva a {usuario.get_full_name()}.')
        return redirect('usuarios:detalle', pk=usuario.pk)

    return render(request, 'usuarios/restablecer_password.html', {'form': form, 'usuario': usuario})


@requiere_permiso('eliminar_usuarios')
def eliminar(request, pk):
    usuario = _obtener_usuario(request, pk)
    # Un revendedor tiene clientes y una libreta de créditos: se elimina por su propio camino
    from reventa.models import Revendedor
    revendedor = Revendedor.objects.filter(usuario=usuario).first()
    if revendedor is not None:
        if chequear_permiso(request.user, 'administrar_reventa'):
            messages.info(request, f'{usuario.get_full_name() or usuario} es revendedor: al eliminarlo se decide qué '
                                   f'pasa con sus clientes.')
            return redirect('reventa:revendedor_eliminar', pk=revendedor.pk)
        messages.error(request, 'Es revendedor: lo puede eliminar quien administra la reventa.')
        return redirect('usuarios:detalle', pk=usuario.pk)
    if request.method == 'POST':
        nombre = usuario.get_full_name()
        try:
            servicios.eliminar_usuario(usuario, request.user)
        except servicios.OperacionNoPermitida as error:
            messages.error(request, str(error))
            return redirect('usuarios:detalle', pk=usuario.pk)
        messages.success(request, f'Usuario {nombre} eliminado.')
        return redirect('usuarios:lista')

    return render(request, 'usuarios/eliminar.html', {'usuario': usuario})


@requiere_permiso('gestionar_permisos')
def permisos(request, pk):
    """Permisos individuales: excepciones al rol para este usuario."""
    usuario = _obtener_usuario(request, pk)

    if request.method == 'POST':
        if request.POST.get('accion') == 'volver_al_rol':
            servicios.quitar_permisos_individuales(usuario, request.user)
            messages.success(request, f'{usuario.get_full_name()} volvió a tener solo los permisos de su rol.')
        else:
            servicios.guardar_permisos_individuales(usuario, request.POST.getlist('permisos'), request.user)
            messages.success(request, f'Permisos de {usuario.get_full_name()} guardados.')
        return redirect('usuarios:permisos', pk=usuario.pk)

    grilla = estado_permisos(usuario, request.user)
    return render(request, 'usuarios/permisos.html', {
        'usuario': usuario,
        'grilla': grilla,
        'hay_editables': any(f['editable'] for _, filas in grilla for f in filas),
        'hay_excepciones': usuario.permisos_individuales.exists(),
    })
