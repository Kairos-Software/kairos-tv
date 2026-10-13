"""
El negocio de reventa.

    Revendedor 1 ──< Cliente 1 ──< Pantalla 1 ──< Dispositivo  (el aparato conectado)
         │              ├──< CreditoCliente   (su saldo: cargas + y meses −)
         │              └──< Renovacion       (cada mes de servicio)
         ├──< Movimiento      (la libreta de créditos del revendedor: + y −)
         └──< Compra >── Paquete

Reglas (definidas por el dueño del negocio):
  - 1 crédito = 1 pantalla (dispositivo) durante 30 días.
  - Un crédito comprado o regalado NO vence: queda en el saldo hasta que se
    usa.
  - El cliente tiene su propio SALDO: se le cargan créditos (por ejemplo, 3
    pantallas × 10 meses = 30) y cada mes se descuentan solos los de sus
    pantallas, hasta que no alcancen. Lo cargado ya se pagó: no vuelve al
    revendedor aunque el cliente no lo use.
  - Cada pantalla es un lugar para UN aparato. Puede tener nombre ("TV
    habitación"), titular y su propio código; se puede cortar sola (sin
    devolución) y agregar una más a mitad de mes (1 crédito, hasta que vence
    el resto; desde el mes siguiente se renueva con las demás).
  - Un cliente SIN revendedor es un "cliente directo" de la empresa: lo
    maneja el administrador y sus créditos los pone la empresa.

Los saldos NO son números que se pisan: son la suma de los movimientos. Así
cada crédito tiene historia (quién lo dio, cuándo, para qué) y las
estadísticas salen solas.
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from herramientas.modelos import ModeloBase

DIAS_POR_CREDITO = 30
# Un dispositivo que no da señales en este tiempo libera su pantalla solo
# (ej: desinstalaron la app o se rompió la TV sin cerrar sesión).
HORAS_SIN_SENAL = 2
# El mes siguiente se descuenta del saldo del cliente un poco antes de que
# termine el actual (la tarea diaria lo hace a tiempo; ver servicios.renovar_los_que_tocan).
ANTICIPO_RENOVACION = timedelta(days=2)


class Revendedor(ModeloBase):
    """Un usuario del panel que vende el servicio a sus propios clientes."""

    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='revendedor')
    precio_pantalla = models.DecimalField(
        'precio por dispositivo', max_digits=12, decimal_places=2, default=0,
        help_text='Lo que cobra a sus clientes por cada pantalla, cada 30 días. Se propone como monto al cargar meses.',
    )
    notas = models.TextField(blank=True, help_text='Solo las ve el administrador.')

    class Meta:
        verbose_name = 'revendedor'
        verbose_name_plural = 'revendedores'
        ordering = ['usuario__first_name', 'usuario__last_name', 'usuario__username']

    def __str__(self):
        return self.usuario.get_full_name() or self.usuario.username

    @property
    def saldo(self):
        """Créditos disponibles (la suma de la libreta)."""
        return self.movimientos.aggregate(total=models.Sum('cantidad'))['total'] or 0


def _codigo_nuevo():
    """8 números al azar que no use otro cliente ni otra pantalla (ej: '48219037')."""
    while True:
        codigo = f'{secrets.randbelow(10 ** 8):08d}'
        if not Cliente.todos.filter(codigo=codigo).exists() and not Pantalla.objects.filter(codigo=codigo).exists():
            return codigo


class Cliente(ModeloBase):
    """Quien mira la TV. Pertenece a un revendedor (o es directo); entra a la app con su código."""

    revendedor = models.ForeignKey(Revendedor, on_delete=models.PROTECT, related_name='clientes',
                                   null=True, blank=True, help_text='Vacío = cliente directo (no gasta créditos).')
    nombre = models.CharField(max_length=150)
    telefono = models.CharField('teléfono', max_length=30, blank=True)
    notas = models.TextField(blank=True)
    # Código fijo para entrar a la app (cómodo con el control remoto). Si
    # cierra sesión o reinstala, vuelve a poner el mismo. Se puede regenerar.
    codigo = models.CharField('código de acceso', max_length=8, unique=True, default=_codigo_nuevo, editable=False)
    vence = models.DateTimeField(null=True, blank=True, help_text='Hasta cuándo puede ver. Vacío = nunca se activó.')
    suspendido = models.BooleanField(default=False, help_text='Cortarle el servicio aunque no haya vencido.')
    # La pantalla del propio revendedor: los revendedores no ven la app gratis
    # con su usuario del panel; se activan a sí mismos con sus créditos, como a
    # cualquier cliente (ver servicios.pantalla_propia).
    propio = models.BooleanField('pantalla propia del revendedor', default=False)

    class Meta:
        verbose_name = 'cliente'
        verbose_name_plural = 'clientes'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    @property
    def es_directo(self):
        return self.revendedor_id is None

    @property
    def codigo_legible(self):
        return f'{self.codigo[:4]} {self.codigo[4:]}'

    @property
    def vigente(self):
        """¿Puede ver ahora? (pagado y no suspendido)"""
        return not self.suspendido and self.vence is not None and self.vence > timezone.now()

    @property
    def saldo(self):
        """Créditos que le quedan para los meses que vienen (la suma de su libreta)."""
        return self.creditos.aggregate(total=models.Sum('cantidad'))['total'] or 0

    def pantallas_vigentes(self):
        """Cuántos aparatos pueden ver HOY: sus pantallas no cortadas (0 si no está vigente)."""
        if not self.vigente:
            return 0
        return self.pantallas.filter(cortada=False).count()

    def meses_pagos(self):
        """Cuántos meses más alcanza su saldo con las pantallas que tiene."""
        cantidad = self.pantallas.count()
        return self.saldo // cantidad if cantidad else 0

    def ultimos_dispositivos(self):
        """Cuántas pantallas tiene (para proponer lo mismo al activar). 1 si no tiene ninguna."""
        return self.pantallas.count() or 1


class Pantalla(models.Model):
    """
    Un lugar para UN aparato del cliente (lo que paga por mes: 1 crédito).
    Con el código del cliente se entra a cualquier pantalla libre sin código
    propio; con el código de una pantalla, solo a esa. Una pantalla cortada
    no deja entrar a nadie (y se sigue pagando: es un castigo, no una baja).
    """

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='pantallas')
    numero = models.PositiveSmallIntegerField('número')
    nombre = models.CharField(max_length=60, blank=True, help_text='Opcional. Ej: "TV habitación".')
    titular = models.CharField(max_length=100, blank=True, help_text='Opcional. Quién la usa. Ej: "Mica Giménez".')
    codigo = models.CharField('código propio', max_length=8, unique=True, null=True, blank=True,
                              help_text='Vacío = se entra con el código del cliente.')
    cortada = models.BooleanField(default=False, help_text='No deja entrar a nadie (sin devolución).')
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'pantalla'
        verbose_name_plural = 'pantallas'
        ordering = ['numero']
        constraints = [models.UniqueConstraint(fields=['cliente', 'numero'], name='pantalla_unica_por_cliente')]

    def __str__(self):
        return f'{self.cliente} · {self.nombre_visible}'

    @property
    def nombre_visible(self):
        return self.nombre or f'Pantalla {self.numero}'

    @property
    def codigo_legible(self):
        return f'{self.codigo[:4]} {self.codigo[4:]}' if self.codigo else ''


class Dispositivo(models.Model):
    """
    Un aparato conectado: la sesión de la app de un cliente, ocupando una de
    sus pantallas. Igual que los tokens de los usuarios, se guarda solo la
    huella (SHA-256) del token, nunca el token.
    """

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='dispositivos')
    pantalla = models.OneToOneField(Pantalla, on_delete=models.CASCADE, null=True, blank=True,
                                    related_name='dispositivo')
    clave_hash = models.CharField(max_length=64, unique=True)
    nombre = models.CharField(max_length=100, blank=True, help_text='Ej: "Smart TV Philips". Lo informa la app.')
    conectado = models.DateTimeField('conectado desde', auto_now_add=True)
    ultima_senal = models.DateTimeField('última señal')

    class Meta:
        verbose_name = 'dispositivo conectado'
        verbose_name_plural = 'dispositivos conectados'
        ordering = ['-ultima_senal']

    def __str__(self):
        return f'{self.cliente} · {self.nombre or "dispositivo sin nombre"}'


class Renovacion(models.Model):
    """
    Un período de servicio: N pantallas por 30 días (gasta N créditos del
    saldo del cliente). Cada mes se crea una sola; una pantalla agregada a
    mitad de mes crea otra, de 1, hasta el vencimiento.
    """

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='renovaciones')
    pantallas = models.PositiveSmallIntegerField('pantallas')
    creditos = models.PositiveIntegerField('créditos usados')
    desde = models.DateTimeField()
    hasta = models.DateTimeField()
    fecha = models.DateTimeField(auto_now_add=True)
    hecha_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')

    class Meta:
        verbose_name = 'renovación'
        verbose_name_plural = 'renovaciones'
        ordering = ['-fecha']

    def __str__(self):
        return f'{self.cliente} · {self.pantallas} dispositivo(s) · {self.desde:%d/%m/%Y} a {self.hasta:%d/%m/%Y}'


class Paquete(ModeloBase):
    """Lo que arma el superusuario para vender créditos a los revendedores."""

    nombre = models.CharField(max_length=80)
    creditos = models.PositiveIntegerField('créditos')
    precio = models.DecimalField(max_digits=12, decimal_places=2)
    activo = models.BooleanField(default=True, help_text='Un paquete inactivo no se puede comprar.')

    class Meta:
        verbose_name = 'paquete de créditos'
        verbose_name_plural = 'paquetes de créditos'
        ordering = ['creditos']

    def __str__(self):
        return f'{self.nombre} ({self.creditos} créditos)'


class Compra(models.Model):
    """Un revendedor compra un paquete. Los créditos se suman al confirmar el pago."""

    class Estado(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente de pago'
        PAGADA = 'pagada', 'Pagada'
        CANCELADA = 'cancelada', 'Cancelada'

    revendedor = models.ForeignKey(Revendedor, on_delete=models.PROTECT, related_name='compras')
    paquete = models.ForeignKey(Paquete, on_delete=models.SET_NULL, null=True, blank=True, related_name='compras')
    # Se copian del paquete: si después el paquete cambia de precio, la compra no
    creditos = models.PositiveIntegerField('créditos')
    precio = models.DecimalField(max_digits=12, decimal_places=2)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)
    creada = models.DateTimeField(auto_now_add=True)
    pedida_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    resuelta = models.DateTimeField('pagada / cancelada', null=True, blank=True)
    resuelta_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='+')

    class Meta:
        verbose_name = 'compra de créditos'
        verbose_name_plural = 'compras de créditos'
        ordering = ['-creada']

    def __str__(self):
        return f'{self.revendedor} · {self.creditos} créditos · {self.get_estado_display()}'


class Movimiento(models.Model):
    """Una línea de la libreta de créditos de un revendedor (+ entra, − sale)."""

    class Tipo(models.TextChoices):
        REGALO = 'regalo', 'Créditos regalados'
        COMPRA = 'compra', 'Compra de paquete'
        RENOVACION = 'renovacion', 'Cargados a un cliente'
        AJUSTE = 'ajuste', 'Ajuste del administrador'

    revendedor = models.ForeignKey(Revendedor, on_delete=models.PROTECT, related_name='movimientos')
    cantidad = models.IntegerField(help_text='Positivo = entran créditos; negativo = salen.')
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    detalle = models.CharField(max_length=200, blank=True)
    compra = models.OneToOneField(Compra, on_delete=models.PROTECT, null=True, blank=True, related_name='movimiento')
    renovacion = models.OneToOneField(Renovacion, on_delete=models.PROTECT, null=True, blank=True,
                                      related_name='movimiento')
    fecha = models.DateTimeField(auto_now_add=True)
    hecho_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')

    class Meta:
        verbose_name = 'movimiento de créditos'
        verbose_name_plural = 'movimientos de créditos'
        ordering = ['-fecha', '-pk']

    def __str__(self):
        return f'{self.revendedor} · {self.cantidad:+d} · {self.get_tipo_display()}'


class CreditoCliente(models.Model):
    """
    Una línea del saldo de un cliente: + cuando se le cargan créditos
    (meses pagados), − cada mes de servicio. Lo cobrado al cliente se anota
    en la carga (así sale la ganancia de cada revendedor).
    """

    class Tipo(models.TextChoices):
        CARGA = 'carga', 'Carga de créditos'
        MES = 'mes', 'Mes de servicio'
        AJUSTE = 'ajuste', 'Ajuste del administrador'

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='creditos')
    cantidad = models.IntegerField(help_text='Positivo = se cargan; negativo = se usan.')
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    detalle = models.CharField(max_length=200, blank=True)
    # De dónde salieron los créditos de una carga: de un revendedor (de su
    # libreta: `movimiento`) o de la empresa (vacío)
    revendedor = models.ForeignKey(Revendedor, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    movimiento = models.OneToOneField(Movimiento, on_delete=models.PROTECT, null=True, blank=True,
                                      related_name='credito_cliente')
    cortesia = models.BooleanField('cortesía', default=False, help_text='Regalo: no se le cobró.')
    monto_cobrado = models.DecimalField('cobrado al cliente', max_digits=12, decimal_places=2, default=0)
    renovacion = models.OneToOneField(Renovacion, on_delete=models.PROTECT, null=True, blank=True,
                                      related_name='credito_cliente')
    fecha = models.DateTimeField(default=timezone.now)
    hecho_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='+')

    class Meta:
        verbose_name = 'crédito de cliente'
        verbose_name_plural = 'créditos de clientes'
        ordering = ['-fecha', '-pk']

    def __str__(self):
        return f'{self.cliente} · {self.cantidad:+d} · {self.get_tipo_display()}'
