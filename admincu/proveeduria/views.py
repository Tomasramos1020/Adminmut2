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
from arquitectura.models import Gasto, Acreedor
from decimal import Decimal
# views.py
from django.views.generic import ListView
from .filters import RemitoFilter
from admincu.generic import OrderQS
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404
from django.http import HttpResponse




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
			objetos = Producto.objects.filter(consorcio=consorcio(self.request), nombre__isnull=False)
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
		formset.form.base_fields['producto'].queryset = Producto.objects.filter(consorcio=cons)

		return render(request, self.template_name, {'form': form, 'formset': formset})

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
			for linea in formset:
				if linea.cleaned_data and not linea.cleaned_data.get('DELETE', False):
					precio = linea.cleaned_data.get('precio') or Decimal('0')
					cantidad = linea.cleaned_data.get('cantidad') or Decimal('0')
					capital += precio * cantidad

			# Crear liquidación
			liquidacion = Liquidacion.objects.create(
				consorcio=cons,
				punto=punto,
				capital=capital, 
				fecha=fecha,
				estado='confirmado'
			)

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

					vp.save()

					# Registrar movimiento de stock (salida)
					ms = MovimientoStock.objects.create(
						venta_producto = vp,
						producto= vp.producto,
						deposito= deposito,
						cantidad= -vp.cantidad,
						fecha = fecha,
					)

			factura.validar_factura()

			liquidacion.hacer_asiento()

			return redirect('facturacion-proveeduria')

		return render(request, self.template_name, {'form': form, 'formset': formset})



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
		if costo is None:
			costo = getattr(p, 'costo', 0)
		return JsonResponse({'precio_1': float(precio), 'costo': float(costo or 0)})
	except Producto.DoesNotExist:
		return JsonResponse({'precio_1': 0, 'costo': 0})


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
		return render(request, self.template_name, {'form': form, 'formset': formset})

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

			total = Decimal('0.00')
			for linea in formset:
				if linea.cleaned_data:
					precio = linea.cleaned_data.get('precio') or 0
					cantidad = linea.cleaned_data.get('cantidad') or 0
					total += precio * cantidad

			deuda = Deuda.objects.create(
				consorcio=cons,
				acreedor=acreedor,
				fecha=fecha,
				numero=numero_fmt,     # <<— sólo este campo del modelo
				total=total,
				observacion=observacion,
				confirmado=True
			)

			gasto_default = Gasto.objects.filter(consorcio=cons, es_proveeduria=True).first()
			if not gasto_default:
				messages.error(request, "No hay gastos de proveeduría configurados.")
				raise Exception("Gasto faltante")

			for linea in formset:
				if linea.cleaned_data:
					compra = linea.save(commit=False)
					compra.consorcio = cons
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

			asiento = asiento_deuda(deuda)
			messages.success(request, "Compra y deuda creadas correctamente.")
			return redirect('deudas')

		return render(request, self.template_name, {'form': form, 'formset': formset})

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
				MovimientoStock.objects.create(
					producto = item.producto,
					deposito = deposito,
					fecha    = fecha,
					cantidad = item.cantidad_salida,  # NEGATIVO
					remito_item = item
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
