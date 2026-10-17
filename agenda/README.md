# agenda/

**Ya no se usa.** Era la Agenda del panel: partidos y programas especiales que se
cargaban a mano, con "Avisarme" en la app (salió en la 1.2.25 y se sacó el 17/10/2026).

Se sacó porque la agenda tiene que ser **de cada persona**: alguien del panel no puede
saber qué le interesa a cada cliente. Ahora cada uno anota lo suyo en la app con
**Recordarme** y se guarda en su aparato (`app_movil/lib/movil/recordatorios.dart`).
El servidor no participa.

## Por qué la carpeta sigue

En producción ya se había creado la tabla (`agenda 0001`). La migración
`0002_sacar_la_agenda_del_panel` la borra, y para que Django la corra la app tiene que
seguir en `INSTALLED_APPS`. Solo quedan `apps.py`, `models.py` (vacío) y `migrations/`.

Cuando producción tenga aplicada la 0002 (`python manage.py showmigrations agenda`
muestra las dos con `[X]`), se puede borrar la carpeta entera y la línea `'agenda'`
de `proyecto/settings.py`.

Los celulares con la 1.2.25 siguen pidiendo `/api/v1/agenda/`: como ya no existe,
no muestran nada (no es un error para la app).
