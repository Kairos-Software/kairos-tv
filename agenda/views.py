"""
La Agenda en el panel: la lista de lo que viene (por día), cargar, editar y
eliminar un evento. Ver los eventos: permiso "ver_canales"; cargarlos y
cambiarlos: "importar_canales" (los mismos que para el contenido).
"""

from itertools import groupby

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from usuarios.decoradores import requiere_permiso
from usuarios.permisos import chequear_permiso

from . import servicios
from .forms import EventoForm
from .models import Evento


def _nombre_del_dia(dia, hoy):
    if dia == hoy:
        return 'Hoy'
    if (dia - hoy).days == 1:
        return 'Mañana'
    if (hoy - dia).days == 1:
        return 'Ayer'
    nombres = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    return f'{nombres[dia.weekday()]} {dia.day}/{dia.month}'


@requiere_permiso('ver_canales')
def lista(request):
    pasados = request.GET.get('ver') == 'pasados'
    ahora = timezone.now()
    hoy = timezone.localdate()
    eventos = list(servicios.para_el_panel(ahora, pasados=pasados)[:300])
    dias = [
        (_nombre_del_dia(dia, hoy), list(del_dia))
        for dia, del_dia in groupby(eventos, key=lambda e: timezone.localtime(e.empieza).date())
    ]
    return render(request, 'agenda/lista.html', {
        'dias': dias,
        'pasados': pasados,
        'ahora': ahora,
        'sin_canal': sum(1 for e in eventos if e.canal_id is None),
        'puede_editar': chequear_permiso(request.user, 'importar_canales'),
    })


@requiere_permiso('importar_canales')
def editar(request, pk=None):
    evento = get_object_or_404(Evento, pk=pk) if pk else None
    pedido = request.GET.get('copiar', '')
    copiar = None if evento or not pedido.isdigit() else Evento.objects.filter(pk=pedido).first()
    inicial = {}
    if copiar:
        # "Cargar otro igual": mismo canal y tipo, otra fecha (ej: la fecha siguiente del torneo)
        inicial = {'detalle': copiar.detalle, 'tipo': copiar.tipo, 'canal': copiar.canal_id}
    form = EventoForm(request.POST or None, instance=evento, initial=inicial)
    if request.method == 'POST' and form.is_valid():
        nuevo = form.save(commit=False)
        nuevo.marcar_autor(request.user)
        nuevo.save()
        aviso = '' if nuevo.canal_id else ' Falta elegir el canal: hasta entonces no sale en la app.'
        messages.success(request, f'"{nuevo.titulo}" guardado en la agenda.{aviso}')
        if 'y_otro' in request.POST:
            return redirect(f"{reverse('agenda:nuevo')}?copiar={nuevo.pk}")
        return redirect('agenda:lista')
    return render(request, 'agenda/formulario.html', {
        'form': form,
        'evento': evento,
        'titulo': f'Editar "{evento.titulo}"' if evento else 'Nuevo evento',
    })


@require_POST
@requiere_permiso('importar_canales')
def eliminar(request, pk):
    evento = get_object_or_404(Evento, pk=pk)
    evento.eliminar(request.user)
    messages.success(request, f'"{evento.titulo}" se sacó de la agenda.')
    return redirect('agenda:lista')
