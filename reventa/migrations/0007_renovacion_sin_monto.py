"""Lo cobrado ya no va en cada mes de servicio sino en la carga de créditos del cliente (CreditoCliente)."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('reventa', '0006_pasar_a_pantallas_y_saldo'),
    ]

    operations = [
        migrations.RemoveField(model_name='renovacion', name='monto_cobrado'),
    ]
