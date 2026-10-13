"""
Pasa lo que ya había al modelo nuevo (pantallas + saldo del cliente):

  - Cada cliente recibe tantas pantallas como dispositivos pagó en su
    período en curso (o en el último), y sus aparatos conectados quedan en
    ellas (los que sobran se desconectan: vuelven a poner el código).
  - Cada renovación vieja queda en el saldo del cliente como una carga (con
    lo que se le cobró y de qué revendedor salieron los créditos) y su mes
    de servicio, así las estadísticas siguen dando lo mismo.
"""

from django.db import migrations
from django.utils import timezone


def pasar(apps, schema_editor):
    Cliente = apps.get_model('reventa', 'Cliente')
    Pantalla = apps.get_model('reventa', 'Pantalla')
    Renovacion = apps.get_model('reventa', 'Renovacion')
    CreditoCliente = apps.get_model('reventa', 'CreditoCliente')
    Movimiento = apps.get_model('reventa', 'Movimiento')
    ahora = timezone.now()

    for cliente in Cliente.objects.all():
        renovaciones = Renovacion.objects.filter(cliente=cliente)
        vigente = renovaciones.filter(desde__lte=ahora, hasta__gt=ahora).order_by('-desde').first()
        ultima = vigente or renovaciones.order_by('-hasta').first()
        pantallas = [Pantalla.objects.create(cliente=cliente, numero=numero)
                     for numero in range(1, (ultima.pantallas if ultima else 0) + 1)]
        dispositivos = list(cliente.dispositivos.order_by('conectado'))
        for pantalla, dispositivo in zip(pantallas, dispositivos):
            dispositivo.pantalla = pantalla
            dispositivo.save(update_fields=['pantalla'])
        for sobrante in dispositivos[len(pantallas):]:
            sobrante.delete()

    for renovacion in Renovacion.objects.select_related('cliente').order_by('fecha'):
        movimiento = Movimiento.objects.filter(renovacion=renovacion).first()
        carga = CreditoCliente.objects.create(
            cliente=renovacion.cliente, cantidad=renovacion.creditos, tipo='carga',
            detalle=f'{renovacion.pantallas} pantalla(s) por 1 mes', revendedor_id=renovacion.cliente.revendedor_id,
            movimiento=movimiento, monto_cobrado=renovacion.monto_cobrado, hecho_por_id=renovacion.hecha_por_id,
            fecha=renovacion.fecha,
        )
        CreditoCliente.objects.create(
            cliente=renovacion.cliente, cantidad=-renovacion.creditos, tipo='mes',
            detalle=f'{renovacion.pantallas} pantalla(s)', renovacion=renovacion, fecha=carga.fecha,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('reventa', '0005_pantallas_y_saldo_del_cliente'),
    ]

    operations = [
        migrations.RunPython(pasar, migrations.RunPython.noop),
    ]
