import datetime
from datetime import date
from django.shortcuts import render, redirect
from admincu.funciones import *
from django.contrib import messages
from .models import *
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count
from comprobantes.models import *
from creditos.models import *
from proveeduria.models import *
from op.models import *
from django.db.models import Sum, Avg, F, DecimalField, FloatField, ExpressionWrapper, Case, When, Value, Subquery, OuterRef
from django.db.models.functions import Coalesce, Cast
from decimal import Decimal

@group_required('administrativo', 'contable')
def res_index(request):

	resumenes = Resumen.objects.all().order_by('nombre')

	return render(request, 'resumenes/index.html', locals())

@group_required('administrativo', 'contable')
def res_par(request, resumen):
	try:
		resumen = Resumen.objects.get(slug=resumen)
	except:
		return redirect('resumenes')

	return render(request, 'resumenes/parametros/index.html', locals())


@require_http_methods(["POST"])
@group_required('administrativo', 'contable')
def res_sp(request):
	consorcio_actual = consorcio(request)
	tiene_convenios = consorcio_actual.convenios	

	resumen = Resumen.objects.get(slug='saldos-pendientes-de-socios')
	ingresos = Ingreso.objects.filter(id__in=request.POST.getlist('ingresos'))

	convenios_seleccionados = request.POST.getlist('convenios')
	socios_ids = request.POST.getlist('socios')

	if tiene_convenios and convenios_seleccionados:
		# Tiene convenios y eligió al menos uno
		socios = Socio.objects.filter(id__in=socios_ids, convenio__in=convenios_seleccionados)
	else:
		# No tiene convenios o no eligió ninguno
		socios = Socio.objects.filter(id__in=socios_ids)


	intereses = request.POST.get('intereses')
	fecha = datetime.strptime(request.POST.get('fecha'), '%Y-%m-%d').date()

	# Filtro base
	filtro = {
		'consorcio': consorcio(request),
		'ingreso__in': ingresos,
		'socio__in': socios,
		# 'periodo__lte': fecha,
		'fecha__lte': fecha,
	}
	# Agregar impagos a la fecha de hoy
	filtro_impagos = filtro.copy()
	filtro_impagos.update({'fin__isnull': True})

	# Agregar impagos a la fecha recibida
	filtro_post_pagos = filtro.copy()
	filtro_post_pagos.update({'fin__gt': fecha})


	saldos = Credito.objects.filter(
			Q(**filtro_impagos) | Q(**filtro_post_pagos)
		)

	periodos = []

	if saldos:
		for periodo in saldos.values('periodo').annotate(Count('periodo')):
			periodos.append(date(periodo['periodo'].year, periodo['periodo'].month, 1))
			periodos = sorted(list(set(periodos)), reverse=True)

	if not periodos:
		periodos = [date.today().replace(day=1)]

	saldo_a_favor = date(periodos[0].year, periodos[0].month, 27)
	periodos.append(saldo_a_favor)
	saldo_final = date(periodos[0].year, periodos[0].month, 28)
	periodos.append(saldo_final)
	periodos = sorted(periodos, reverse=True)
	saldos = saldos.order_by('periodo')
	data = {}
	for d in socios:
		convenio = d.convenio if tiene_convenios else None  # Obtén el convenio del socio si corresponde
		data_ingresos = {}
		for i in ingresos:
			data_periodos = {}
			for p in periodos:
				data_periodos.update({p: 0})
			data_ingresos.update({i:data_periodos})
		data.update({d:data_ingresos})

	#desuso = len(dominios) >= (0.7*len(consorcio(request).dominio_set.all()))
	#if desuso:
	#	socios_desuso = Socio.objects.filter(Q(consorcio=consorcio(request), baja__isnull=False) | Q(consorcio=consorcio(request), socio__isnull=True))
	#	for s in socios_desuso:
	#		data_ingresos = {}
	#		for i in ingresos:
	#			data_periodos = {}
	#			for p in periodos:
	#				data_periodos.update({p: 0})
	#			data_ingresos.update({i:data_periodos})
	#		data.update({s:data_ingresos})

	totales = {}
	for p in periodos:
		totales.update({p: 0})

	data_totales = {'Totales': {'Totales':totales}}

	if saldos:
		for s in saldos:
			valor = s.subtotal(fecha_operacion=fecha) if intereses else s.bruto
			data[s.socio][s.ingreso][date(s.periodo.year, s.periodo.month, 1)] += valor
			data_totales['Totales']['Totales'][date(s.periodo.year, s.periodo.month, 1)] += valor

	pagos_a_cuenta = Saldo.objects.filter(
			consorcio=consorcio(request),
			socio__in=set([d for d in socios]),
			fecha__lte=fecha,
			padre__isnull=True
			)
	if pagos_a_cuenta:
		for p in pagos_a_cuenta:
			valor = p.saldo(fecha=fecha)
			data[p.socio][ingresos[0]][saldo_a_favor] -= valor
			data_totales['Totales']['Totales'][saldo_a_favor] -= valor

	#if desuso:
	#	pagos_a_cuenta_socios_baja = Saldo.objects.filter(
	#			consorcio=consorcio(request),
	#			socio__in=socios_desuso,
	#			fecha__lte=fecha,
	#			padre__isnull=True
	#			)
	#	if pagos_a_cuenta_socios_baja:
	#		for p in pagos_a_cuenta_socios_baja:
	#			valor = p.saldo(fecha=fecha)
	#			data[p.socio][ingresos[0]][saldo_a_favor] -= valor
	#			data_totales['Totales']['Totales'][saldo_a_favor] -= valor	
	#
	for socio, ingresos in data.copy().items():
		for i, p in ingresos.copy().items():
			suma = sum(p.values())
			con_valores = any(valor for valor in p.values())
			if not con_valores:
				data[socio].pop(i)
			else:
				data[socio][i][saldo_final] = suma
				data_totales['Totales']['Totales'][saldo_final] += suma


	return render(request, 'resumenes/saldos-pendientes/index.html', locals())

@require_http_methods(["POST"])
@group_required('administrativo', 'contable')
def res_cob(request):
	try:
		resumen = Resumen.objects.get(slug='cobranzas-y-medios')
		socios = Socio.objects.filter(id__in=request.POST.getlist('socios'))
	except:
		messages.add_message(request, messages.ERROR, 'Has seleccionado parametros invalidos')
		return redirect('resumenes')


	ingresos = {}
	for i in Ingreso.objects.filter(consorcio=consorcio(request)):
		ingresos.update({i: 0})

	cajas = {}
	for c in Caja.objects.filter(consorcio=consorcio(request)):
		cajas.update({c: 0})


	opcion = request.POST.get('opcion')
	fechas = request.POST.get('fechas')
	if fechas:
		rango = request.POST.get('fechas').split(" / ")

		#Cobros
		cobros = Cobro.objects.filter(
				consorcio=consorcio(request),
				socio__in=socios,
				fecha__range=rango
			)
		# Excluir cobros por notas de credito que hayan sido anuladas (Esto porque en el prado anularon una nota de credito. )
		# La situacion ya esta arreglada para que no se vuelva a repetir
		cobros = cobros.exclude(comprobante__nota_credito__isnull=False, comprobante__anulado__isnull=False)
		# Excluir cobros de mercadopago que aun no tengan recibos
		cobros = cobros.exclude(preference__paid=False)
		cobros = cobros.exclude(preference__paid=True, comprobante__isnull=True)


		saldos_nuevos = Saldo.objects.filter(
				consorcio=consorcio(request),
				socio__in=socios,
				fecha__range=rango,
				padre__isnull=True
			)
		total_saldos_nuevos = sum([c.subtotal for c in saldos_nuevos])
		total_ingresos = total_saldos_nuevos
		intereses = 0
		for c in cobros:
			ingresos[c.credito.ingreso] += c.capital
			intereses += c.int_desc
			total_ingresos += c.subtotal



		# Cajas
		formas_de_cobro = CajaComprobante.objects.filter(
					comprobante__socio__in=socios,
					fecha__range=rango,
			)
		saldos_utilizados = Saldo.objects.filter(
					consorcio=consorcio(request),
					socio__in=socios,
					fecha__range=rango,
					padre__isnull=False
			)
		total_saldos_utilizados = sum([s.subtotal_invertido for s in saldos_utilizados])
		total_cajas = total_saldos_utilizados
		nc = Comprobante.objects.filter(
				socio__in=socios,
				punto__isnull=True,
				nota_credito__isnull=False,
				fecha__range=rango,
			)
		# Excluir cobros por notas de credito que hayan sido anuladas (Esto porque en el prado anularon una nota de credito. )
		# La situacion ya esta arreglada para que no se vuelva a repetir
		nc = nc.exclude(nota_credito__isnull=False, anulado__isnull=False)
		total_nc = nc.values('total').aggregate(suma_valor=Sum('total'))['suma_valor'] or 0
		total_cajas += total_nc
		for fc in formas_de_cobro:
			cajas[fc.caja] += fc.valor
			total_cajas += fc.valor



	return render(request, 'resumenes/cobranzas/index.html', locals())

@require_http_methods(["POST"])
@group_required('administrativo', 'contable')
def res_dp(request):
	try:
		resumen = Resumen.objects.get(slug='deudas-pendientes-con-acreedores')
		acreedores = Acreedor.objects.filter(id__in=request.POST.getlist('acreedores'))
	except:
		messages.add_message(request, messages.ERROR, 'Has seleccionado parametros invalidos')
		return redirect('resumenes')

	fecha = request.POST.get('fecha')


	deudas = Deuda.objects.filter(
		consorcio=consorcio(request),
		acreedor__in=acreedores,
		fecha__lte=fecha,
		aceptado=True,
	)

	saldos = []
	total_adeudado = 0
	total_cancelado = 0
	total_saldo = 0
	for d in deudas:
		if d.saldo_a_fecha(fecha):
			saldito = d.saldo_a_fecha(fecha)
			cancelado_a_fecha = -d.cancelado_a_fecha(fecha)
			total_adeudado += d.total
			total_cancelado += cancelado_a_fecha
			total_saldo += saldito
			d.cancelado = cancelado_a_fecha
			d.saldito = saldito
			saldos.append(d)

	return render(request, 'resumenes/deudas-pendientes/index.html', locals())

@require_http_methods(["POST"])
@group_required('administrativo', 'contable')
def res_pagos(request):
	try:
		resumen = Resumen.objects.get(slug='pagos-y-medios')
		acreedores = Acreedor.objects.filter(id__in=request.POST.getlist('acreedores'))
	except:
		messages.add_message(request, messages.ERROR, 'Has seleccionado parametros invalidos')
		return redirect('resumenes')

	opcion = request.POST.get('opcion')
	fechas = request.POST.get('fechas')

	erogaciones = {}
	for g in Gasto.objects.filter(consorcio=consorcio(request)):
		erogaciones.update({g: 0})

	cajas = {}
	for c in Caja.objects.filter(consorcio=consorcio(request)).order_by('nombre'):
		cajas.update({c: 0})

	if fechas:
		rango = request.POST.get('fechas').split(" / ")
		pagos = OP.objects.filter(
				consorcio=consorcio(request),
				fecha__range=rango,
				acreedor__in=acreedores,
				confirmado=True,
				anulado__isnull=True,
			)

		# Deudas
		deudas = DeudaOP.objects.filter(op__in=pagos)
		total_deudas = 0
		for deuda in deudas:
			total_deudas += deuda.valor

		# Gastos
		gastos = GastoOP.objects.filter(op__in=pagos)
		total_gastos = 0
		for gasto in gastos:
			erogaciones[gasto.gasto] += gasto.valor
			total_gastos += gasto.valor

		total_conceptos = total_deudas + total_gastos


		# Retenciones
		retenciones = RetencionOP.objects.filter(op__in=pagos)
		total_retenciones = 0
		for retencion in retenciones:
			total_retenciones += retencion.valor

		# Cajas
		formas_de_pago = CajaOP.objects.filter(op__in=pagos)
		total_cajas = 0
		for caja in formas_de_pago:
			cajas[caja.caja] += caja.valor
			total_cajas += caja.valor

		total_formas_de_pago = total_retenciones + total_cajas


	return render(request, 'resumenes/pagos/index.html', locals())

@require_http_methods(["POST"])
@group_required('administrativo', 'contable')
def res_edc(request):
	try:
		resumen = Resumen.objects.get(slug='estado-de-cuenta')
		socio = Socio.objects.get(id=request.POST.get('socio'))
	except:
		messages.add_message(request, messages.ERROR, 'Has seleccionado parametros invalidos')
		return redirect('resumenes')

	fecha = datetime.strptime(request.POST.get('fecha'), '%Y-%m-%d').date()

	operaciones = socio.cuenta_corriente(fecha)

	return render(request, 'resumenes/estado-de-cuenta/index.html', locals())

@require_http_methods(["POST"])
@group_required('administrativo', 'contable')
def res_edcp(request):
	try:
		resumen = Resumen.objects.get(slug='estado-de-cuenta-proveedores')
		proveedor = Acreedor.objects.get(id=request.POST.get('acreedor'))
	except:
		messages.add_message(request, messages.ERROR, 'Has seleccionado parametros invalidos')
		return redirect('resumenes')

	fecha = datetime.strptime(request.POST.get('fecha'), '%Y-%m-%d').date()

	operaciones = proveedor.cuenta_corriente(fecha)

	return render(request, 'resumenes/estado-de-cuenta-proveedores/index.html', locals())



@require_http_methods(["POST"])
@group_required('administrativo', 'contable')
def res_mdc(request):
	try:
		resumen = Resumen.objects.get(slug='movimientos-de-caja')
		caja = Caja.objects.get(id=request.POST.get('caja'))
	except:
		messages.add_message(request, messages.ERROR, 'Has seleccionado parametros invalidos')
		return redirect('resumenes')

	fecha = datetime.strptime(request.POST.get('fecha'), '%Y-%m-%d').date()

	if fecha:
		# Validaciones logicas
		if not caja.fecha or caja.saldo is None:
			messages.add_message(request, messages.ERROR, 'Debe colocar un saldo inicial y una fecha de dicho saldo en la caja solicitada.')

		elif caja.fecha > fecha:
			messages.add_message(request, messages.ERROR, 'El saldo de la caja seleccionada es posterior a la fecha solicitada.')

		else:
			operaciones = caja.movimientos(fecha)

	return render(request, 'resumenes/movimientos-de-caja/index.html', locals())



@require_http_methods(["POST"])
@group_required('administrativo', 'contable')
def res_id(request):
	try:
		resumen = Resumen.objects.get(slug='ingresos-devengados')
		ingresos = Ingreso.objects.filter(id__in=request.POST.getlist('ingresos'))
	except:
		messages.add_message(request, messages.ERROR, 'Has seleccionado parametros invalidos')
		return redirect('resumenes')

	fechas = request.POST.get('fechas').split(' / ')

	if fechas:
		fechas = request.POST.get('fechas').split(" / ")
		# Creditos por facturas
		creditos = Credito.objects.filter(
				consorcio=consorcio(request),
				fecha__range=fechas,
				ingreso__in=ingresos,
				padre__isnull=True,
				capital__gt=0
			)
		notas_debito = Cobro.objects.filter(
				consorcio=consorcio(request),
				comprobante__isnull=False,
				fecha__range=fechas,
				int_desc__gt=0,
				anulacion=False
			)
		notas_debito_anulado = Cobro.objects.filter(
				consorcio=consorcio(request),
				fecha__range=fechas,
				int_desc__gte=0,
				anulacion=True,
				comprobante__nota_credito__isnull=False,
			)
		notas_credito_automaticas = Cobro.objects.filter(
				consorcio=consorcio(request),
				comprobante__isnull=False,
				fecha__range=fechas,
				int_desc__lt=0,
				anulacion=False
			)
		notas_credito_automaticas_anulado = Cobro.objects.filter(
				consorcio=consorcio(request),
				comprobante__isnull=False,
				fecha__range=fechas,
				int_desc__lt=0,
				anulacion=True
			)
		notas_credito_manuales = Cobro.objects.filter(
				consorcio=consorcio(request),
				fecha__range=fechas,
				comprobante__punto__isnull=True,
				comprobante__nota_credito__isnull=False,
				capital__gte=0
			)



	return render(request, 'resumenes/ingresos/index.html', locals())

@require_http_methods(["POST"])
@group_required('administrativo', 'contable')
def res_gd(request):
	try:
		resumen = Resumen.objects.get(slug='gastos-devengados')
		gastos = Gasto.objects.filter(id__in=request.POST.getlist('gastos'))
	except:
		messages.add_message(request, messages.ERROR, 'Has seleccionado parametros invalidos')
		return redirect('resumenes')

	fechas = request.POST.get('fechas').split(' / ')

	if fechas:
		fechas = request.POST.get('fechas').split(" / ")
		deudas = GastoDeuda.objects.filter(
				deuda__consorcio=consorcio(request),
				fecha__range=fechas,
				gasto__in=gastos,
				deuda__confirmado=True,
			)
		ops = GastoOP.objects.filter(
				op__consorcio=consorcio(request),
				fecha__range=fechas,
				gasto__in=gastos,
				op__confirmado=True,
			)


	return render(request, 'resumenes/gastos/index.html', locals())

@require_http_methods(["POST"])
@group_required('administrativo', 'contable')
def res_edd(request):
	try:
		resumen = Resumen.objects.get(slug='estado-de-deuda')
		socio = Socio.objects.get(id=request.POST.get('socio'))
		consorcio = socio.consorcio
	except:
		messages.add_message(request, messages.ERROR, 'Has seleccionado parametros invalidos')
		return redirect('resumenes')

	fecha = datetime.strptime(request.POST.get('fecha'), '%Y-%m-%d').date()

	creditos = Credito.objects.filter(
		socio=socio,
		liquidacion__estado="confirmado",
		dominio__isnull=True,
		fin__isnull=True,
		periodo__lte=fecha,
	)

	total_saldo = sum(credito.saldo for credito in creditos)

	return render(request, 'resumenes/estado-de-deuda/index.html', {
	'resumen': resumen,
	'socio': socio,
	'fecha': fecha,
	'creditos': creditos,
	'context_type': 'estado_deuda',  # Nueva variable de contexto
	'total_saldo': total_saldo,
	'consorcio': consorcio,
	})


# views.py

# views.py


@require_http_methods(["POST"])
@group_required('administrativo', 'contable')
def res_cmv(request):
	try:
		resumen = Resumen.objects.get(slug='costo-de-mercaderia-vendida')
	except Resumen.DoesNotExist:
		messages.error(request, 'No existe el resumen "Costo de mercadería vendida".')
		return redirect('resumenes')

	# Rango de fechas "YYYY-MM-DD / YYYY-MM-DD"
	fechas_raw = (request.POST.get('fechas') or '').split(' / ')
	if len(fechas_raw) != 2:
		messages.error(request, 'Debés seleccionar un rango de fechas válido.')
		return redirect('res_par', resumen=resumen.slug)
	fecha_desde, fecha_hasta = fechas_raw

	# Productos seleccionados (opcional)
	productos_ids = request.POST.getlist('productos')

	# Query base
	qs = (
		Venta_Producto.objects
		.filter(
			consorcio=consorcio(request),
			credito__fecha__range=(fecha_desde, fecha_hasta),
			credito__liquidacion__estado='confirmado',
		)
		.select_related('producto')
	)
	if productos_ids:
		qs = qs.filter(producto_id__in=productos_ids)

	# 1) Anoto importes por línea (NO los sume todavía)
	qs = qs.annotate(
		cantidad_dec=Cast(Coalesce(F('cantidad'), Value(0)), DecimalField(max_digits=18, decimal_places=2)),
		costo_prod=Cast(Coalesce(F('producto__costo'), Value(0)), DecimalField(max_digits=18, decimal_places=2)),
		precio_unit=Cast(Coalesce(F('precio'), Value(0)), DecimalField(max_digits=18, decimal_places=2)),
	).annotate(
		costo_linea=ExpressionWrapper(F('cantidad_dec') * F('costo_prod'),
									  output_field=DecimalField(max_digits=18, decimal_places=2)),
		venta_linea=ExpressionWrapper(F('cantidad_dec') * F('precio_unit'),
									  output_field=DecimalField(max_digits=18, decimal_places=2)),
	)

	# 2) Agrupo y sumo sobre las ANOTACIONES (evita el FieldError)
	por_prod = (
		qs.values('producto__id', 'producto__nombre')
		  .annotate(
			  cantidad=Coalesce(Sum('cantidad_dec'), Value(0)),
			  costo_prom=Avg('costo_prod'),
			  precio_prom=Avg('precio_unit'),
			  costo_total=Coalesce(Sum('costo_linea'), Value(0)),
			  venta_total=Coalesce(Sum('venta_linea'), Value(0)),
		  )
		  .annotate(
			  rent_neto=ExpressionWrapper(F('venta_total') - F('costo_total'),
										  output_field=DecimalField(max_digits=18, decimal_places=2)),
		  )
		  .annotate(
			  rent_pct=Case(
				  When(venta_total__gt=0,
					   then=ExpressionWrapper((F('rent_neto') * Value(100.0)) / F('venta_total'),
											  output_field=FloatField())),
				  default=Value(0.0),
				  output_field=FloatField()
			  )
		  )
		  .order_by('producto__nombre')
	)

	# 3) Totales generales
	totales = qs.aggregate(
		cantidad=Coalesce(Sum('cantidad_dec'), Value(0)),
		costo_total=Coalesce(Sum('costo_linea'), Value(0)),
		venta_total=Coalesce(Sum('venta_linea'), Value(0)),
	)
	totales['rent_neto'] = totales['venta_total'] - totales['costo_total']
	totales['rent_pct'] = (float(totales['rent_neto']) * 100.0 / float(totales['venta_total'])) if totales['venta_total'] else 0.0

	return render(request, 'resumenes/cmv/index.html', {
		'resumen': resumen,
		'fechas': f'{fecha_desde} / {fecha_hasta}',
		'fecha_desde': fecha_desde,
		'fecha_hasta': fecha_hasta,
		'filas': list(por_prod),
		'totales': totales,
	})


@require_http_methods(["POST"])
@group_required('administrativo', 'contable')
def res_val_stock(request):
	try:
		resumen = Resumen.objects.get(slug='valorizacion-de-stock-a-fecha')
	except Resumen.DoesNotExist:
		messages.error(request, 'No existe el resumen "Valorización de stock a fecha".')
		return redirect('resumenes')

	fecha_str = request.POST.get('fecha')
	if not fecha_str:
		messages.error(request, 'Debés seleccionar una fecha.')
		return redirect('res_par', resumen=resumen.slug)

	productos_ids = request.POST.getlist('productos')  # múltiple, puede venir vacío

	# Movimientos hasta la fecha, del consorcio y (si hay) de los productos elegidos
	movs = MovimientoStock.objects.filter(
		producto__consorcio=consorcio(request),
		fecha__lte=fecha_str,
	)
	if productos_ids:
		movs = movs.filter(producto_id__in=productos_ids)

	# Último precio de compra por producto (fallback si Producto.costo es nulo)
	ult_compra_precio = (
		Compra_Producto.objects
		.filter(producto_id=OuterRef('producto_id'))
		.order_by('-id').values('precio')[:1]
	)

	base = (
		movs
		.values(
			'producto_id',
			'producto__nombre',
			'producto__rubro__nombre',
			'producto__unidad_medida',
			'producto__precio_1',
			'producto__costo',
		)
		.annotate(
			stock=Coalesce(Sum('cantidad'), Value(0)),
		)
		.annotate(
			costo_unit=Case(
				When(producto__costo__isnull=False, then=F('producto__costo')),
				default=Coalesce(Subquery(ult_compra_precio), Value(0)),
				output_field=DecimalField(max_digits=18, decimal_places=2),
			),
			precio_unit=Coalesce(F('producto__precio_1'), Value(0)),
		)
		.annotate(
			costo_total=Coalesce(F('stock') * F('costo_unit'), Value(0),
								 output_field=DecimalField(max_digits=18, decimal_places=2)),
			venta_total=Coalesce(F('stock') * F('precio_unit'), Value(0),
								 output_field=DecimalField(max_digits=18, decimal_places=2)),
		)
		.filter(stock__gt=0)  # si querés ver también stock 0, quitá esta línea
	)

	filas = (
		base
		.annotate(rent_neto=F('venta_total') - F('costo_total'))
		.annotate(
			rent_pct=Case(
				When(venta_total__gt=0, then=(F('rent_neto') * Value(100.0)) / F('venta_total')),
				default=Value(0.0),
				output_field=FloatField(),
			)
		)
		.order_by('producto__nombre')
	)

	# 👇 Evaluamos y sumamos en Python para evitar el error 1054 de MySQL
	filas_list = list(filas)

	tot_stock = Decimal('0')
	tot_costo = Decimal('0')
	tot_venta = Decimal('0')

	for f in filas_list:
		# pueden venir como Decimal o None
		tot_stock += f.get('stock') or Decimal('0')
		tot_costo += f.get('costo_total') or Decimal('0')
		tot_venta += f.get('venta_total') or Decimal('0')

	tot_rent_neto = tot_venta - tot_costo
	tot_rent_pct = float(tot_rent_neto) * 100.0 / float(tot_venta) if tot_venta else 0.0

	return render(request, 'resumenes/val_stock/index.html', {
		'resumen': resumen,
		'fecha': fecha_str,
		'filas': filas_list,
		'totales': {
			'stock': tot_stock,
			'costo_total': tot_costo,
			'venta_total': tot_venta,
			'rent_neto': tot_rent_neto,
			'rent_pct': tot_rent_pct,
		},
	})

