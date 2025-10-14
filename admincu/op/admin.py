from django.contrib import admin
from import_export.admin import ImportExportMixin
from .models import *
from django.contrib import messages
from contabilidad.asientos.funciones import asiento_deuda, asiento_op
import PyPDF2
from django.db import transaction
from admincu.funciones import randomNumber



def buscar_caja_pdf(modeladmin, request, queryset):
	texto_buscado = 'CAJA TERESA'
	numeros_ops_y_diferencia = []
	ops_a_revisar = []
	for op in queryset:
		pdf_op = op.pdf.path
		fichero_pdf = open(pdf_op, 'rb')
		pdf_leido = PyPDF2.PdfFileReader(fichero_pdf)
		pagina = pdf_leido.getPage(0)
		contenido_pagina = pagina.extractText()
		if texto_buscado in contenido_pagina:			
			operaciones = op.asiento.operaciones.all()
			debe = haber = 0
			for operacion in operaciones:
				debe = debe + operacion.debe
				haber = haber + operacion.haber
				diferencia = debe - haber #para el caso de las ops funciona asi porque el faltante debe darse en el haber
				f = str(op.id) + " - " + str(op.fecha_operacion) + " - " + str(diferencia)
			if diferencia == 0:
				ops_a_revisar.append(op.numero)
				messages.add_message(request, messages.SUCCESS, "Revisar: {}".format(op.id))
			else:
				numeros_ops_y_diferencia.append(f)
				messages.add_message(request, messages.SUCCESS, f)

	# messages.add_message(request, messages.SUCCESS, "las ops buscadas son {}.    Revisar: {}".format(str(numeros_ops_y_diferencia),str(ops_a_revisar)))

buscar_caja_pdf.short_description = "buscar caja"



def rehacer_asiento_deuda(modeladmin, request, queryset):
	asientos_nuevos = 0
	for deuda in queryset:
		if deuda.asiento:
			deuda.asiento.delete()
			asiento = asiento_deuda(deuda)
			asientos_nuevos += 1
	messages.add_message(request, messages.SUCCESS, "Se regeneraron {} asientos nuevos.".format(str(asientos_nuevos)))

rehacer_asiento_deuda.short_description = "Rehacer asiento"

def hacer_pdf_op(modeladmin, request, queryset):
	for op in queryset:
		op.hacer_pdf()
		messages.add_message(request, messages.SUCCESS, "Hecho.")
hacer_pdf_op.short_description = "Hacer PDF"

class GastoDeudaInline(admin.TabularInline):
	model = GastoDeuda


class DeudaAdmin(ImportExportMixin, admin.ModelAdmin):
	list_display = ['__str__', 'consorcio']
	list_filter = ['consorcio']
	inlines = [GastoDeudaInline]
	actions = [rehacer_asiento_deuda]

class GastoOPInline(admin.TabularInline):
	model = GastoOP

class DeudaOPInline(admin.TabularInline):
	model = DeudaOP

class RetencionOPInline(admin.TabularInline):
	model = RetencionOP

class CajaOPInline(admin.TabularInline):
	model = CajaOP

def rehacer_asiento_op(modeladmin, request, queryset):
	asientos_nuevos = 0
	for op in queryset:
		if op.asiento:
			op.asiento.delete()
			fecha_operacion = op.fecha_operacion or op.fecha
			asiento = asiento_op(op, op.gastoop_set.all(), op.deudaop_set.all(), op.retencionop_set.all(), op.cajaop_set.all())
			asientos_nuevos += 1
	messages.add_message(request, messages.SUCCESS, "Se regeneraron {} asientos nuevos.".format(str(asientos_nuevos)))

rehacer_asiento_op.short_description = "Rehacer asiento"


class OPAdmin(ImportExportMixin, admin.ModelAdmin):
	list_display = ['__str__', 'consorcio']
	list_filter = ['consorcio']
	inlines = [
		GastoOPInline,
		DeudaOPInline,
		RetencionOPInline,
		CajaOPInline,
	]
	actions = [rehacer_asiento_op, hacer_pdf_op, buscar_caja_pdf]

admin.site.register(Deuda, DeudaAdmin)
admin.site.register(OP, OPAdmin)



class GastoAdmin(ImportExportMixin, admin.ModelAdmin):
	list_display = ['__str__']


class CajaOPAdmin(ImportExportMixin, admin.ModelAdmin):
	list_display = ['__str__']


def decimal2(x):
	from decimal import Decimal
	if x is None or x == "":
		return Decimal('0.00')
	if isinstance(x, Decimal):
		return x
	return Decimal(str(x))


def generar_asiento_nc(modeladmin, request, queryset):
	# Tomamos solo las que no tienen asiento
	qs = queryset.select_related('consorcio', 'acreedor', 'deuda').filter(asiento__isnull=True)

	generadas, saltadas, errores = 0, 0, 0

	for nc in qs:
		try:
			# 1) Calcular 'aplicado' (sin tocar stock ni deuda)
			aplicado = decimal2(nc.total_aplicado)

			if not aplicado or aplicado <= 0:
				# intentar deducirlo de GastoDeuda negativos en esa fecha
				negativos = (GastoDeuda.objects
							 .filter(deuda=nc.deuda, fecha=nc.fecha, valor__lt=0)
							 .values_list('valor', flat=True))
				if negativos:
					aplicado = sum([abs(decimal2(v)) for v in negativos])
					# nunca más que el total de la NC
					aplicado = min(aplicado, decimal2(nc.total))

			if not aplicado or aplicado <= 0:
				# fallback final
				aplicado = decimal2(nc.total)

			if aplicado <= 0:
				saltadas += 1
				continue

			# 2) Contabilidad base: Debe Proveedores / Haber Gasto (o mercadería)
			# Elegimos una cuenta "representativa":
			gasto_ref = None
			if nc.es_proveeduria:
				gasto_ref = (GastoDeuda.objects
							 .filter(deuda=nc.deuda, gasto__es_proveeduria=True)
							 .select_related('gasto')
							 .first())
			else:
				gasto_ref = (GastoDeuda.objects
							 .filter(deuda=nc.deuda)
							 .select_related('gasto')
							 .first())

			if not gasto_ref:
				messages.warning(
					request,
					f"NC #{nc.pk}: no se halló gasto de referencia; usando fallback a la primera cuenta de gasto de la deuda."
				)
				gasto_ref = (GastoDeuda.objects
							 .filter(deuda=nc.deuda)
							 .select_related('gasto')
							 .first())

			if not gasto_ref:
				mensajes = f"NC #{nc.pk}: no fue posible determinar cuenta contrapartida (sin GastoDeuda)."
				messages.error(request, mensajes)
				errores += 1
				continue

			cuenta_contra = gasto_ref.gasto.cuenta_contable

			# 3) Crear asiento y linkearlo a la NC (sin re-aplicar lógica de negocio)
			with transaction.atomic():
				# SIEMPRE generamos un identificador válido para vincular las operaciones
				identificacion = randomNumber(Operacion, 'numero_aleatorio')

				ops = [
					# Debe Proveedores (baja pasivo)
					Operacion(
						numero_aleatorio=identificacion,
						cuenta=nc.acreedor.cuenta_contable,
						debe=aplicado,
						haber=0,
						descripcion=f"NC Proveedor {nc.acreedor} - Deuda {getattr(nc.deuda, 'numero', nc.deuda_id)}"
					),
					# Haber Gasto/Mercadería (reverso)
					Operacion(
						numero_aleatorio=identificacion,
						cuenta=cuenta_contra,
						debe=0,
						haber=aplicado,
						descripcion=f"NC Proveedor {nc.acreedor} - Reverso gasto/mercadería"
					),
				]

				# 1) guardo operaciones
				Operacion.objects.bulk_create(ops)

				# 2) creo el asiento
				As = Asiento(
					consorcio=nc.consorcio,
					fecha_asiento=nc.fecha,
					descripcion=f"NC Proveedor {nc.acreedor} - Deuda {getattr(nc.deuda, 'numero', nc.deuda_id)}"
				)
				As.save()

				# 3) reconsulto las operaciones ya persistidas (ya tienen PK)
				ops_guardadas = Operacion.objects.filter(numero_aleatorio=identificacion)

				# 4) agrego al M2M con PK válidos
				As.operaciones.add(*ops_guardadas)

				# 5) linkeo a la NC y backfill de total_aplicado si faltaba
				nc.asiento = As
				if not nc.total_aplicado:
					nc.total_aplicado = aplicado
				nc.save(update_fields=['asiento', 'total_aplicado'])


				generadas += 1

		except Exception as e:
			errores += 1
			messages.error(request, f"NC #{nc.pk}: error al crear asiento: {e}")

	if generadas:
		messages.success(request, f"Asientos generados: {generadas}")
	if saltadas:
		messages.info(request, f"NC saltadas (importe <= 0): {saltadas}")
	if errores:
		messages.error(request, f"Con errores: {errores}")


@admin.register(NotaCreditoProveedor)
class NotaCreditoProveedorAdmin(admin.ModelAdmin):
	list_display = ('id', 'fecha', 'acreedor', 'deuda', 'total', 'es_proveeduria', 'asiento')
	actions = [generar_asiento_nc]


admin.site.register(GastoDeuda, GastoAdmin)
admin.site.register(GastoOP, GastoAdmin)
admin.site.register(CajaOP, CajaOPAdmin)
