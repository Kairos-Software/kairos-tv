from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseServerError, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.template import loader

from . import herramientas_dev, mantenimiento, trabajos
from .forms import EstadoMantenimientoForm
from .models import EstadoMantenimiento


@login_required
def inicio(request):
    anterior = request.session.get('ingreso_anterior')
    return render(request, 'core/inicio.html', {
        'ingreso_anterior': datetime.fromisoformat(anterior) if anterior else None,
    })


# ── Modo mantenimiento (solo superusuarios) ───────────────────────

@login_required
def trabajos_en_curso(request):
    """Los trabajos pesados en curso (JSON): el aviso de arriba del panel pregunta cada 10 s."""
    return JsonResponse({'trabajos': [trabajos.como_dato(t) for t in trabajos.en_curso()]})


def _solo_superusuario(request):
    if not request.user.is_superuser:
        raise PermissionDenied


@login_required
def mantenimiento_config(request):
    _solo_superusuario(request)
    estado = EstadoMantenimiento.obtener()
    # No usar `request.POST or None`: con todo destildado el POST viene vacío
    # y el formulario quedaría sin enviar (se desactivaría sin guardar)
    form = EstadoMantenimientoForm(request.POST if request.method == 'POST' else None, instance=estado)
    if request.method == 'POST' and form.is_valid():
        estado = mantenimiento.guardar_estado(form, request.user)
        if estado.activo:
            messages.warning(request, 'Modo mantenimiento ACTIVO: los usuarios ya no pueden usar el sistema.')
        else:
            messages.success(request, 'Modo mantenimiento desactivado: el sistema vuelve a estar disponible.')
        return redirect('core:mantenimiento')
    return render(request, 'core/mantenimiento_config.html', {
        'form': form,
        'estado': estado,
        'forzado': mantenimiento.forzado_por_env(),
    })


@login_required
def mantenimiento_vista_previa(request):
    _solo_superusuario(request)
    return pantalla_mantenimiento(mantenimiento.estado_actual() | {'activo': True}, status=200)


# ── Herramientas de desarrollador (solo superusuarios) ────────────

# slug -> (función, textos que necesita del formulario)
HERRAMIENTAS = {
    'mail_prueba': (herramientas_dev.enviar_mail_prueba, ['destinatario']),
    'cerrar_sesiones': (herramientas_dev.cerrar_todas_las_sesiones, ['_sesion']),
    'limpiar_cache': (herramientas_dev.limpiar_cache, []),
    'sincronizar_roles': (herramientas_dev.sincronizar_roles, []),
    'cargar_demo': (herramientas_dev.cargar_demo, []),
    'borrar_demo': (herramientas_dev.borrar_demo, []),
    'borrar_actividad': (herramientas_dev.borrar_actividad, ['confirmacion']),
    'borrar_notificaciones': (herramientas_dev.borrar_notificaciones, ['confirmacion']),
    'borrar_contenido': (herramientas_dev.borrar_contenido, ['que', 'confirmacion', 'password']),
    'reiniciar': (herramientas_dev.reiniciar_sistema, ['confirmacion', 'password']),
}


@login_required
def herramientas(request):
    _solo_superusuario(request)

    if request.method == 'POST':
        slug = request.POST.get('herramienta', '')
        if slug not in HERRAMIENTAS:
            messages.error(request, 'Herramienta desconocida.')
            return redirect('core:herramientas')
        funcion, campos = HERRAMIENTAS[slug]
        argumentos = [
            request.session.session_key if campo == '_sesion' else request.POST.get(campo, '')
            for campo in campos
        ]
        try:
            resultado = funcion(request.user, *argumentos)
        except herramientas_dev.HerramientaError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, resultado)
        return redirect(f"{reverse('core:herramientas')}#{slug}")

    return render(request, 'core/herramientas.html', {
        'estado': herramientas_dev.estado_del_sistema(),
        'resumen_reinicio': herramientas_dev.resumen_reinicio(),
        'contenido': herramientas_dev.resumen_contenido(),
        'FRASE_BORRAR': herramientas_dev.FRASE_BORRAR,
        'FRASE_REINICIO': herramientas_dev.FRASE_REINICIO,
    })


def pantalla_mantenimiento(estado, status=503):
    """Arma la pantalla sin request ni context processors: funciona aunque la base no responda."""
    html = loader.get_template('mantenimiento.html').render({
        'estado': estado,
        'url_login': reverse('usuarios:login'),
        'NOMBRE_SISTEMA': settings.NOMBRE_SISTEMA,
        'NOMBRE_EMPRESA': settings.NOMBRE_EMPRESA,
    })
    respuesta = HttpResponse(html, status=status)
    if status == 503:
        respuesta['Retry-After'] = '300'
    return respuesta


# ── Páginas de error (se conectan en proyecto/urls.py) ────────────

def error_403(request, exception=None):
    return render(request, '403.html', status=403)


def error_404(request, exception=None):
    return render(request, '404.html', status=404)


def error_500(request):
    # Sin request ni context processors a propósito: si lo que falló es la
    # base de datos, cualquier consulta extra volvería a fallar.
    return HttpResponseServerError(loader.get_template('500.html').render())
