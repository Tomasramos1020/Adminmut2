from django.shortcuts import render, redirect
from django.views import generic
from django.urls import reverse_lazy
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.forms.utils import ErrorList
from django_afip.models import *
from django.db import transaction
from contabilidad.asientos.funciones import asiento_deuda


from .models import *
from consorcios.models import *
from admincu.funciones import *
from .forms import *
from django.http import JsonResponse
from django.views.generic import View
from op.models import Deuda, GastoDeuda
from arquitectura.models import Gasto, Acreedor, Ingreso
from decimal import Decimal, ROUND_HALF_UP
# views.py
from django.views.generic import ListView
from .filters import RemitoFilter
from admincu.generic import OrderQS
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404
from django.http import HttpResponse

from django.db import transaction
from django.contrib import messages
from decimal import Decimal, ROUND_HALF_UP
from datetime import date

from comprobantes.models import Comprobante, Cobro  # tu modelo
from django_afip.models import *
from creditos.models import Factura
from contabilidad.asientos.manager import AsientoCreator
from creditos.models import Credito, Factura, Liquidacion
from django.views.decorators.http import require_GET
from django import forms as djforms
from django.db.models import Max
from django.core.exceptions import ObjectDoesNotExist
from collections import defaultdict
from django.db.models import Q
from .utils_stock import mover_stock_por_producto
# proveeduria/views_modulos.py


class Index(generic.TemplateView):

	"""
			Index de herramientas.
	"""

	template_name = 'index.html'

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		sucursales = Sucursal.objects.filter(consorcio=consorcio(self.request)).count()
		productos = Producto.objects.filter(consorcio=consorcio(self.request)).count()
		depositos = Deposito.objects.filter(consorcio=consorcio(self.request)).count()
		stock = Stock.objects.filter(consorcio=consorcio(self.request)).count()
		transportes = Transporte.objects.filter(consorcio=consorcio(self.request)).count()
		notas_pedido = Notas_Pedido.objects.filter(consorcio=consorcio(self.request)).count()
		comp_venta = Comp_Venta.objects.filter(consorcio=consorcio(self.request)).count()
		consol_carga = Consol_Carga.objects.filter(consorcio=consorcio(self.request)).count()
		guias_distri = Guia_Distri.objects.filter(consorcio=consorcio(self.request)).count()
		informes = Informe.objects.filter(consorcio=consorcio(self.request)).count()
		recibos_provee = Recibo_Provee.objects.filter(consorcio=consorcio(self.request)).count()
		rubros = Rubro.objects.filter(consorcio=consorcio(self.request)).count()
		proveedores_proveeduria = Proveedor_proveeduria.objects.filter(consorcio=consorcio(self.request)).count()
		vendedores = Vendendor.objects.filter(consorcio=consorcio(self.request)).count()
		modulos = Producto.objects.filter(consorcio=consorcio(self.request), es_modulo=True).count()
		context.update(locals())
		return context

PIVOT = {
	'Sucursal': ['Sucursales', sucursalForm],
	'Producto': ['Productos', productoForm],
	'Deposito': ['Depositos', depositoForm],
	'Stock': ['Stock', stockForm],
	'Transporte': ['Transportes', transporteForm],
	'Notas_Pedido': ['Notas de Pedido', notas_pedidoForm],
	'Comp_Venta': ['Comprobantes de Venta', comp_ventaForm],
	'Consol_Carga': ['Consolidacion de Carga', consol_cargaForm],
	'Guia_Distri': ['Guia de Distribucion', guia_distriForm],
	'Informe': ['Informes', informeForm],
	'Recibo_Provee': ['Recibos de Proveedores', recibo_proveeForm],
	'Rubro': ['Rubros de Productos', rubroForm],
	'Proveedor_proveeduria':['Proveedor de Proveeduria', proveedor_proveeduriaForm],
	'Vendendor':['Vendedores', vendedorForm]	


}



class Listado(generic.ListView):

	""" Lista del modelo seleccionado """

	template_name = 'elemento.html'

	def get_queryset(self, **kwargs):
		evaluacion = self.kwargs['modelo']
		if evaluacion == 'Stock':
			objetos = Producto.objects.filter(
				consorcio=consorcio(self.request),
				nombre__isnull=False,
				es_modulo=False,
			).order_by('nombre')
		elif evaluacion == 'Producto':
			objetos = Producto.objects.filter(
				consorcio=consorcio(self.request),
				nombre__isnull=False,
			).order_by('nombre')
		else:
			objetos = eval(evaluacion).objects.filter(consorcio=consorcio(self.request), nombre__isnull=False)
		return objetos

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["elemento"] = self.kwargs['modelo']
		context["nombre_elemento"] = PIVOT[self.kwargs['modelo']][0]
		return context

class Crear(generic.CreateView):

	""" Para crear una nueva instancia de cualquier modelo excepto Punto """

	template_name = 'instancia.html'
	model = None

	def get_form_class(self):
		return PIVOT[self.kwargs['modelo']][1]

	def get_form_kwargs(self):
		kwargs = super().get_form_kwargs()
		kwargs['consorcio'] = consorcio(self.request)
		return kwargs

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		elemento = self.kwargs['modelo']
		pregunta = PIVOT[self.kwargs['modelo']][0]
		alerta = "Solo podes modificar estas opciones en un %s principal. Si necesita ayuda comuniquese con el encargado de sistema" % elemento
		context.update(locals())
		return context

	def get_success_url(self, **kwargs):
		return reverse_lazy('elemento', args=(self.kwargs['modelo'],))

	def form_valid(self, form):
		objeto = form.save(commit=False)
		objeto.consorcio = consorcio(self.request)
		try:
			objeto.validate_unique()
			objeto.save()
			form.save_m2m()
			mensaje = "{} guardado con exito".format(self.kwargs['modelo'])
			messages.success(self.request, mensaje)
		except ValidationError:
			form._errors["numero"] = ErrorList(
				[u"Ya existe el numero que desea utilizar."])
			return super().form_invalid(form)

		return super().form_valid(form)

class HeaderExeptMixin:

	def dispatch(self, request, *args, **kwargs):
		try:
			objeto = eval(kwargs['modelo']).objects.get(
				consorcio=consorcio(self.request), pk=kwargs['pk'])
		except:
			messages.error(request, 'No se pudo encontrar.')
			return redirect('elementos')

		return super().dispatch(request, *args, **kwargs)





class Instancia(HeaderExeptMixin, Crear, generic.UpdateView):

	""" Para modificar una instancia de cualquier modelo excepto Punto """

	def get_object(self, queryset=None):
		objeto = eval(self.kwargs['modelo']).objects.get(pk=self.kwargs['pk'])
		return objeto

	def form_valid(self, form):
		retorno = super().form_valid(form)
		objeto = self.get_object()
		return retorno



# Create your views here.


class CrearOperacionView(View):
	template_name = 'crear_operacion.html'

	def get_form_kwargs(self):
		return {
			'request': self.request,
			**self.request.POST.dict(),
		}

	def get(self, request):
		form = OperacionForm(request=self.request)
		formset = VentaProductoFormSet(queryset=Venta_Producto.objects.none())

		cons = consorcio(request)
		# Afecta a todos los formularios del formset (incluye empty_form)
		formset.form.base_fields['producto'].queryset = Producto.objects.filter(consorcio=cons).select_related('alicuota')


		return render(request, self.template_name, {'form': form, 'formset': formset, 'es_ri': cons.es_ri})

	def post(self, request):
		form = OperacionForm(request.POST, request=request)
		formset = VentaProductoFormSet(request.POST, queryset=Venta_Producto.objects.none())

		cons = consorcio(request)
		# Importante: también en POST, antes de is_valid(), para que valide contra el queryset correcto
		formset.form.base_fields['producto'].queryset = Producto.objects.filter(consorcio=cons)

		if form.is_valid() and formset.is_valid():
			socio = form.cleaned_data['socio']
			sucursal = form.cleaned_data.get('sucursal')
			fecha = form.cleaned_data['fecha']
			transporte = form.cleaned_data['transporte']
			deposito = form.cleaned_data['deposito']
			vendedor = form.cleaned_data['vendedor']
			punto = form.cleaned_data['punto_venta']

			capital = Decimal('0.00')
			neto = Decimal('0')
			iva_total = Decimal('0')
			faltan_alicuota = []

			for linea in formset:
				if linea.cleaned_data and not linea.cleaned_data.get('DELETE', False):
					producto = linea.cleaned_data['producto']
					precio = linea.cleaned_data.get('precio') or Decimal('0')
					cantidad = linea.cleaned_data.get('cantidad') or Decimal('0')
					subtotal = precio * cantidad
					if cons.es_ri:
						if not producto.alicuota:
							faltan_alicuota.append(producto)
							continue
						alicuota = producto.alicuota
						porc = alicuota.porcentaje / Decimal(100)
						iva = (precio * cantidad) * porc

						neto += subtotal
						iva_total += iva
					else:
						capital += precio * cantidad
			if cons.es_ri and faltan_alicuota:
				messages.error(
					request,
					"Hay productos sin alícuota IVA: " +
					", ".join(sorted({str(p) for p in faltan_alicuota}))
				)
				return render(request, self.template_name, {'form': form, 'formset': formset, 'es_ri': cons.es_ri})
			if cons.es_ri:
				capital = neto + iva_total

			# Crear liquidación
			liquidacion = Liquidacion.objects.create(
				consorcio=cons,
				punto=punto,
				capital=capital, 
				fecha=fecha,
				estado='confirmado'
			)

			if cons.es_ri:
				# Tipo factura automática
				cond_codigo = socio.condicionIVA.codigo if socio.condicionIVA else "5"
				if cond_codigo == '1':
					tipo = '1'   # Factura A
				else:
					tipo = '6'   # Factura B

				receipt = Receipt.objects.create(
					point_of_sales=punto,
					receipt_type=ReceiptType.objects.get(code=tipo),
					concept=ConceptType.objects.get(code="1"),
					document_type=socio.tipo_documento,
					document_number=socio.numero_documento,
					issued_date=fecha,

					net_taxed=neto,
					net_untaxed=0,
					exempt_amount=0,
					total_amount=capital,

					currency=CurrencyType.objects.get(code="PES"),
					service_start=fecha,
					service_end=fecha
				)
				for linea in formset:
					if linea.cleaned_data and not linea.cleaned_data.get('DELETE', False):
						producto = linea.cleaned_data['producto']
						neto_item = (linea.cleaned_data.get('precio') or Decimal('0')) * (linea.cleaned_data.get('cantidad') or Decimal('0'))
						alicuota = producto.alicuota

						codigo_afip = str(alicuota.codigo_afip)

						Vat.objects.create(
							receipt=receipt,
							vat_type=VatType.objects.get(code=codigo_afip),
							base_amount=neto_item,
							amount=neto_item * (alicuota.porcentaje / Decimal(100))
						)
			else:
				# Crear factura
				receipt = Receipt.objects.create(
					point_of_sales=punto,
					receipt_type=ReceiptType.objects.get(code=101),
					concept=ConceptType.objects.get(code=1),
					document_type= socio.tipo_documento,
					document_number=socio.numero_documento,
					issued_date=fecha,
					net_untaxed=0,
					exempt_amount=0,
					expiration_date=fecha,
					currency=CurrencyType.objects.get(code="PES"),
					service_start = fecha,
					service_end = fecha,
					total_amount = capital,
					net_taxed = capital
				)
			factura = Factura.objects.create(
				consorcio=cons,
				receipt = receipt,
				liquidacion = liquidacion,
				socio=socio,
			)

			# Crear crédito
			credito = Credito.objects.create(
				consorcio=cons,
				socio=socio,
				factura=factura,
				liquidacion=liquidacion,
				fecha=fecha,
				detalle='Venta Proveeduría',
				periodo = fecha,
				ingreso = Ingreso.objects.get(consorcio=cons, es_proveeduria=True),
				capital = capital,
			)

			# Crear comprobante de venta
			comp_venta = Comp_Venta.objects.create(
				consorcio=cons,
				socio=socio,
				sucursal=sucursal,
				nombre="Venta Proveeduría",
				vendedor=vendedor,
				deposito=deposito,
				transporte=transporte, 
				fecha_entrega=fecha,
				factura=factura,
				liquidacion=liquidacion
			)

			# Crear líneas de productos
			for linea in formset:
				if linea.cleaned_data and not linea.cleaned_data.get('DELETE', False):
					vp = linea.save(commit=False)
					vp.consorcio = cons
					vp.socio = socio
					vp.sucursal = sucursal
					vp.credito = credito
					vp.liquidacion = liquidacion

					# Asegurar costo:
					if not vp.costo:
						prod_costo = getattr(vp.producto, 'costo', None)
						vp.costo = prod_costo or Decimal('0.00')
					# Calcular IVA SOLO si es Responsable Inscripto
					if cons.es_ri:
						alicuota = vp.producto.alicuota
						porc = alicuota.porcentaje / Decimal(100)

						vp.alicuota = alicuota
						vp.neto = vp.precio * vp.cantidad
						vp.iva = vp.neto * porc
						vp.total_iva = vp.neto + vp.iva

					vp.save()

					# Registrar movimiento de stock (salida)
					ms = mover_stock_por_producto(
						producto=vp.producto,
						deposito=deposito,
						fecha=fecha,
						cantidad_signed=Decimal('-1') * Decimal(vp.cantidad or 0),
						venta_producto=vp
					)

			factura.validar_factura()
			if (
				factura.receipt
				and factura.receipt.receipt_type
				and str(factura.receipt.receipt_type.code) not in ["101", "104"]
				and factura.observacion
			):
				messages.error(
					request,
					"AFIP devolvio un error: {}".format(factura.observacion),
				)

			liquidacion.hacer_asiento()

			return redirect('facturacion-proveeduria')

		return render(request, self.template_name, {'form': form, 'formset': formset,'es_ri': cons.es_ri})



def obtener_sucursales(request):
	socio_id = request.GET.get('socio_id')
	data = []
	if socio_id:
		sucursales = Sucursal.objects.filter(socio_id=socio_id)
		data = [{'id': s.id, 'nombre': s.nombre} for s in sucursales]
	return JsonResponse({'sucursales': data})

def obtener_precio_producto(request):
	producto_id = request.GET.get('producto_id')
	try:
		p = Producto.objects.get(id=producto_id)
		precio = p.precio_1 or 0
		costo = getattr(p, 'costo', None)

		iva = p.alicuota.porcentaje if p.alicuota else Decimal('0')
		if costo is None:
			costo = getattr(p, 'costo', 0)
		return JsonResponse({'precio_1': float(precio), 'costo': float(costo or 0),'iva': float(iva)},)
	except Producto.DoesNotExist:
		return JsonResponse({'precio_1': 0, 'costo': 0, 'iva': 0})


class CrearCompraView(View):
	template_name = 'crear_compra.html'

	def get_form_kwargs(self):
		return {
			'request': self.request,
			**self.request.POST.dict(),
		}

	def get(self, request):
		form = CompraForm(request=self.request)
		formset = CompraProductoFormSet(
			queryset=Compra_Producto.objects.none(),
			form_kwargs={'request': request}   # <-- clave para filtrar productos por consorcio
		)
		return render(request, self.template_name, {'form': form, 'formset': formset,'es_ri': consorcio(request).es_ri })

	@transaction.atomic
	def post(self, request):
		form = CompraForm(request.POST, request=request)
		formset = CompraProductoFormSet(
			request.POST,
			form_kwargs={'request': request}   # <-- también en POST
		)

		if form.is_valid() and formset.is_valid():
			cons = consorcio(request)
			acreedor = form.cleaned_data['acreedor']
			fecha = form.cleaned_data['fecha']
			deposito = form.cleaned_data['deposito']
			observacion = form.cleaned_data.get('observacion')

			# número final (compacto) ya armado por el form:
			numero_fmt = form.cleaned_data['numero']   # ej: B000100000005

			# evitar duplicados por consorcio + acreedor + numero
			if Deuda.objects.filter(consorcio=cons, acreedor=acreedor, numero=numero_fmt).exists():
				messages.error(request, "Ya existe una deuda con ese número.")
				return redirect('deudas')

			deuda = Deuda.objects.create(
				consorcio=cons,
				acreedor=acreedor,
				fecha=fecha,
				numero=numero_fmt,     # <<— sólo este campo del modelo
				total=Decimal('0.00'),
				observacion=observacion,
				confirmado=True
			)

			gasto_default = Gasto.objects.filter(consorcio=cons, es_proveeduria=True).first()
			if not gasto_default:
				messages.error(request, "No hay gastos de proveeduría configurados.")
				raise Exception("Gasto faltante")

			lineas = []
			for linea in formset:
				if not linea.cleaned_data:
					continue
				compra = linea.save(commit=False)
				if not compra.producto_id:
					continue
				try:
					precio = Decimal(compra.precio or 0)
					cantidad = Decimal(compra.cantidad or 0)
				except Exception:
					continue
				if precio <= 0 or cantidad <= 0:
					continue
				compra.consorcio = cons
				compra.deuda = deuda
				if cons.es_ri:
					compra.alicuota = compra.producto.alicuota.porcentaje if compra.producto.alicuota else Decimal('0')
				lineas.append(compra)

			if not lineas:
				messages.error(request, "Cargá al menos un producto con precio y cantidad.")
				transaction.set_rollback(True)
				return render(request, self.template_name, {'form': form, 'formset': formset,'es_ri': cons.es_ri})

			ajuste = form.cleaned_data.get('ajuste_distribuible') or Decimal('0')
			try:
				ajuste = Decimal(ajuste).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
			except Exception:
				ajuste = Decimal('0.00')

			if ajuste != 0:
				total_base = sum(
					(Decimal(c.precio or 0) * Decimal(c.cantidad or 0)) for c in lineas
				)
				if total_base == 0:
					messages.error(request, "No se puede distribuir el ajuste porque el total base es 0.")
					transaction.set_rollback(True)
					return render(request, self.template_name, {'form': form, 'formset': formset,'es_ri': cons.es_ri})

				total_objetivo = total_base + ajuste
				if total_objetivo <= 0:
					messages.error(request, "El ajuste no puede dejar el total en cero o negativo.")
					transaction.set_rollback(True)
					return render(request, self.template_name, {'form': form, 'formset': formset,'es_ri': cons.es_ri})
				factor = total_objetivo / total_base
				total_aplicado = Decimal('0.00')

				for idx, compra in enumerate(lineas):
					cant = Decimal(compra.cantidad or 0)
					if cant == 0:
						continue
					if idx < len(lineas) - 1:
						nuevo_precio = (Decimal(compra.precio or 0) * factor).quantize(
							Decimal('0.01'), rounding=ROUND_HALF_UP
						)
						compra.precio = nuevo_precio
						total_aplicado += nuevo_precio * cant
					else:
						objetivo_linea = total_objetivo - total_aplicado
						nuevo_precio = (objetivo_linea / cant).quantize(
							Decimal('0.01'), rounding=ROUND_HALF_UP
						)
						compra.precio = nuevo_precio
						total_aplicado += nuevo_precio * cant

				diff = (total_objetivo - total_aplicado).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
				if diff != 0:
					messages.warning(
						request,
						f"El ajuste distribuido difiere por {diff}. Esto puede ocurrir por redondeos."
					)

			for compra in lineas:
				compra.calcular()
				compra.save()

				MovimientoStock.objects.create(
					producto=compra.producto,
					deposito=deposito,
					cantidad=compra.cantidad,
					compra_producto=compra,
					fecha=fecha
				)

				GastoDeuda.objects.create(
					deuda=deuda,
					gasto=gasto_default,
					valor=compra.total,
					fecha=fecha
				)
			from django.db.models import Sum

			if cons.es_ri:
				totales = deuda.compras.aggregate(
					neto=Sum('neto'),
					iva=Sum('iva'),
					total=Sum('total')
				)
				deuda.neto = totales['neto'] or 0
				deuda.iva = totales['iva'] or 0
				deuda.total = totales['total'] or 0
			else:
				deuda.total = deuda.compras.aggregate(Sum('total'))['total__sum'] or 0
				deuda.neto = Decimal('0.00')
				deuda.iva = Decimal('0.00')

			deuda.save()

			asiento = asiento_deuda(deuda)
			messages.success(request, "Compra y deuda creadas correctamente.")
			return redirect('deudas')

		return render(request, self.template_name, {'form': form, 'formset': formset,'es_ri': consorcio(request).es_ri})

@group_required('administrativo', 'contable')
def obtener_precio_producto_remito(request):
	pid = request.GET.get('producto_id')
	precio = None
	if pid:
		try:
			prod = Producto.objects.get(id=pid)
			# Elegí la fuente del precio:
			# primero intento precio_venta, si no, precio, si no, costo
			for attr in ('precio_venta', 'precio', 'costo'):
				if hasattr(prod, attr) and getattr(prod, attr) is not None:
					precio = Decimal(getattr(prod, attr))
					break
		except Producto.DoesNotExist:
			pass
	return JsonResponse({'precio': f"{precio:.2f}" if precio is not None else ""})


class CrearRemitoView(View):
	template_name = 'crear_remito.html'

	def get_form_kwargs(self):
		return {'request': self.request, **self.request.POST.dict()}

	def get(self, request):
		form = RemitoForm(request=self.request)
		formset = RemitoItemFormSet(queryset=RemitoItem.objects.none())
		# Limitar productos por consorcio en formset
		cons = consorcio(request)
		formset.form.base_fields['producto'].queryset = Producto.objects.filter(consorcio=cons, activo=True)
		return render(request, self.template_name, {'form': form, 'formset': formset})

	@transaction.atomic
	def post(self, request):
		form    = RemitoForm(request.POST, request=request)
		formset = RemitoItemFormSet(request.POST, queryset=RemitoItem.objects.none())

		cons = consorcio(request)
		formset.form.base_fields['producto'].queryset = Producto.objects.filter(consorcio=cons, activo=True)

		if form.is_valid() and formset.is_valid():
			socio      = form.cleaned_data.get('socio')
			sucursal   = form.cleaned_data.get('sucursal')
			fecha      = form.cleaned_data['fecha']
			deposito   = form.cleaned_data['deposito']
			transporte = form.cleaned_data.get('transporte')
			vendedor   = form.cleaned_data.get('vendedor')
			obs        = form.cleaned_data.get('observacion')

			# Crear Remito (con numeración simple por consorcio)
			remito = Remito(
				consorcio=cons,
				socio=socio, sucursal=sucursal,
				deposito=deposito, transporte=transporte, vendedor=vendedor,
				fecha=fecha, observacion=obs
			)
			remito.asignar_numero_si_falta()
			remito.save()

			# Crear ítems + descarga de stock
			lineas_cargadas = 0
			for linea in formset:
				if not linea.cleaned_data or linea.cleaned_data.get('DELETE', False):
					continue
				item = linea.save(commit=False)
				item.remito = remito
				# snapshot de costo (opcional)
				if item.producto.costo is not None:
					item.costo = Decimal(item.producto.costo)
				item.full_clean()
				item.save()
				lineas_cargadas += 1

				# Registrar movimiento de stock (salida)
				mover_stock_por_producto(
					producto=item.producto,
					deposito=deposito,
					fecha=fecha,
					cantidad_signed=item.cantidad_salida,  # NEGATIVO
					remito_item=item
				)

			if lineas_cargadas == 0:
				# Sin líneas, revertir
				raise ValidationError("Cargá al menos un producto con cantidad.")

			return redirect('facturacion-proveeduria')  # definí una vista de listado
		return render(request, self.template_name, {'form': form, 'formset': formset})




@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class RegistroRemitos(OrderQS):
	"""Registro de remitos (solo imprimir)."""
	model = Remito
	filterset_class = RemitoFilter
	template_name = 'remitos.html'
	paginate_by = 50

	def get_queryset(self, **kwargs):
		qs = super().get_queryset(**kwargs).select_related('consorcio','deposito','socio','sucursal','vendedor','transporte')
		# limitar por consorcio actual (como en tus otras vistas)
		try:
			from admincu.funciones import consorcio
			c = consorcio(self.request)
			qs = qs.filter(consorcio=c)
		except Exception:
			pass
		return qs

def remito_pdf(request, pk):
	remito = get_object_or_404(
		Remito.objects.select_related(
			'consorcio','deposito','socio','sucursal','vendedor','transporte',
			'consorcio__contribuyente','consorcio__contribuyente__extras'
		).prefetch_related('items__producto'),
		pk=pk
	)

	# Armar datos con precio_1 y subtotal calculados al vuelo (sin tocar DB)
	items_data = []
	total_general = Decimal('0.00')
	for it in remito.items.all():
		# Fuente de precio informativo
		precio = getattr(it.producto, 'precio_1', None) or Decimal('0.00')
		# Asegurar Decimal
		if not isinstance(precio, Decimal):
			try:
				precio = Decimal(str(precio))
			except Exception:
				precio = Decimal('0.00')

		cantidad = it.cantidad or Decimal('0.00')
		if not isinstance(cantidad, Decimal):
			try:
				cantidad = Decimal(str(cantidad))
			except Exception:
				cantidad = Decimal('0.00')

		subtotal = (precio * cantidad).quantize(Decimal('0.01'))
		total_general += subtotal

		items_data.append({
			'it': it,
			'precio': precio.quantize(Decimal('0.01')),
			'subtotal': subtotal,
		})

	context = {
		'remito': remito,
		'items_data': items_data,
		'total_general': total_general.quantize(Decimal('0.01')),
	}

	html = render_to_string('remito.html', context)
	pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf()

	resp = HttpResponse(pdf_bytes, content_type='application/pdf')
	resp['Content-Disposition'] = f'inline; filename="remito_{remito.numero or remito.pk}.pdf"'
	return resp


# views.py

@transaction.atomic
def remito_anular(request, pk):
	remito = get_object_or_404(Remito.objects.prefetch_related('items__producto'), pk=pk)
	try:
		remito.anular()
		messages.success(request, f"Remito #{remito.numero or remito.pk} anulado y stock revertido.")
	except ValidationError as e:
		messages.error(request, f"No se pudo anular: {e}")
	except Exception as e:
		messages.error(request, f"Error al anular: {e}")

	return redirect('remitos-registro')

class CrearAjusteView(View):
	template_name = 'ajustes/crear_ajuste.html'

	def get_form_kwargs(self):
		return {'request': self.request, **self.request.POST.dict()}

	def get(self, request):
		form = AjusteForm(request=self.request)
		formset = AjusteItemFormSet(queryset=AjusteStockItem.objects.none())
		# limitar productos por consorcio
		cons = consorcio(request)
		formset.form.base_fields['producto'].queryset = Producto.objects.filter(consorcio=cons, activo=True)
		return render(request, self.template_name, {'form': form, 'formset': formset})

	@transaction.atomic
	def post(self, request):
		form    = AjusteForm(request.POST, request=request)
		formset = AjusteItemFormSet(request.POST, queryset=AjusteStockItem.objects.none())

		cons = consorcio(request)
		formset.form.base_fields['producto'].queryset = Producto.objects.filter(consorcio=cons, activo=True)

		if form.is_valid() and formset.is_valid():
			fecha    = form.cleaned_data['fecha']
			deposito = form.cleaned_data['deposito']
			motivo   = form.cleaned_data.get('motivo')

			ajuste = AjusteStock(
				consorcio=cons,
				deposito=deposito,
				fecha=fecha,
				motivo=motivo
			)
			ajuste.asignar_numero_si_falta()
			ajuste.save()

			lineas_cargadas = 0
			for linea in formset:
				if not linea.cleaned_data or linea.cleaned_data.get('DELETE', False):
					continue

				item = linea.save(commit=False)
				item.ajuste = ajuste
				item.full_clean()
				item.save()
				lineas_cargadas += 1

				# Movimiento de stock (E=+ ; S=-)
				MovimientoStock.objects.create(
					producto=item.producto,
					deposito=deposito,
					fecha=fecha,
					cantidad=item.cantidad_entrada_salida,
					ajuste_item=item
				)

			if lineas_cargadas == 0:
				raise ValidationError("Cargá al menos un producto con cantidad.")

			return redirect('registro-ajustes')  # definí esta url
		return render(request, self.template_name, {'form': form, 'formset': formset})


# proveeduria/views.py
from .filters import AjusteFilter

@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class RegistroAjustes(OrderQS):
	model = AjusteStock
	filterset_class = AjusteFilter              # <— clave
	template_name = 'ajustes/ajustes.html'
	paginate_by = 50

	def get_queryset(self, **kwargs):
		qs = super().get_queryset(**kwargs).select_related('consorcio','deposito')
		try:
			from admincu.funciones import consorcio
			c = consorcio(self.request)
			qs = qs.filter(consorcio=c)
		except Exception:
			pass
		return qs

	# si tu OrderQS NO pasa request al FilterSet, podés sobreescribir así:
	def get(self, request, *args, **kwargs):
		# esto fuerza que el FilterSet reciba request
		datos = self.model.objects.all()
		try:
			from admincu.funciones import consorcio
			c = consorcio(request)
			datos = datos.filter(consorcio=c)
		except Exception:
			pass
		self.filter = self.filterset_class(request.GET or None, queryset=datos, request=request)
		self.object_list = self.order_queryset(self.filter.qs) if hasattr(self, 'order_queryset') else self.filter.qs
		context = self.get_context_data(object_list=self.object_list)
		return self.render_to_response(context)



def ajuste_pdf(request, pk):
	ajuste = get_object_or_404(
		AjusteStock.objects.select_related(
			'consorcio','deposito','consorcio__contribuyente','consorcio__contribuyente__extras'
		).prefetch_related('items__producto'),
		pk=pk
	)
	html = render_to_string('ajustes/ajuste_pdf.html', {'ajuste': ajuste})
	pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf()

	resp = HttpResponse(pdf_bytes, content_type='application/pdf')
	resp['Content-Disposition'] = f'inline; filename="ajuste_{ajuste.numero or ajuste.pk}.pdf"'
	return resp


@group_required('administrativo', 'contable')
def ajuste_anular(request, pk):
	ajuste = get_object_or_404(AjusteStock, pk=pk)
	ajuste.anular(usuario=request.user)
	messages.success(request, "Ajuste anulado y stock revertido.")
	return redirect('registro-ajustes')

@require_GET
def facturas_por_socio(request):
	cons = consorcio(request)
	socio_id = request.GET.get('socio')
	items = []
	if socio_id:
		qs = (Factura.objects
			  .filter(consorcio=cons, socio_id=socio_id,
					  credito__ingreso__es_proveeduria=True,
					  liquidacion__estado='confirmado')
			  .select_related('receipt', 'receipt__point_of_sales')
			  .order_by('-id')
			  .distinct())

		for f in qs:
			r = f.receipt
			if not r:
				continue
			# POS: puede ser FK; tomamos number si existe, sino el propio valor
			pos_val = getattr(r.point_of_sales, 'number', r.point_of_sales)
			pos_str = str(pos_val).zfill(4)
			nro_str = str(r.receipt_number or 0).zfill(8)
			fecha = r.issued_date.strftime("%d/%m/%Y") if r.issued_date else ""
			importe = r.total_amount or 0
			etiqueta = f"{pos_str}-{nro_str} · {fecha} · ${importe}"
			items.append({"id": f.id, "text": etiqueta})

	return JsonResponse({"items": items})


Q00 = Decimal('0.00')

def q2(x: Decimal) -> Decimal:
	return (x or Q00).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

class NCProveeduriaCreateView(View):
	template_inicial = 'nc/ventas/nc_inicial.html'
	template_renglones = 'nc/ventas/nc_renglones.html'
	formset_prefix = 'dev'  # prefijo único

	# ---------- Helpers ----------
	def _rows_from_vps(self, vps):
		rows = []
		for vp in vps:
			rows.append({
				'producto': vp.producto.nombre,
				'precio': vp.precio or Q00,
				'cantidad_original': vp.cantidad or 0,
				'ya_devuelto': getattr(vp, 'devuelto', 0),
			})
		return rows

	def _rows_from_post(self, post):
		total = int(post.get(f'{self.formset_prefix}-TOTAL_FORMS', 0) or 0)
		rows = []
		for i in range(total):
			vp_id = post.get(f'{self.formset_prefix}-{i}-vp_id')
			if not vp_id:
				rows.append(None); continue
			try:
				vp = (Venta_Producto.objects
					  .select_related('producto')
					  .get(id=vp_id))
				rows.append({
					'producto': vp.producto.nombre,
					'precio': vp.precio or Q00,
					'cantidad_original': vp.cantidad or 0,
					'ya_devuelto': getattr(vp, 'devuelto', 0),
				})
			except Venta_Producto.DoesNotExist:
				rows.append(None)
		return rows

	def _socio_factura_from_post(self, post):
		socio_obj = None
		factura_obj = None
		try:
			socio_id = post.get('socio')
			factura_id = post.get('factura')
			if socio_id:
				socio_obj = Socio.objects.get(id=socio_id)
			if factura_id:
				factura_obj = Factura.objects.select_related('receipt').get(id=factura_id)
		except Exception:
			pass
		return socio_obj, factura_obj

	# ---------- GET ----------
	def get(self, request):
		cons = consorcio(request)
		form = NCProveeduriaInicialForm(consorcio=cons)
		return render(request, self.template_inicial, {'form': form})

	# ---------- POST ----------
	def post(self, request):
		cons = consorcio(request)

		is_step2 = (
			request.POST.get('step') == '2'
			or f'{self.formset_prefix}-TOTAL_FORMS' in request.POST
		)

		# ===== PASO 1 =====
		if not is_step2:
			form = NCProveeduriaInicialForm(request.POST, consorcio=cons)
			if not form.is_valid():
				return render(request, self.template_inicial, {'form': form})

			socio = form.cleaned_data['socio']
			factura = form.cleaned_data['factura']

			vps = (Venta_Producto.objects
				   .filter(consorcio=cons, socio=socio, credito__factura=factura, es_nc=False)
				   .select_related('producto'))

			if not vps.exists():
				messages.warning(request, "La factura seleccionada no tiene renglones de Proveeduría para devolver.")
				return render(request, self.template_inicial, {'form': form})

			# Inicial del formset
			formset_initial = []
			for vp in vps:
				formset_initial.append({
					'vp_id': vp.id,
					'producto': vp.producto.nombre,
					'precio': vp.precio or Q00,
					'cantidad_original': vp.cantidad or 0,
					'ya_devuelto': getattr(vp, 'devuelto', 0),
					'devolver': None,
					'motivo': '',
				})
			formset = DevolucionFormSet(initial=formset_initial, prefix=self.formset_prefix)

			# Form hidden para re-postear socio/factura
			form_hidden = NCProveeduriaInicialForm(consorcio=cons, initial={
				'socio': socio.id,
				'factura': factura.id,
			})
			form_hidden.fields['socio'].widget = djforms.HiddenInput()
			form_hidden.fields['factura'].widget = djforms.HiddenInput()

			rows = self._rows_from_vps(vps)
			pairs = list(zip(formset.forms, rows))

			ctx = {
				'form': form_hidden,
				'formset': formset,
				'pairs': pairs,
				'step': '2',
				'factura': factura,
				'socio': socio,
			}
			return render(request, self.template_renglones, ctx)

		# ===== PASO 2 =====
		form = NCProveeduriaInicialForm(request.POST, consorcio=cons)
		form.fields['socio'].widget = djforms.HiddenInput()
		form.fields['factura'].widget = djforms.HiddenInput()
		formset = DevolucionFormSet(request.POST, prefix=self.formset_prefix)

		if not form.is_valid() or not formset.is_valid():
			socio_obj, factura_obj = self._socio_factura_from_post(request.POST)
			rows = self._rows_from_post(request.POST)
			pairs = list(zip(formset.forms, rows))
			ctx = {
				'form': form,
				'formset': formset,
				'pairs': pairs,
				'step': '2',
				'socio': socio_obj,
				'factura': factura_obj,
				'form_errors': form.errors,
				'formset_non_form_errors': formset.non_form_errors(),
				'formset_errors': formset.errors,
			}
			return render(request, self.template_renglones, ctx)

		socio = form.cleaned_data['socio']
		factura = form.cleaned_data['factura']
		hoy = date.today()

		# Crédito "vigente" (idealmente el abierto)
		try:
			credito_actual = (Credito.objects
							  .select_related('ingreso', 'liquidacion')
							  .get(factura=factura, socio=socio, fin__isnull=True))
		except ObjectDoesNotExist:
			# fallback al único si no hay abierto
			try:
				credito_actual = Credito.objects.get(factura=factura, socio=socio)
			except ObjectDoesNotExist:
				rows = self._rows_from_post(request.POST)
				pairs = list(zip(formset.forms, rows))
				messages.error(request, "No encontré el crédito asociado a esa factura.")
				ctx = {'form': form, 'formset': formset, 'pairs': pairs, 'step': '2', 'socio': socio, 'factura': factura}
				return render(request, self.template_renglones, ctx)

		devoluciones = []
		total_nc = Q00

		for f in formset:
			cd = f.cleaned_data or {}
			devolver = cd.get('devolver') or Q00
			if devolver <= 0:
				continue

			vp_id = cd['vp_id']
			motivo = cd.get('motivo') or ''
			vp_orig = (Venta_Producto.objects
					   .select_related('producto', 'credito', 'liquidacion', 'socio')
					   .get(id=vp_id))

			# Validar disponibilidad (si tu modelo lo tiene)
			disp = getattr(vp_orig, 'disponible_para_devolver', None)
			if disp is not None and Decimal(devolver) > Decimal(disp):
				rows = self._rows_from_post(request.POST)
				pairs = list(zip(formset.forms, rows))
				messages.error(request, f"No se puede devolver más de lo disponible para {vp_orig.producto}.")
				ctx = {'form': form, 'formset': formset, 'pairs': pairs, 'step': '2', 'socio': socio, 'factura': factura}
				return render(request, self.template_renglones, ctx)

			# Depósito original (primer movimiento)
			orig_ms = (MovimientoStock.objects
					   .filter(venta_producto=vp_orig)
					   .order_by('id')
					   .first())
			if not orig_ms or not getattr(orig_ms, 'deposito_id', None):
				rows = self._rows_from_post(request.POST)
				pairs = list(zip(formset.forms, rows))
				messages.error(request, f"No pude determinar el depósito de origen para {vp_orig.producto}.")
				ctx = {'form': form, 'formset': formset, 'pairs': pairs, 'step': '2', 'socio': socio, 'factura': factura}
				return render(request, self.template_renglones, ctx)

			precio = q2(Decimal(vp_orig.precio or 0))
			subtotal = q2(precio * Decimal(devolver))
			total_nc = q2(total_nc + subtotal)

			devoluciones.append({
				'vp_orig': vp_orig,
				'cant_dev': Decimal(devolver),
				'precio': precio,
				'subtotal': subtotal,
				'motivo': motivo or "Devolución",
				'deposito': orig_ms.deposito,
			})

		if total_nc <= 0:
			rows = self._rows_from_post(request.POST)
			pairs = list(zip(formset.forms, rows))
			messages.error(request, "No ingresaste cantidades a devolver.")
			ctx = {'form': form, 'formset': formset, 'pairs': pairs, 'step': '2', 'socio': socio, 'factura': factura}
			return render(request, self.template_renglones, ctx)

		ingreso_prov = Ingreso.objects.get(consorcio=cons, es_proveeduria=True)

		from collections import defaultdict

		with transaction.atomic():
			# 1) Receipt NC RG 1415 (no fiscal) -> code "105"
			rtype = ReceiptType.objects.get(code="105")
			receipt_nc = Receipt.objects.create(
				point_of_sales=factura.receipt.point_of_sales,
				receipt_type=rtype,
				concept=ConceptType.objects.get(code=1),  # Bienes
				document_type=socio.tipo_documento,
				document_number=socio.numero_documento,
				issued_date=hoy,
				total_amount=total_nc,
				net_untaxed=0,
				net_taxed=total_nc,
				exempt_amount=0,
				service_start=hoy,
				service_end=hoy,
				expiration_date=hoy,
				currency=CurrencyType.objects.get(code="PES"),
			)
			last = (Receipt.objects
					.filter(receipt_type=rtype, point_of_sales=receipt_nc.point_of_sales)
					.aggregate(Max('receipt_number'))['receipt_number__max'] or 0)
			receipt_nc.receipt_number = last + 1
			receipt_nc.save()

			# 2) Comprobante NC que referencia el receipt
			comp = Comprobante.objects.create(
				consorcio=cons,
				socio=socio,
				fecha=hoy,
				total=total_nc,
				nota_credito=receipt_nc,
				descripcion=(
					"NC Proveeduría por devolución de mercadería sobre "
					f"Factura {factura.receipt.point_of_sales}-{factura.receipt.receipt_number}"
				),
			)

			# 3) Renglones NC (es_nc=True) + stock de retorno + preparamos líneas para PDF
			lineas_pdf = []

			# --- NUEVO: agregador por crédito ---
			por_credito = defaultdict(lambda: q2(Q00))

		def _credito_destino(cred):
			"""
			Dado un crédito (posiblemente ya cerrado) devuelve el crédito ABIERTO
			vigente dentro de la misma cadena (root = padre o el mismo).
			Si no hay abierto, devuelve el root si está abierto; si no, None.
			"""
			root = cred.padre or cred
			# Preferimos un hijo abierto
			abierto = (Credito.objects
					.filter(Q(padre=root) | Q(id=root.id), fin__isnull=True)
					.order_by('-fecha', '-id')
					.first())
			return abierto  # puede ser None si todo está cerrado

		# --- NUEVO: agregador por crédito DESTINO (vigente) ---
		por_credito = defaultdict(lambda: q2(Q00))
		lineas_pdf = []

		for d in devoluciones:
			vp_orig = d['vp_orig']
			cred_dest = _credito_destino(vp_orig.credito)  # << clave del fix

			if cred_dest is None:
				# Si no hay abierto en la cadena, por consistencia usamos el root
				# (pero casi siempre vas a tener el de $40.000 abierto)
				cred_dest = (vp_orig.credito.padre or vp_orig.credito)

			# Crear el renglón de NC apuntando al crédito DESTINO (no al original)
			vp_nc = Venta_Producto.objects.create(
				consorcio=cons,
				sucursal=vp_orig.sucursal,
				producto=vp_orig.producto,
				precio=d['precio'],
				cantidad=d['cant_dev'],
				credito=cred_dest,                 # << aquí el cambio importante
				liquidacion=vp_orig.liquidacion,
				socio=vp_orig.socio,
				costo=vp_orig.costo or Q00,
				padre=vp_orig,
				es_nc=True,
				motivo_nc=d['motivo'],
				comprobante_nc=comp,
			)

			mover_stock_por_producto(
				producto=vp_orig.producto,
				deposito=d['deposito'],
				fecha=hoy,
				cantidad_signed=Decimal(d['cant_dev']),
				venta_producto=vp_nc
			)

			lineas_pdf.append({
				'producto': vp_orig.producto.nombre,
				'cantidad': d['cant_dev'],
				'precio': d['precio'],
				'subtotal': d['subtotal'],
				'motivo': d['motivo'],
			})

			# Acumular por el crédito DESTINO (vigente)
			por_credito[cred_dest] = q2(por_credito[cred_dest] + d['subtotal'])

		# 4) Cobros por crédito + cierre y recreación de remanentes por crédito
		ingreso_prov = Ingreso.objects.get(consorcio=cons, es_proveeduria=True)
		nuevos_creditos = []
		cerrados = 0

		for cred_dest, subtotal_cred in por_credito.items():
			# Cobro correcto para ESTE crédito vigente
			Cobro.objects.create(
				consorcio=cons,
				socio=socio,
				fecha=hoy,
				credito=cred_dest,
				subtotal=subtotal_cred,
				int_desc=Q00,
				comprobante=comp
			)

			capital_original = q2(Decimal(cred_dest.capital or 0))
			remanente = q2(capital_original - subtotal_cred)

			# Cerrar SIEMPRE el crédito destino (era el abierto de la cadena)
			if cred_dest.fin is None:
				cred_dest.fin = hoy
				cred_dest.save(update_fields=['fin'])
				cerrados += 1

			# Si quedó saldo, reabrimos un crédito nuevo por el remanente
			if remanente > 0:
				root = cred_dest.padre or cred_dest  # mantener la cadena consistente
				nuevo = Credito.objects.create(
					consorcio=cons,
					socio=socio,
					factura=factura,
					liquidacion=cred_dest.liquidacion,
					fecha=hoy,
					detalle='Proveeduría (remanente tras NC)',
					periodo=getattr(cred_dest, 'periodo', hoy),
					ingreso=ingreso_prov,
					capital=remanente,
					padre=root,  # encadenamos al root de la serie
				)
				nuevos_creditos.append(nuevo)

		# 5) PDF
		comp._lineas_nc = lineas_pdf
		comp.hacer_pdfs_inst()



		messages.success(
			request,
			f"Nota de Crédito emitida por ${total_nc}."
			+ ("" if remanente == 0 else f" Crédito original cerrado y creado nuevo por ${remanente}.")
		)
		return redirect('facturacion-proveeduria')



class _NoFilter:
	def __init__(self, qs):
		self.qs = qs  # para que OrderQS pueda hacer self.filter.qs

@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class ModuloListView(OrderQS):
	model = Producto
	template_name = 'modulos/index.html'
	paginate_by = 50

	def get(self, request, *args, **kwargs):
		c = consorcio(request)
		datos = Producto.objects.filter(consorcio=c, es_modulo=True).order_by('nombre')

		# filtro “dummy” para satisfacer OrderQS
		self.filter = _NoFilter(datos)

		self.object_list = self.order_queryset(self.filter.qs) if hasattr(self, 'order_queryset') else datos
		context = self.get_context_data(object_list=self.object_list)
		return self.render_to_response(context)



@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class ModuloCreateView(generic.View):
	template_name = 'modulos/form.html'

	def get(self, request):
		form = ModuloForm(request=request)
		formset = ModuloComponenteFormSet(
			instance=Producto(consorcio=consorcio(request), es_modulo=True),
			form_kwargs={'request': request}
		)
		return render(request, self.template_name, {
			'form': form,
			'formset': formset,
			'titulo': 'Nuevo módulo'
		})

	@transaction.atomic
	def post(self, request):
		form = ModuloForm(request.POST, request=request)

		# objeto "en memoria" para enganchar el formset
		modulo = Producto(consorcio=consorcio(request), es_modulo=True)
		formset = ModuloComponenteFormSet(
			request.POST,
			instance=modulo,
			form_kwargs={'request': request}
		)

		if form.is_valid() and formset.is_valid():
			# 1. guardamos el módulo base
			modulo.nombre = form.cleaned_data['nombre']
			modulo.descripcion = form.cleaned_data.get('descripcion')
			modulo.precio_1 = form.cleaned_data.get('precio') or None
			modulo.activo = form.cleaned_data.get('activo', True)
			modulo.es_modulo = True
			modulo.consorcio = consorcio(request)
			modulo.save()

			# 2. validaciones app sobre el formset
			comps = []
			for f in formset:
				if f.cleaned_data and not f.cleaned_data.get('DELETE', False):
					comp = f.cleaned_data['componente']
					if comp.id == modulo.id:
						messages.error(request, "El módulo no puede ser componente de sí mismo.")
						transaction.set_rollback(True)
						return render(request, self.template_name, {
							'form': form,
							'formset': formset,
							'titulo': 'Nuevo módulo'
						})
					comps.append((comp.id, f.cleaned_data['cantidad']))

			vistos = set()
			for comp_id, _ in comps:
				if comp_id in vistos:
					messages.error(request, "Hay componentes repetidos.")
					transaction.set_rollback(True)
					return render(request, self.template_name, {
						'form': form,
						'formset': formset,
						'titulo': 'Nuevo módulo'
					})
				vistos.add(comp_id)

			# 3. grabamos las líneas del formset ahora que modulo ya tiene pk
			formset.instance = modulo
			formset.save()

			# 4. AHORA que ya existen los ModuloComponente -> calculamos costo y actualizamos
			modulo.recalcular_costo_modulo()
			modulo.save(update_fields=['costo'])

			messages.success(request, "Módulo creado correctamente.")
			return redirect('modulos-index')

		return render(request, self.template_name, {
			'form': form,
			'formset': formset,
			'titulo': 'Nuevo módulo'
		})



@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class ModuloUpdateView(generic.View):
	template_name = 'modulos/form.html'

	def get_object(self):
		c = consorcio(self.request)
		return get_object_or_404(Producto, pk=self.kwargs['pk'], consorcio=c, es_modulo=True)

	def get(self, request, pk):
		modulo = self.get_object()
		form = ModuloForm(instance=modulo, request=request)
		formset = ModuloComponenteFormSet(instance=modulo, form_kwargs={'request': request})
		return render(request, self.template_name, {
			'form': form,
			'formset': formset,
			'titulo': f'Editar módulo: {modulo.nombre}'
		})

	@transaction.atomic
	def post(self, request, pk):
		modulo = self.get_object()
		form = ModuloForm(request.POST, instance=modulo, request=request)
		formset = ModuloComponenteFormSet(request.POST, instance=modulo, form_kwargs={'request': request})

		if form.is_valid() and formset.is_valid():
			# 1. guardo cambios básicos del módulo
			modulo = form.save(commit=False)
			modulo.es_modulo = True
			modulo.consorcio = consorcio(request)
			modulo.precio_1 = form.cleaned_data.get('precio') or None
			modulo.save()

			# 2. validaciones app igual que antes
			comps = []
			for f in formset:
				if f.cleaned_data and not f.cleaned_data.get('DELETE', False):
					comp = f.cleaned_data['componente']
					if comp.id == modulo.id:
						messages.error(request, "El módulo no puede ser componente de sí mismo.")
						transaction.set_rollback(True)
						return render(request, self.template_name, {
							'form': form,
							'formset': formset,
							'titulo': f'Editar módulo: {modulo.nombre}'
						})
					comps.append((comp.id, f.cleaned_data['cantidad']))

			vistos = set()
			for comp_id, _ in comps:
				if comp_id in vistos:
					messages.error(request, "Hay componentes repetidos.")
					transaction.set_rollback(True)
					return render(request, self.template_name, {
						'form': form,
						'formset': formset,
						'titulo': f'Editar módulo: {modulo.nombre}'
					})
				vistos.add(comp_id)

			# 3. guardo el formset (esto crea/actualiza/elimina ModuloComponente)
			formset.save()

			# 4. recalculo costo según nuevos componentes
			modulo.recalcular_costo_modulo()
			modulo.save(update_fields=['costo'])

			messages.success(request, "Módulo actualizado correctamente.")
			return redirect('modulos-index')

		return render(request, self.template_name, {
			'form': form,
			'formset': formset,
			'titulo': f'Editar módulo: {modulo.nombre}'
		})
