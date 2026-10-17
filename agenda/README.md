# agenda/

La **Agenda**: partidos y programas especiales que se cargan a mano en el panel,
cada uno con el **canal en vivo** donde se ve. En la app aparecen en Inicio (celular
y TV) con el botón **Avisarme**.

## En el panel

Menú **Kairos TV → Agenda** (`/agenda/`):

- **Lo que viene**, agrupado por día ("Hoy", "Mañana", "Sábado 18/10"), con "En vivo"
  en lo que se está dando. **Ya pasó** muestra lo terminado.
- **Nuevo evento**: título, detalle (opcional, ej: "Liga Profesional · Fecha 14"), tipo
  (Fútbol, Otro deporte, Programa especial, Noticias, Otro), **canal**, cuándo empieza
  y, opcional, cuándo termina (si no, dura 2 horas). El canal se busca escribiendo
  el nombre o el número.
- **Guardar y cargar otro igual** / **Otro igual**: abre uno nuevo con el mismo canal,
  tipo y detalle (para cargar todas las fechas de un torneo seguido).
- Sin canal se puede guardar ("Falta el canal"), pero **no sale en la app** hasta elegirlo.
  Pensado también para la etapa 3: los partidos que lleguen solos quedan así.
- Eliminar: baja lógica (como todo el sistema).

Permisos: verla, `ver_canales`; cargar y cambiar, `importar_canales` (los mismos que Contenido).

## En la app

`GET /api/v1/agenda/` (`api/v1/agenda.py`): lo que tiene canal, no terminó y empieza
en los próximos 14 días (`servicios.para_la_app`). La app muestra cada evento solo si
su canal se ve en ese aparato. Ver `app_movil/lib/movil/agenda.dart`.

**Avisarme** lo guarda cada aparato (no el servidor):
- En el **celular**, un aviso de Android 5 minutos antes, aunque la app esté cerrada.
  Tocarlo abre el canal.
- En la **TV**, un cartel "Empieza ..." con "Verlo", si la app está abierta.

## Archivos

| Archivo | Qué es |
|---|---|
| `models.py` | `Evento` (título, detalle, tipo, canal, empieza, termina). |
| `servicios.py` | Qué va a la app (`para_la_app`), qué ve el panel (`para_el_panel`), los canales que se pueden elegir (`canales_en_vivo`: los en vivo y las radios) y el JSON de cada evento. |
| `forms.py` | El formulario (fecha y hora con el selector del navegador). |
| `views.py`, `urls.py` | Lista, nuevo/editar y eliminar. |
| `templates/agenda/` | `lista.html` y `formulario.html`. Estilos en `static/css/agenda.css` y el buscador de canales en `static/js/agenda.js`. |
| `tests/` | `python manage.py test agenda`. |

Instalarlo en producción: `git pull` y `python manage.py migrate` (crea la tabla, `agenda 0001`),
`collectstatic` y reiniciar kairostv. No cambia nada de lo que ya funciona.
