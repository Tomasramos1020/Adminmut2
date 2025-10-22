from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import transaction
from django.utils.decorators import method_decorator


from admincu.funciones import *
from admincu.generic import OrderQS
from consorcios.models import *
from arquitectura.models import *
from .models import *
from .forms import *
from contabilidad.asientos.funciones import asiento_deuda
from .funciones import *
from .filters import *
from proveeduria.models import MovimientoStock
from django.views import View



@group_required('administrativo', 'contable', 'sin_op')
def deud_index(request):
	hoy = date.today()

	deudas = Deuda.objects.filter(consorcio=consorcio(request), confirmado=True, aceptado=True).order_by('-id')

	# Saldo total de creditos pendientes
	saldo = sum([d.saldo for d in deudas.filter(pagado=False)])

	borrar_deudas_no_confirmadas(request.user)

	deudas = deudas[:5]

	return render(request, 'deudas/index.html', locals())


@method_decorator(group_required('administrativo', 'contable', 'sin_op'), name='dispatch')
class Registro(OrderQS):

	""" Registro de deudas """

	model = Deuda
	filterset_class = DeudaFilter
	template_name = 'deudas/registros/deudas.html'
	paginate_by = 50



@group_required('administrativo', 'contable', 'sin_op')
def deud_registro(request):

	deudas = Deuda.objects.filter(consorcio=consorcio(request), confirmado=True).order_by('-id')

	borrar_deudas_no_confirmadas(request.user)

	if request.POST.get('fechas'):
		rango = request.POST.get('fechas').split(" / ")
		deudas = deudas.filter(fecha__range=rango)
	else:
		deudas = deudas[:20]

	return render(request, 'deudas/registro.html', locals())


@group_required('administrativo', 'sin_op')
def deud_nuevo(request):
	if valid_demo(request.user):
		return redirect('deudas')
	request.session['fecha'] = None
	request.session['numero'] = None
	request.session['acreedor'] = None

	borrar_deudas_no_confirmadas(request.user)

	form = encabezadoDeudaForm(
			data=request.POST or None,
			consorcio=consorcio(request),
		)
	pregunta = "Seleccione las siguientes opciones"
	if form.is_valid():
		# Validacion para no cargar con fecha de periodos cerrados
		fecha = form.cleaned_data['fecha']
		try:
			ultimo_cierre = Cierre.objects.filter(consorcio=consorcio(request), confirmado=True).order_by('-periodo')[0].periodo
		except:
			ultimo_cierre = None

		if ultimo_cierre and fecha <= ultimo_cierre:
			messages.add_message(request, messages.ERROR, 'No se puede generar deudas con fecha anterior a la de periodos cerrados.')
		else:
			request.session['fecha'] = request.POST.get('fecha')
			request.session['numero'] = request.POST.get('numero')
			request.session['acreedor'] = request.POST.get('acreedor')
			try:
				deuda_existente = Deuda.objects.get(
						numero=request.session['numero'],
						acreedor=Acreedor.objects.get(id=request.session['acreedor'])
					)
				messages.add_message(request, messages.ERROR, 'La deuda que desea cargar ya existe')
			except:
				deuda_existente = None
			if not deuda_existente:
				return redirect(deud_vinculaciones)
	else:
		messages.add_message(request, messages.ERROR, 'Debes rellenar todos los campos para poder continuar') if request.method == "POST" else None


	return render(request, 'deudas/nuevo.html', locals())


@group_required('administrativo', 'sin_op')
@transaction.atomic
def deud_vinculaciones(request):
	try:
		acreedor = Acreedor.objects.get(id=request.session['acreedor'])
		fecha = request.session['fecha']
		numero = request.session['numero']
	except:
		return redirect(deud_index)

	form = detallesDeudaForm(
			consorcio=consorcio(request),
			data=request.POST or None
			)

	erogaciones_posibles = acreedor.tipo.exclude(cuenta_contable=acreedor.cuenta_contable)

	if request.method == "POST":
		errores = []
		gastos = [
		{
			"nombre": gasto.split("_")[1],
			"valor": float(valor)
		} for gasto, valor in request.POST.items() if "gasto_" in gasto and valor != 0 and valor != ""
		]
		errores.append("Debes cargar valores en los gastos vinculados al acreedor") if not gastos else None

		if not errores:
			observacion = request.POST.get('observacion') or None
			total = sum([val for gasto in gastos for g,val in gasto.items() if g == "valor"])
			# Creacion de la deuda
			deuda = Deuda(
				consorcio=consorcio(request),
				fecha=fecha,
				numero=numero,
				acreedor=acreedor,
				total=total,
				observacion=observacion,
				)
			deuda.save()

			# Creacion de objeto de gastos
			listado_gastos = []
			for gasto in gastos:
				gastoDeuda = GastoDeuda(
					deuda=deuda,
					gasto=Gasto.objects.get(id=gasto['nombre']),
					valor=gasto["valor"],
					)
				listado_gastos.append(gastoDeuda)

			# Guardado de gastos en base de datos
			try:
				guardar_gastos = GastoDeuda.objects.bulk_create(listado_gastos)
			except:
				deuda.delete()
				messages.add_message(request, messages.ERROR, 'Hubo un error, debe realizar el proceso de generacion de la deuda')
				return redirect(deud_index)

			return redirect(deud_confirm, pk=deuda.pk)


	return render(request, 'deudas/vinculaciones.html', locals())


@group_required('administrativo', 'sin_op')
@transaction.atomic
def deud_confirm(request, pk):
	try:
		deuda = Deuda.objects.get(
				consorcio=consorcio(request),
				pk=pk,
				confirmado=False
				)
	except:
		messages.add_message(request, messages.ERROR, 'Hubo un error, debe realizar el proceso de generacion de deuda')
		return redirect(deud_index)

	gastoDeuda = GastoDeuda.objects.filter(deuda=deuda)

	if request.method == "POST":
		if request.POST.get('accion') =='confirm':
			deuda.confirmado = True
			gastoDeuda.update(fecha=deuda.fecha)
			deuda.save()
			try:
				asiento = asiento_deuda(deuda)
			except:
				asiento = None

			if asiento == True:
				messages.add_message(request, messages.SUCCESS, "Deuda generada con exito.")
			else:
				messages.add_message(request, messages.ERROR, asiento)

			return redirect(deud_index)

	return render(request, 'deudas/confirmacion.html', locals())


@group_required('administrativo', 'sin_op')
@transaction.atomic
def deud_eliminar(request, pk):
	try:
		deuda = Deuda.objects.get(
				consorcio=consorcio(request),
				pk=pk,
				confirmado=False
				)
	except:
		messages.add_message(request, messages.ERROR, 'Hubo un error al cancelar el proceso de generacion de deuda')
		return redirect(deud_index)

	gastoDeuda = GastoDeuda.objects.filter(deuda=deuda).delete()
	deuda.delete()
	messages.add_message(request, messages.SUCCESS, "Deuda cancelada.")
	return redirect(deud_index)

@group_required('administrativo', 'sin_op')
@transaction.atomic
def eliminar_deuda(request, pk):
	try:
		deuda = Deuda.objects.get(
				consorcio=consorcio(request),
				pk=pk,
				)
	except:
		messages.add_message(request, messages.ERROR, 'Hubo un error al cancelar el proceso de generacion de deuda')
		return redirect(deud_index)

	mj=(deuda.eliminacion())
	messages.add_message(request, messages.SUCCESS, mj)
	return redirect(deud_index)




@group_required('administrativo', 'contable', 'sin_op')
def deud_ver(request, pk):
	try:
		deuda = Deuda.objects.get(
				pk=pk,
				consorcio=consorcio(request),
				confirmado=True,
				)
	except:
		messages.add_message(request, messages.ERROR, 'Hubo un error, debe seleccionar opciones validas en el menu')
		return redirect(deud_index)

	gastoDeuda = GastoDeuda.objects.filter(deuda=deuda)

	return render(request, 'deudas/ver.html', locals())


@group_required('administrativo', 'contable', 'sin_op')
@transaction.atomic
def deud_vincular_pago(request, pk):
	try:
		deuda = Deuda.objects.get(
				pk=pk,
				consorcio=consorcio(request),
				confirmado=True,
				)
	except:
		messages.add_message(request, messages.ERROR, 'Hubo un error, debe seleccionar opciones validas en el menu')
		return redirect(deud_index)

	adelantos = GastoOP.objects.filter(
				op__acreedor=deuda.acreedor,
				gasto__cuenta_contable=deuda.acreedor.cuenta_contable
			)
	for a in adelantos:
		if a.op.deudaop_set.filter(deuda=deuda):
			adelantos = adelantos.exclude(id=a.id)

	if not adelantos:
		messages.add_message(request, messages.ERROR, 'No hay pagos posibles a vincular.')
		return redirect('deud_ver', pk=deuda.pk)

	if request.method == "POST":
		seleccionados = adelantos.filter(id__in=request.POST.getlist('pagos'))
		suma_seleccionados = sum([a.valor for a in seleccionados])
		errores = []
		if suma_seleccionados > deuda.saldo:
			errores.append('El total de pagos seleccionados excede al saldo de la deuda.')
		if not errores:
			vinculaciones = []
			for s in seleccionados:
				vinculaciones.append(
						DeudaOP(
							op=s.op,
							deuda=deuda,
							valor=s.valor
						)
					)
				s.delete()
			guardar_vinculaciones = DeudaOP.objects.bulk_create(vinculaciones)
			deuda.chequear()
			messages.add_message(request, messages.SUCCESS, 'Pagos vinculados con exito.')
			return redirect('deud_ver', pk=deuda.pk)

	return render(request, 'deudas/vincular-pago.html', locals())

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.http import JsonResponse
# Utils cortos
def decimal2(x):
    if x is None or x == "":
        return Decimal('0.00')
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))

def deuda_es_proveeduria(deuda: Deuda) -> bool:
    # Si la deuda tiene AL MENOS un gasto marcado como es_proveeduria=True, tratamos la NC como de mercadería.
    return GastoDeuda.objects.filter(deuda=deuda, gasto__es_proveeduria=True).exists()

@require_GET
@login_required
def deudas_por_acreedor(request):
    cons = consorcio(request)
    acreedor_id = request.GET.get('acreedor')
    data = []
    if acreedor_id:
        qs = (Deuda.objects
              .filter(consorcio=cons, acreedor_id=acreedor_id, confirmado=True, pagado=False, anulado__isnull=True)
              .order_by('-fecha', '-id'))
        for d in qs:
            data.append({
                "id": d.id,
                "texto": f"{d.numero or d.id} - {d.fecha} - Total: {d.total} - Saldo: {d.saldo}",
            })
    return JsonResponse({"items": data})

@require_GET
@login_required
def deuda_es_proveeduria_ajax(request):
    deuda_id = request.GET.get('deuda')
    es_prov = False
    if deuda_id:
        try:
            d = Deuda.objects.get(pk=deuda_id, consorcio=consorcio(request))
            es_prov = deuda_es_proveeduria(d)
        except Deuda.DoesNotExist:
            pass
    return JsonResponse({"es_proveeduria": es_prov})

def _cap_monto_nc(deuda: Deuda, monto_nc: Decimal) -> Decimal:
    """
    Evita dejar la deuda con saldo negativo:
    new_total >= total_pagos_confirmados
    """
    pagos_conf = sum([p.valor for p in deuda.deudaop_set.filter(op__confirmado=True)])
    total_actual = deuda.total or Decimal('0.00')
    monto_nc = decimal2(monto_nc)
    # nuevo total no puede ser menor a los pagos ya hechos
    min_total_permitido = decimal2(pagos_conf)
    new_total = total_actual - monto_nc
    if new_total < min_total_permitido:
        # Capamos la NC para que new_total == pagos_conf
        return (total_actual - min_total_permitido).quantize(Decimal('0.01'))
    return monto_nc.quantize(Decimal('0.01'))


@transaction.atomic
def aplicar_nc_a_deuda(*, deuda: Deuda, nc: NotaCreditoProveedor) -> Decimal:
    """
    Aplica el efecto contable/stock de la Nota de Crédito:
    - Baja Deuda.total hasta el máximo permitido (no menor a pagos ya hechos).
    - Si es de proveeduría: genera MovimientoStock negativo por línea y (opcional) un GastoDeuda negativo de auditoría.
    - Si NO es de proveeduría: opcionalmente registra un GastoDeuda negativo genérico (si querés historial), pero lo principal es bajar 'total'.
    """
    total_nc = decimal2(nc.total)
    if total_nc <= 0:
        return Decimal('0.00')
    
    aplicado = Decimal('0.00')

    # 1) Stock (si corresponde)
    if nc.es_proveeduria:
        if not nc.deposito:
            raise ValueError("La NC de proveeduría requiere un depósito.")
        for lp in nc.lineas_productos.all():
            MovimientoStock.objects.create(
                producto=lp.producto,
                deposito=nc.deposito,
                fecha=nc.fecha,
                cantidad=decimal2(-lp.cantidad),  # ENTRA negativo
                compra_producto=None,  # sin referencia específica
            )

    # 2) Bajar el total de la deuda (capado por pagos)
    total_nc_capado = _cap_monto_nc(deuda, total_nc)
    if total_nc_capado <= 0:
        # Ya no hay saldo suficiente para aplicar; nada que hacer
        deuda.chequear()
        return Decimal('0.00')

    deuda.total = (decimal2(deuda.total) - total_nc_capado).quantize(Decimal('0.01'))
    deuda.save()
    deuda.chequear()
    aplicado = total_nc_capado

    # 3) (Opcional) rastro en GastoDeuda negativo para auditoría
    try:
        # Tomamos un gasto "representativo":
        #   - si es_proveeduría: buscar uno es_proveeduría=True (como el que se usó en la compra)
        #   - si no: tomamos el primer gasto de la deuda o alguno “NC Proveedor” si lo tenés parametrizado
        if nc.es_proveeduria:
            gasto_ref = (GastoDeuda.objects
                         .filter(deuda=deuda, gasto__es_proveeduria=True)
                         .values_list('gasto', flat=True).first())
        else:
            gasto_ref = (GastoDeuda.objects
                         .filter(deuda=deuda)
                         .values_list('gasto', flat=True).first())

        if gasto_ref:
            GastoDeuda.objects.create(
                fecha=nc.fecha,
                deuda=deuda,
                gasto=Gasto.objects.get(pk=gasto_ref),
                valor=decimal2(-aplicado)
            )
    except Exception:
        # Si no existe gasto apto, no frenamos el flujo: la baja de total ya quedó aplicada.
        pass
    if hasattr(nc, 'total_aplicado'):
        nc.total_aplicado = aplicado
        nc.save(update_fields=['total_aplicado'])
    
    return aplicado

    
# admincu/op/views_nc_proveedor.py (o utils.py donde prefieras)
from django.db.models import Sum
from collections import defaultdict
from .models import NotaCreditoLineaProducto
from proveeduria.models import Compra_Producto

def disponibles_por_producto_en_deuda(deuda):
    """
    Devuelve dict {producto_id: cantidad_disponible} para esa deuda.
    disponible = sum(compra.cantidad) - sum(nc_lineas.cantidad)
    """
    comprados = (
        Compra_Producto.objects
        .filter(deuda=deuda)
        .values('producto_id')
        .annotate(q=Sum('cantidad'))
    )
    devueltos = (
        NotaCreditoLineaProducto.objects
        .filter(nc__deuda=deuda)
        .values('producto_id')
        .annotate(q=Sum('cantidad'))
    )

    map_comp = {r['producto_id']: (r['q'] or 0) for r in comprados}
    map_dev = {r['producto_id']: (r['q'] or 0) for r in devueltos}

    disponibles = {}
    for pid, q in map_comp.items():
        disponibles[pid] = max(0, (q or 0) - (map_dev.get(pid, 0) or 0))
    return disponibles

# admincu/op/views_nc_proveedor.py
@require_GET
@login_required
def disponible_producto_nc_ajax(request):
    deuda_id = request.GET.get('deuda')
    prod_id = request.GET.get('producto')
    disp = 0
    try:
        d = Deuda.objects.get(pk=deuda_id, consorcio=consorcio(request))
        mapa = disponibles_por_producto_en_deuda(d)
        disp = mapa.get(int(prod_id), 0)
    except Exception:
        pass
    return JsonResponse({"disponible": float(disp)})

# views_nc_proveedor.py
from django.db.models import Sum, OuterRef, Subquery, Value, DecimalField

@require_GET
@login_required
def nc_lineas_deuda_ajax(request):
    cons = consorcio(request)
    deuda_id = request.GET.get('deuda')
    try:
        d = Deuda.objects.get(pk=deuda_id, consorcio=cons)
    except Deuda.DoesNotExist:
        return JsonResponse({"items": []})

    # último precio usado por producto dentro de esa deuda
    ult_precio_sq = (Compra_Producto.objects
        .filter(deuda=d, producto_id=OuterRef('producto_id'))
        .order_by('-id').values('precio')[:1])

    compras = (Compra_Producto.objects
        .filter(deuda=d)
        .values('producto_id', 'producto__nombre')
        .annotate(comprado=Sum('cantidad'),
                  precio=Subquery(ult_precio_sq)))

    devueltos = (NotaCreditoLineaProducto.objects
        .filter(nc__deuda=d)
        .values('producto_id')
        .annotate(q=Sum('cantidad')))
    map_dev = {r['producto_id']: (r['q'] or 0) for r in devueltos}

    items = []
    for r in compras:
        disp = (r['comprado'] or 0) - (map_dev.get(r['producto_id'], 0) or 0)
        if disp > 0:
            items.append({
                "producto_id": r['producto_id'],
                "producto": r['producto__nombre'],
                "disponible": float(disp),
                "precio": float(r['precio'] or 0),
            })
    return JsonResponse({"items": items})

def asiento_nc_proveedor(nc: NotaCreditoProveedor, aplicado: Decimal):
    if aplicado is None or aplicado <= 0:
        return True  # nada que asentar

    identificacion = randomNumber(Operacion, 'numero_aleatorio')
    ops = []

    # 1) Debe Proveedores (baja el pasivo frente al acreedor)
    ops.append(
        Operacion(
            numero_aleatorio=identificacion,
            cuenta=nc.acreedor.cuenta_contable,
            debe=aplicado,
            haber=0,
            descripcion=f"NC a {nc.acreedor} - Deuda {getattr(nc.deuda, 'numero', nc.deuda_id)}"
        )
    )

    # 2) Haber contra gasto/mercadería
    # Elegimos una cuenta "representativa" según el tipo de NC:
    gasto_ref = None
    if nc.es_proveeduria:
        # buscamos un gasto que esté marcado como es_proveeduria=True en la deuda
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
        # Fallback (podés parametrizar una cuenta "Ajuste NC Proveedor")
        raise ValueError("No se encontró un gasto de referencia para armar el asiento de la NC.")

    cuenta_contra = gasto_ref.gasto.cuenta_contable

    ops.append(
        Operacion(
            numero_aleatorio=identificacion,
            cuenta=cuenta_contra,
            debe=0,
            haber=aplicado,
            descripcion=f"NC a {nc.acreedor} - Reverso gasto/mercadería"
        )
    )

    asiento = Asiento(
        consorcio=nc.consorcio,
        fecha_asiento=nc.fecha,
        descripcion=f"NC Proveedor {nc.acreedor} - Deuda {getattr(nc.deuda, 'numero', nc.deuda_id)}",
    )

    try:
        with transaction.atomic():
            Operacion.objects.bulk_create(ops)
            asiento.save()
            asiento.operaciones.add(*Operacion.objects.filter(numero_aleatorio=identificacion))
            # Si tu modelo NotaCreditoProveedor tiene FK a Asiento, guardalo:
            if hasattr(nc, 'asiento'):
                nc.asiento = asiento
                nc.save(update_fields=['asiento'])
        return True
    except Exception as e:
        return f"Error creando asiento NC Proveedor: {e}"


class NCProveedorView(View):
    template_name = 'nc/crear_nc_proveedor.html'

    def get(self, request):
        inicial = NCProveedorInicialForm(request=request)
        # en GET todavía no sabemos la deuda -> no filtramos por disponibilidad
        prod_fs  = NCProductoFS(prefix='p', form_kwargs={'request': request})
        return render(request, self.template_name, {'inicial': inicial, 'prod_fs': prod_fs})

    @transaction.atomic
    def post(self, request):
        # 1) validar encabezado primero
        inicial = NCProveedorInicialForm(request.POST, request=request)
        if not inicial.is_valid():
            prod_fs = NCProductoFS(request.POST, prefix='p', form_kwargs={'request': request})
            messages.error(request, "Revisá los datos del encabezado.")
            return render(request, self.template_name, {'inicial': inicial, 'prod_fs': prod_fs})

        c = consorcio(request)
        acreedor = inicial.cleaned_data['acreedor']
        deuda = inicial.cleaned_data['deuda']
        fecha = inicial.cleaned_data['fecha']
        observacion = inicial.cleaned_data.get('observacion') or ''
        deposito = inicial.cleaned_data.get('deposito')

        # ahora instancias el formset con la deuda (para filtrar productos por disponibilidad)
        prod_fs  = NCProductoFS(
            request.POST, prefix='p',
            form_kwargs={'request': request, 'deuda': deuda}
        )

        # 2) decidir camino
        es_prov = deuda_es_proveeduria(deuda)
        total = Decimal('0.00')
        lineas_p = []

        if es_prov:
            # validar formset
            if not prod_fs.is_valid():
                messages.error(request, "Completá correctamente las líneas de productos.")
                return render(request, self.template_name, {'inicial': inicial, 'prod_fs': prod_fs})
            if not deposito:
                messages.error(request, "Debés seleccionar un depósito para ajustar stock.")
                return render(request, self.template_name, {'inicial': inicial, 'prod_fs': prod_fs})

            # disponibilidad por producto (compra - NC previas)
            mapa_disp = disponibles_por_producto_en_deuda(deuda)  # {producto_id: qty}

            for f in prod_fs:
                cd = getattr(f, 'cleaned_data', {}) or {}
                if cd and not cd.get('DELETE'):
                    prod = cd['producto']
                    precio = decimal2(cd.get('precio'))
                    cantidad = decimal2(cd.get('cantidad'))

                    if cantidad <= 0 or precio < 0:
                        messages.error(request, "Cantidad > 0 y precio >= 0 en todas las líneas.")
                        return render(request, self.template_name, {'inicial': inicial, 'prod_fs': prod_fs})

                    # validar disponible
                    disp = decimal2(mapa_disp.get(prod.pk, 0))
                    if cantidad > disp:
                        messages.error(
                            request,
                            f"La cantidad solicitada para '{prod}' ({cantidad}) excede el disponible ({disp}) para esta deuda."
                        )
                        return render(request, self.template_name, {'inicial': inicial, 'prod_fs': prod_fs})

                    total += (precio * cantidad)
                    lineas_p.append(cd)

            if total <= 0:
                messages.error(request, "La NC debe tener total > 0.")
                return render(request, self.template_name, {'inicial': inicial, 'prod_fs': prod_fs})

        else:
            # NC sin stock: un único importe
            importe = decimal2(inicial.cleaned_data.get('importe_nc') or 0)
            if importe <= 0:
                messages.error(request, "Indicá un importe > 0 para la NC.")
                return render(request, self.template_name, {'inicial': inicial, 'prod_fs': prod_fs})
            total = importe

        # 3) Crear NC
        nc = NotaCreditoProveedor.objects.create(
            consorcio=c,
            acreedor=acreedor,
            deuda=deuda,
            fecha=fecha,
            observacion=observacion,
            es_proveeduria=es_prov,
            deposito=deposito if es_prov else None,
            total=total.quantize(Decimal('0.01')),
        )

        # 4) Guardar líneas (si corresponde)
        if es_prov:
            for cd in lineas_p:
                NotaCreditoLineaProducto.objects.create(
                    nc=nc,
                    producto=cd['producto'],
                    cantidad=decimal2(cd['cantidad']),
                    precio=decimal2(cd['precio']),
                )

        # 5) Aplicar efectos (stock / total deuda capado)
        aplicado = aplicar_nc_a_deuda(deuda=deuda, nc=nc)

        # crear asiento solo si hubo aplicación efectiva
        if aplicado > 0:
            ok = asiento_nc_proveedor(nc=nc, aplicado=aplicado)
            if ok is not True:
                messages.error(request, ok)  # muestra el error del asiento

        messages.success(request, "Nota de Crédito aplicada correctamente.")
        return redirect('deudas')



from django.views import generic

@method_decorator(group_required('administrativo', 'contable', 'sin_op'), name='dispatch')
class RegistroNCProveedor(OrderQS):
    """ Registro de NC Proveedor """
    model = NotaCreditoProveedor
    filterset_class = NotaCreditoProveedorFilter
    template_name = 'nc/registros/nc_proveedor.html'
    paginate_by = 50

    def get_queryset(self, **kwargs):
        qs = super().get_queryset(**kwargs)
        return (
            qs.filter(consorcio=consorcio(self.request))
              .select_related('acreedor', 'deuda', 'deposito', 'asiento')
              .order_by('-fecha', '-id')
        )

@method_decorator(group_required('administrativo', 'contable', 'sin_op'), name='dispatch')
class NCProveedorDetalleView(generic.DetailView):
    model = NotaCreditoProveedor
    template_name = 'nc/registros/detalle_nc_proveedor.html'

    def get_queryset(self):
        return (
            super().get_queryset()
            .filter(consorcio=consorcio(self.request))
            .select_related('acreedor','deuda','deposito')
            .prefetch_related('lineas_productos__producto', 'lineas_gastos__gasto')
        )
