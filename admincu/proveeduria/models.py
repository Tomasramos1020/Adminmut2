from xml.parsers.expat import model
from django.db import models
from arquitectura.models import Consorcio, Socio
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Sum
from django.utils.functional import cached_property
from django.utils import timezone

from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError


class Sucursal(models.Model):
	LISTA_CHOICES = (
			('1', 'Lista de precios 1'),
			('2', 'Lista de precios 2'),
			('3', 'Lista de precios 3'),
			('4', 'Lista de precios 4'),
		)

	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	nombre = models.CharField(max_length=30, blank=True, null=True)
	direccion =  models.CharField(max_length=50, blank=True, null=True)
	localidad = models.CharField(max_length=50, blank=True, null=True)
	provincia = models.CharField(max_length=50, blank=True, null=True)
	mail = models.CharField(max_length=50, blank=True, null=True)
	socio = models.ForeignKey(Socio, on_delete=models.CASCADE, null=True, blank=True)
	lista_precio = models.CharField(max_length=15, choices=LISTA_CHOICES, default='1')
	def __str__(self):
		return self.nombre



class Proveedor_proveeduria(models.Model):
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	nombre = models.CharField(max_length=30)
	def __str__(self):
		return self.nombre

class Rubro(models.Model):
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	nombre = models.CharField(max_length=30)
	def __str__(self):
		return self.nombre


class Producto(models.Model):
	UNIDAD_CHOICES = (
			('litros', 'Litros'),
			('gramos', 'Gramos'),
			('cc', 'CC'),
			('unidades', 'Unidades'),
		)

	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	nombre = models.CharField(max_length=30)
	embalaje = models.IntegerField(blank=True, null=True)
	retornable = models.BooleanField(default=False)
	calibre = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
	vencimiento = models.DateField(blank=True, null=True)
	otra_clasificacion = models.CharField(max_length=200, blank=True, null=True)
	precio_1 = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
	precio_2 = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
	precio_3 = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
	precio_4 = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)   
	activo = models.BooleanField(default=True)
	codigo_inter = models.IntegerField(blank=True, null=True)
	descripcion = models.CharField(max_length=200, blank=True, null=True)
	proveedor = models.ForeignKey(Proveedor_proveeduria, on_delete=models.CASCADE, null=True, blank=True)
	rubro = models.ForeignKey(Rubro, on_delete=models.CASCADE, blank=True, null=True)
	unidad_medida = models.CharField(max_length=15, choices=UNIDAD_CHOICES, default='unidades')
	stock_minimo = models.IntegerField(blank=True, null=True)
	codigo_barra = models.IntegerField(blank=True, null=True)
	costo = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
	es_modulo = models.BooleanField(default=False)
	alicuota = models.ForeignKey("creditos.AlicuotaIVA", on_delete=models.PROTECT, null=True, blank=True)

	def __str__(self):
		return self.nombre

	@cached_property
	def cantidad(self):
		resultado = MovimientoStock.objects.filter(producto=self).aggregate(
			total=Sum('cantidad')
		)
		total = resultado['total'] or 0
		return Decimal(total).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

	@cached_property
	def precio_compra(self):
		"""
		Compatibilidad hacia atrás:
		- Si hay costo persistido, úsalo.
		- Si no, caé al último precio de compra.
		"""
		if self.costo is not None:
			return Decimal(self.costo).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

		ultima_compra = self.compra_producto_set.order_by('-id').only('precio').first()
		if ultima_compra and ultima_compra.precio is not None:
			return Decimal(ultima_compra.precio).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
		return Decimal('0.00')  # Devolvemos 0.00 en lugar de None para evitar errores en multiplicaciones

	@cached_property
	def costo_total(self):
		total = self.precio_compra * self.cantidad
		return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

	@cached_property
	def precio_por_cantidad(self):
		if self.precio_1 is not None:
			total = Decimal(self.precio_1) * self.cantidad
			return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
		return Decimal('0.00')


	def recalcular_costo_modulo(self):
		"""
		Si este Producto es un módulo, calcula el costo total
		como la suma de (cantidad * costo) de cada componente
		y actualiza self.costo.
		Si no es módulo, no hace nada.
		"""
		if not self.es_modulo:
			return  # por las dudas

		total = Decimal('0.00')

		# Ojo: usamos .all() sobre related_name='componentes'
		for mc in self.componentes.all():
			comp = mc.componente

			# usamos la mejor noción que ya definiste: precio_compra
			# (que cae a .costo si existe o al último precio de compra)
			costo_unitario = comp.precio_compra or Decimal('0.00')

			if mc.cantidad:
				total += (Decimal(mc.cantidad) * costo_unitario)

		# redondeo lindo
		total = total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

		# guardamos en el propio módulo
		self.costo = total
		# IMPORTANTE: no hacemos save() acá. Lo hace la view.
		return total

# models.py
class ModuloComponente(models.Model):
	producto_modulo = models.ForeignKey(
		Producto, on_delete=models.CASCADE, related_name='componentes'
	)
	componente = models.ForeignKey(Producto, on_delete=models.PROTECT)
	cantidad = models.DecimalField(max_digits=12, decimal_places=2)

	class Meta:
		unique_together = [('producto_modulo', 'componente')]  # evita duplicados

	def clean(self):
		from django.core.exceptions import ValidationError
		# Debe ser un módulo
		if not getattr(self.producto_modulo, 'es_modulo', False):
			raise ValidationError("El producto seleccionado no está marcado como módulo.")
		# No se puede autoincluir
		if self.producto_modulo_id == self.componente_id:
			raise ValidationError("Un módulo no puede ser componente de sí mismo.")
		# (opcional) sin módulos anidados
		if getattr(self.componente, 'es_modulo', False):
			raise ValidationError("No se permiten módulos dentro de módulos.")

		if self.cantidad is None or self.cantidad <= 0:
			raise ValidationError("La cantidad del componente debe ser > 0.")

	def save(self, *args, **kwargs):
		self.full_clean()  # fuerza validaciones siempre
		return super().save(*args, **kwargs)



class Deposito(models.Model):
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	nombre = models.CharField(max_length=30)
	def __str__(self):
		return self.nombre

	
class Stock(models.Model):
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	nombre = models.CharField(max_length=30)

class Transporte(models.Model):
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	nombre = models.CharField(max_length=30)
	def __str__(self):
		return self.nombre	


class Notas_Pedido(models.Model):
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	nombre = models.CharField(max_length=30)


class Consol_Carga(models.Model):
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	nombre = models.CharField(max_length=30)

class Guia_Distri(models.Model):
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	nombre = models.CharField(max_length=30)

class Informe(models.Model):
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	nombre = models.CharField(max_length=30)

class Recibo_Provee(models.Model):
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	nombre = models.CharField(max_length=30)

class Vendendor(models.Model):
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	nombre = models.CharField(max_length=30)

	def __str__(self):
		return self.nombre


class Comp_Venta(models.Model):
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, blank=True, null=True)
	nombre = models.CharField(max_length=30)
	vendedor = models.ForeignKey(Vendendor, on_delete=models.CASCADE, blank=True, null=True)
	deposito = models.ForeignKey(Deposito, on_delete=models.CASCADE, blank=True, null=True)
	transporte = models.ForeignKey(Transporte, on_delete=models.CASCADE, blank=True, null=True)
	fecha_entrega = models.DateField(blank=True, null=True)
	factura = models.ForeignKey('creditos.Factura', on_delete=models.CASCADE, blank=True, null=True)
	liquidacion = models.ForeignKey('creditos.Liquidacion', blank=True, null=True, on_delete=models.CASCADE)
	socio = models.ForeignKey(Socio, blank=True, null=True, on_delete=models.CASCADE)


class Venta_Producto(models.Model):
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, blank=True, null=True)
	producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
	precio = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
	cantidad = models.IntegerField(blank=True, null=True)
	credito = models.ForeignKey('creditos.Credito', on_delete=models.CASCADE)
	liquidacion = models.ForeignKey('creditos.Liquidacion', blank=True, null=True, on_delete=models.CASCADE)
	socio = models.ForeignKey(Socio, blank=True, null=True, on_delete=models.CASCADE)
	costo = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
	padre = models.ForeignKey('self', null=True, blank=True, related_name='devoluciones', on_delete=models.SET_NULL)
	es_nc = models.BooleanField(default=False)  # marca que es un renglón “negativo” de NC (devolución)
	motivo_nc = models.CharField(max_length=200, blank=True, null=True)
	comprobante_nc = models.ForeignKey('comprobantes.Comprobante', null=True, blank=True, on_delete=models.SET_NULL, related_name='vps_nc')
	neto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
	iva = models.DecimalField(max_digits=12, decimal_places=2, default=0)
	total_iva = models.DecimalField(max_digits=12, decimal_places=2, default=0)
	@property
	def devuelto(self):
		"""
		Cantidad devuelta sobre este renglón original (suma de renglones hijo es_nc=True).
		"""
		if not self.pk:
			return Decimal('0')
		total = self.devoluciones.aggregate(s=Sum('cantidad'))['s'] or 0
		return Decimal(total)

	@property
	def disponible_para_devolver(self):
		"""
		Cuánto aún se puede devolver (max: cantidad original - devuelto).
		"""
		if not self.cantidad:
			return Decimal('0')
		return max(Decimal('0'), Decimal(self.cantidad) - Decimal(self.devuelto))

	@property
	def total(self):
		if self.precio and self.cantidad:
			return (Decimal(self.precio) * Decimal(self.cantidad)).quantize(Decimal('0.01'))
		return Decimal('0.00')
	


class Compra_Producto(models.Model):
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
	precio = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
	cantidad = models.IntegerField(blank=True, null=True)
	deuda = models.ForeignKey('op.Deuda', on_delete=models.CASCADE, null=True, blank=True, related_name='compras')
	neto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
	iva = models.DecimalField(max_digits=12, decimal_places=2, default=0)
	alicuota = models.DecimalField(max_digits=5, decimal_places=2, default=0)
	total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

	@property
	def totall(self):
		if self.precio and self.cantidad:
			return self.precio * self.cantidad
		return Decimal('0.00')

	def calcular(self):
		base = self.precio * self.cantidad
		if not self.consorcio.es_ri:
			self.total = base
			# En MySQL estos campos no aceptan NULL
			self.neto = base
			self.iva = Decimal('0.00')
			self.alicuota = Decimal('0.00')
			return
		self.neto = base
		self.iva = base * (self.alicuota / Decimal('100'))
		self.total = self.neto + self.iva

class Remito(models.Model):
	"""Comprobante de salida de mercadería que SOLO baja stock."""
	consorcio   = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	socio       = models.ForeignKey(Socio, blank=True, null=True, on_delete=models.SET_NULL)
	sucursal    = models.ForeignKey(Sucursal, blank=True, null=True, on_delete=models.SET_NULL)
	deposito    = models.ForeignKey(Deposito, on_delete=models.PROTECT)
	transporte  = models.ForeignKey(Transporte, blank=True, null=True, on_delete=models.SET_NULL)
	vendedor    = models.ForeignKey(Vendendor, blank=True, null=True, on_delete=models.SET_NULL)
	fecha       = models.DateField()
	observacion = models.TextField(blank=True, null=True)
	anulado = models.BooleanField(default=False)


	# Si querés numeración visible (sencilla, por consorcio):
	numero      = models.PositiveIntegerField(blank=True, null=True, editable=False)

	class Meta:
		ordering = ['-id']

	def __str__(self):
		return f"Remito #{self.numero or self.pk} – {self.fecha} – {self.deposito}"

	def asignar_numero_si_falta(self):
		if self.numero:
			return
		last = Remito.objects.filter(consorcio=self.consorcio).order_by('-numero').first()
		self.numero = (last.numero + 1) if (last and last.numero) else 1

	@transaction.atomic
	def anular(self, usuario=None, motivo=''):
		"""
		Anula el remito y genera movimientos de stock inversos por cada ítem.
		Idempotente: si ya está anulado, lanza ValidationError.
		"""
		if self.anulado:
			raise ValidationError("El remito ya está anulado.")

		# Si tenés reglas (p.ej. no anular si está facturado), validalas acá:
		# if self.factura_set.exists():
		#     raise ValidationError("No se puede anular: el remito ya está facturado.")

		# Revertir stock de cada ítem
		for item in self.items.select_related('producto').all():
			# El alta original hizo una salida (cantidad negativa). Ahora hacemos la contraria (entrada).
			# Si tu lógica original ya guarda cantidad negativa en MovimientoStock, acá guardamos la opuesta.
			# Asumo tu MovimientoStock tiene campos: producto, deposito, fecha, cantidad, remito_item
			MovimientoStock.objects.create(
				producto=item.producto,
				deposito=self.deposito,
				fecha=timezone.localdate(),
				cantidad=(item.cantidad_salida * Decimal('-1')),  # opuesto
				remito_item=item,
			)

		self.anulado = True
		self.save(update_fields=['anulado'])

class RemitoItem(models.Model):
	remito   = models.ForeignKey(Remito, on_delete=models.CASCADE, related_name='items')
	producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
	cantidad = models.DecimalField(max_digits=9, decimal_places=2)  # permitir decimales
	costo    = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)  # snapshot opcional
	detalle  = models.CharField(max_length=200, blank=True, null=True)

	def clean(self):
		if self.cantidad is None or self.cantidad <= 0:
			raise ValidationError("La cantidad debe ser mayor a 0.")

	@property
	def cantidad_salida(self):
		# Siempre salida (negativo)
		return (self.cantidad * Decimal('-1')).quantize(Decimal('0.01'))

# inventario/models.py

class AjusteStock(models.Model):
	"""Comprobante interno que ajusta stock (entradas/salidas) con un motivo."""
	consorcio   = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	deposito    = models.ForeignKey(Deposito, on_delete=models.PROTECT)
	fecha       = models.DateField()
	motivo      = models.TextField(blank=True, null=True)
	anulado     = models.BooleanField(default=False)

	# numeración simple por consorcio (como Remito)
	numero      = models.PositiveIntegerField(blank=True, null=True, editable=False)

	class Meta:
		ordering = ['-id']

	def __str__(self):
		return f"Ajuste #{self.numero or self.pk} – {self.fecha} – {self.deposito}"

	def asignar_numero_si_falta(self):
		if self.numero:
			return
		last = AjusteStock.objects.filter(consorcio=self.consorcio).order_by('-numero').first()
		self.numero = (last.numero + 1) if (last and last.numero) else 1

	@transaction.atomic
	def anular(self, usuario=None, motivo_extra=''):
		if self.anulado:
			raise ValidationError("El ajuste ya está anulado.")

		# Reversa: crear movimiento opuesto por cada ítem
		for item in self.items.select_related('producto').all():
			MovimientoStock.objects.create(
				producto=item.producto,
				deposito=self.deposito,
				fecha=timezone.localdate(),
				cantidad=(item.cantidad_entrada_salida * Decimal('-1')),  # opuesto
				ajuste_item=item
			)

		self.anulado = True
		self.save(update_fields=['anulado'])


class AjusteStockItem(models.Model):
	SENTIDO = (
		('E', 'Entrada'),
		('S', 'Salida'),
	)
	ajuste   = models.ForeignKey(AjusteStock, on_delete=models.CASCADE, related_name='items')
	producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
	sentido  = models.CharField(max_length=1, choices=SENTIDO)
	cantidad = models.DecimalField(max_digits=9, decimal_places=2)  # > 0
	detalle  = models.CharField(max_length=200, blank=True, null=True)

	def clean(self):
		if self.cantidad is None or self.cantidad <= 0:
			raise ValidationError("La cantidad debe ser mayor a 0.")

	@property
	def cantidad_entrada_salida(self):
		# Entrada = +cantidad ; Salida = -cantidad
		sign = Decimal('1') if self.sentido == 'E' else Decimal('-1')
		return (self.cantidad * sign).quantize(Decimal('0.01'))




class MovimientoStock(models.Model):
	producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
	deposito = models.ForeignKey(Deposito, on_delete=models.CASCADE, blank=True, null=True)
	fecha = models.DateField(auto_now_add=True)
	cantidad = models.DecimalField(max_digits=12, decimal_places=2)  # idem
	venta_producto = models.ForeignKey(Venta_Producto, on_delete=models.SET_NULL, null=True, blank=True)
	compra_producto = models.ForeignKey(Compra_Producto, on_delete=models.SET_NULL, null=True, blank=True)
	remito_item = models.ForeignKey(RemitoItem, on_delete=models.SET_NULL, null=True, blank=True)
	ajuste_item = models.ForeignKey(AjusteStockItem, on_delete=models.SET_NULL, null=True, blank=True)

	def __str__(self):
		return f"{self.fecha} - {self.producto.nombre} - {self.cantidad}"








# Create your models here.
