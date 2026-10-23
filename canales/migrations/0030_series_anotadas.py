"""
De qué serie, temporada y capítulo es cada canal, guardado (ver Canal.serie):
los campos y la primera anotación de todo lo que ya estaba cargado. Después
lo mantiene al día consultas.anotar_series.

Si algún día cambia la regla de clasificar.episodio, hace falta una migración
que vacíe `serie_leida_de` en todos: así se vuelven a anotar solos.
"""

from django.db import migrations, models


def anotar(apps, schema_editor):
    from canales.consultas import guardar_anotaciones

    Canal = apps.get_model('canales', 'Canal')
    ultimo = 0
    while True:
        tanda = list(Canal._base_manager.filter(pk__gt=ultimo).order_by('pk').values_list('pk', 'nombre')[:2000])
        if not tanda:
            return
        guardar_anotaciones(schema_editor.connection, Canal._meta.db_table, tanda)
        ultimo = tanda[-1][0]


class Migration(migrations.Migration):

    dependencies = [
        ('canales', '0029_ultimo_problema_en_un_aparato'),
    ]

    operations = [
        migrations.AddField(
            model_name='canal',
            name='capitulo',
            field=models.PositiveIntegerField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='canal',
            name='serie',
            field=models.CharField(blank=True, db_collation='C', editable=False, max_length=120),
        ),
        migrations.AddField(
            model_name='canal',
            name='serie_leida_de',
            field=models.CharField(blank=True, editable=False, max_length=120),
        ),
        migrations.AddField(
            model_name='canal',
            name='temporada',
            field=models.PositiveSmallIntegerField(default=1, editable=False),
        ),
        migrations.AddIndex(
            model_name='canal',
            index=models.Index(fields=['contenido', 'serie'], name='canal_contenido_serie'),
        ),
        migrations.AddIndex(
            model_name='canal',
            index=models.Index(condition=models.Q(('serie_leida_de', models.F('nombre')), _negated=True), fields=['id'], name='canal_serie_sin_anotar'),
        ),
        migrations.RunPython(anotar, migrations.RunPython.noop),
    ]
