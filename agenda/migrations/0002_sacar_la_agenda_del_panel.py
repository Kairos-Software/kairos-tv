# La Agenda cargada en el panel no servía: cada persona elige qué quiere que le
# recuerden, y eso lo guarda la app ("Recordarme": app_movil/lib/movil/recordatorios.dart).
# Esta migración borra la tabla que creó la 0001.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('agenda', '0001_initial'),
    ]

    operations = [
        migrations.DeleteModel(name='Evento'),
    ]
