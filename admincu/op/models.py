from __future__ import unicode_literals
from datetime import date
from django.contrib.auth.models import User, Group
from django.db import models
from consorcios.models import *
from arquitectura.models import *
from django_afip.models import PointOfSales
from contabilidad.models import *
from django.template.loader import render_to_string
from weasyprint import HTML
from django.core.files.uploadedfile import SimpleUploadedFile
from proveeduria.models import Deposito, Producto
from django.db import transaction
from django.db.models import Sum, Q
from proveeduria.models import MovimientoStock, Compra_Producto


def eliminarAsiento(asiento):
    if asiento:
        asiento.operaciones.all().delete()
        asiento.delete()

def revertir_stock_de_compra(deuda):
    """
    Crea movimientos inversos por todo el stock ingresado por las compras
    asociadas a esta deuda. Devuelve cantidad de movimientos creados.
    """
    # Tomo todos los movimientos de stock que entraron por las líneas de compra de la deuda
    movs = (MovimientoStock.objects
            .filter(compra_producto__in=deuda.compras.all()))

    if not movs.exists():
        return 0

    # Agrupo por producto/deposito para no llenar de filas innecesarias
    agregados = (movs.values('producto_id', 'deposito_id')
                      .annotate(total_cant=Sum('cantidad')))

    creados = 0
    for item in agregados:
        total = item['total_cant'] or 0
        if total == 0:
            continue
        MovimientoStock.objects.create(
            producto_id=item['producto_id'],
            deposito_id=item['deposito_id'],
            # OJO: tu modelo tiene fecha = auto_now_add=True, así que ignorará el valor que mandes.
            # Quedará con la fecha de hoy, que es correcto para la reversión.
            cantidad= -total,
            # Lo dejamos sin compra_producto para que se note que es una reversión manual/sistémica
            compra_producto=None
        )
        creados += 1
    return creados

class Deuda(models.Model):
	usuario = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	retencion = models.ForeignKey(Relacion, on_delete=models.CASCADE, blank=True, null=True)
	fecha_carga = models.DateField(auto_now_add=False, auto_now=True)
	fecha = models.DateField()
	numero = models.CharField(max_length=15, blank=True, null=True)
	total = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
	acreedor = models.ForeignKey(Acreedor, on_delete=models.CASCADE)
	observacion = models.TextField(blank=True, null=True)
	confirmado = models.BooleanField(default=False)
	pagado = models.BooleanField(default=False)
	aceptado = models.BooleanField(default=True)
	asiento = models.ForeignKey(Asiento, on_delete=models.SET_NULL, blank=True, null=True, related_name='asiento_deuda')
	anulado = models.DateField(blank=True, null=True)
	asiento_anulado = models.ForeignKey(Asiento, on_delete=models.SET_NULL, blank=True, null=True, related_name='asiento_deuda_anulado')


	def eliminacion(self):
		# 1) Bloqueos obvios: Notas de crédito proveedor aplicadas a la deuda
		if hasattr(self, 'notas_credito') and self.notas_credito.exists():
			return "No se puede eliminar: la deuda tiene Notas de Crédito asociadas."

		# 2) Pagos/OP vigentes = OP confirmadas y NO anuladas
		pagos_vigentes_qs = self.deudaop_set.filter(
			op__confirmado=True,
			op__anulado__isnull=True
		)

		total_pagado_vigente = pagos_vigentes_qs.aggregate(s=Sum('valor'))['s'] or 0

		# Si hay importe vigente distinto de 0, no se puede eliminar
		if total_pagado_vigente != 0:
			return "No se puede eliminar porque la deuda tiene pagos/OP vigentes vinculados."

		# Si llegamos acá: no hay pagos vigentes. Puede haber OP anuladas o neto 0.
		with transaction.atomic():
			if self.compras.exists():
				revertir_stock_de_compra(self)

			eliminarAsiento(self.asiento)
			eliminarAsiento(self.asiento_anulado)

			if self.retencion:
				self.retencion.delete()

			# Borro el desglose de gastos de la deuda (si tu política es conservar histórico, podés omitir)
			GastoDeuda.objects.filter(deuda=self).delete()

			# Opcional: limpiar líneas DeudaOP (solo si querés “limpiar” todo rastro)
			# self.deudaop_set.all().delete()

			self.delete()
			return "Deuda eliminada con éxito"

	def cancelado_a_fecha(self, fecha=None):
		fecha = fecha or date.today()
		total_pagos = (self.deudaop_set
						   .filter(op__confirmado=True,
								   op__anulado__isnull=True,
								   fecha__lte=fecha)
						   .aggregate(s=Sum('valor'))['s'] or 0)
		return total_pagos


	def saldo_a_fecha(self, fecha=None):
		fecha = fecha or date.today()
		total_pagos = (self.deudaop_set
						   .filter(op__confirmado=True,
								   op__anulado__isnull=True,
								   fecha__lte=fecha)
						   .aggregate(s=Sum('valor'))['s'] or 0)
		return (self.total or 0) - total_pagos
		
	@property
	def saldo(self):
		total_pagos = (self.deudaop_set
						   .filter(op__confirmado=True,
								   op__anulado__isnull=True)
						   .aggregate(s=Sum('valor'))['s'] or 0)
		return (self.total or 0) - total_pagos

	def chequear(self):
		if self.saldo == 0:
			self.pagado = True
		else:
			self.pagado = False
		self.save()


	def save(self, *args, **kw):
		if self.retencion and not self.numero:
			numero = 1
			try:
				ultimo = Deuda.objects.filter(consorcio=self.consorcio, retencion=self.retencion).order_by('-numero')[0].numero
			except:
				ultimo = 0
			self.numero = int(ultimo) + numero
		super(Deuda, self).save(*args, **kw)

	def __str__(self):
		nombre = '{}-{}'.format(self.acreedor, self.numero)
		return nombre


class GastoDeuda(models.Model):
	fecha = models.DateField(blank=True, null=True)
	deuda = models.ForeignKey(Deuda, on_delete=models.CASCADE)
	gasto = models.ForeignKey(Gasto, on_delete=models.CASCADE)
	valor = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)


class OP(models.Model):
	usuario = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	fecha = models.DateField(auto_now_add=True, auto_now=False)
	fecha_operacion = models.DateField(blank=True, null=True)
	punto = models.ForeignKey(PointOfSales, on_delete=models.CASCADE)
	numero = models.PositiveIntegerField(blank=True, null=True)
	acreedor = models.ForeignKey(Acreedor, on_delete=models.CASCADE)
	total = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
	descripcion = models.TextField(blank=True, null=True)
	confirmado = models.BooleanField(default=False)
	aceptado = models.BooleanField(default=True)
	asiento = models.ForeignKey(Asiento, on_delete=models.SET_NULL, blank=True, null=True, related_name='asiento_op')
	pdf = models.FileField(upload_to="op/pdf/", blank=True, null=True)
	anulado = models.DateField(blank=True, null=True)
	asiento_anulado = models.ForeignKey(Asiento, on_delete=models.SET_NULL, blank=True, null=True, related_name='asiento_op_anulado')

	def puntof(self):
		agregado = "0"
		numero = str(self.punto)
		largo = len(numero)
		ceros = 4 - largo
		ceros = agregado * ceros
		numero = ceros + numero
		return numero

	def numerof(self):
		agregado = "0"
		numero = str(self.numero)
		largo = len(numero)
		ceros = 8 - largo
		ceros = agregado * ceros
		numero = ceros + numero
		return numero

	def formatoAfip(self):
		data = "%s-%s" % (self.puntof(), self.numerof())
		return data

	def __str__(self):
		nombre = self.formatoAfip()
		return nombre

	def hacer_pdf(self):
		pass

	def hacer_pdf_inst(self):
		"""Genera PDF de la OP y lo devuelve como bytes sin guardarlo en media."""
		# Variables a pdf
		op = self
		cons = self.consorcio
		gastos = self.gastoop_set.all()
		deudas = self.deudaop_set.all()
		retenciones = self.retencionop_set.all()
		cajas = self.cajaop_set.all()

		html_string = render_to_string('op/pdf.html', locals())
		html = HTML(string=html_string, base_url='https://www.admincu.com/pagos/')
		pdf_bytes = html.write_pdf()

		return pdf_bytes
		# if not self.pdf:
		# 	# Variables a pdf
		# 	op = self
		# 	cons = self.consorcio
		# 	gastos = self.gastoop_set.all()
		# 	deudas = self.deudaop_set.all()
		# 	retenciones = self.retencionop_set.all()
		# 	cajas = self.cajaop_set.all()
		# 	html_string = render_to_string('op/pdf.html', locals())
		# 	html = HTML(string=html_string, base_url='https://www.admincu.com/pagos/')
		# 	pdf = html.write_pdf()
		# 	ruta = "{}_{}.pdf".format(
		# 			str(cons.abreviatura),
		# 			str(self.formatoAfip())
		# 		)
		# 	self.pdf = SimpleUploadedFile(ruta, pdf, content_type='application/pdf')
		# 	self.save()

		# return self.pdf

	def save(self, *args, **kw):
		if self.confirmado == True and not self.numero:
			numero_op = 1
			try:
				ultima = OP.objects.filter(
						consorcio=self.consorcio,
						punto=self.punto,
						confirmado=True,
						numero__isnull=False
						).order_by('-numero')[0].numero
			except:
				ultima = 0
			self.numero = ultima + numero_op
		super(OP, self).save(*args, **kw)


	def reversar_operaciones(self):

		""" Reversar operaciones cuando se anula una OP """

		gastos = self.gastoop_set.all()
		if gastos:
			for g in gastos:
				nuevo_gasto = g
				nuevo_gasto.pk = None
				nuevo_gasto.fecha = date.today()
				nuevo_gasto.valor = -nuevo_gasto.valor
				nuevo_gasto.save()

		deudas = self.deudaop_set.all()
		if deudas:
			for d in deudas:
				nueva_deuda = d
				nueva_deuda.pk = None
				nueva_deuda.fecha = date.today()
				nueva_deuda.valor = -nueva_deuda.valor
				nueva_deuda.save()


		retenciones = self.retencionop_set.all()
		if retenciones:
			for r in retenciones:
				nueva_retencion = r
				nueva_retencion.pk = None
				nueva_retencion.fecha = date.today()
				nueva_retencion.valor = -nueva_retencion.valor
				nueva_retencion.save()

		cajas = self.cajaop_set.all()
		if cajas:
			for c in cajas:
				nueva_caja = c
				nueva_caja.pk = None
				nueva_caja.fecha = date.today()
				nueva_caja.valor = -nueva_caja.valor
				nueva_caja.save()

class GastoOP(models.Model):
	fecha = models.DateField(blank=True, null=True)
	op = models.ForeignKey(OP, on_delete=models.CASCADE)
	gasto = models.ForeignKey(Gasto, on_delete=models.CASCADE)
	valor = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)

# Pago de deudas
class DeudaOP(models.Model):
	fecha = models.DateField(blank=True, null=True)
	op = models.ForeignKey(OP, on_delete=models.CASCADE)
	deuda = models.ForeignKey(Deuda, on_delete=models.CASCADE)
	valor = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)

# Creacion de retenciones
class RetencionOP(models.Model):
	fecha = models.DateField(blank=True, null=True)
	op = models.ForeignKey(OP, on_delete=models.CASCADE)
	deuda = models.ForeignKey(Deuda, on_delete=models.CASCADE)
	valor = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)


# Creacion de las formas de pago
class CajaOP(models.Model):
	fecha = models.DateField(blank=True, null=True)
	op = models.ForeignKey(OP, on_delete=models.CASCADE)
	caja = models.ForeignKey(Caja, on_delete=models.CASCADE)
	referencia = models.CharField(max_length=10, blank=True, null=True)
	valor = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)


	def __str__(self):
		nombre = '{}. {}'.format(self.op, self.caja)
		return nombre


	@property
	def nombre(self):

		""" Retorna el nombre. No utilizo __str__ porque nose donde la estoy mostrando """

		nombre = "OP {}.".format(self.op.formatoAfip())

		if self.op.anulado:
			nombre += 'ANULACION'

		return nombre

	@property
	def registro(self):
		return -self.valor, "OP - {}".format(self.op.formatoAfip())

class NotaCreditoProveedor(models.Model):
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	acreedor = models.ForeignKey(Acreedor, on_delete=models.CASCADE)
	deuda = models.ForeignKey(Deuda, on_delete=models.CASCADE, related_name='notas_credito')
	fecha = models.DateField()
	observacion = models.TextField(blank=True, null=True)
	total = models.DecimalField(max_digits=20, decimal_places=2)  # POSITIVO
	es_proveeduria = models.BooleanField(default=False)
	deposito = models.ForeignKey(Deposito, on_delete=models.SET_NULL, blank=True, null=True)
	total_aplicado = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
	asiento = models.ForeignKey(Asiento, on_delete=models.SET_NULL, blank=True, null=True, related_name='notas_credito_proveedor')


class NotaCreditoLineaProducto(models.Model):
	nc = models.ForeignKey(NotaCreditoProveedor, on_delete=models.CASCADE, related_name='lineas_productos')
	producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
	cantidad = models.DecimalField(max_digits=12, decimal_places=2)
	precio = models.DecimalField(max_digits=12, decimal_places=2)

class NotaCreditoLineaGasto(models.Model):
	nc = models.ForeignKey(NotaCreditoProveedor, on_delete=models.CASCADE, related_name='lineas_gastos')
	gasto = models.ForeignKey(Gasto, on_delete=models.CASCADE)
	valor = models.DecimalField(max_digits=12, decimal_places=2)
