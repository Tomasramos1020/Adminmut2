from .models import *
from django.db.models import Prefetch

def generacionSaldos(cuentas, asientos):
	sumas = {}
	for c in cuentas:
		dic = {c: 0}
		sumas.update(dic)


	for asiento in asientos:
		for op in asiento.operaciones.filter(cuenta__in=cuentas):
			saldo = sumas[op.cuenta] + op.debe - op.haber
			sumas[op.cuenta] = saldo



	cuentas_con_saldo = {}
	for cuenta, saldo in sumas.items():
		if saldo != 0:
			cuentas_con_saldo.update({cuenta: saldo})
	return cuentas_con_saldo


def generacionSyS(cuentas, operaciones):
	for c in cuentas:
		c.debe = sum([op.debe for op in operaciones.filter(cuenta=c)])
		c.haber = sum([op.haber for op in operaciones.filter(cuenta=c)])
		c.saldo = c.debe - c.haber


def apropiadorDeAsientosPrincipales(ejercicio):
	# Para tomar el asiento de apertura
	try:
		ejercicio.asiento_apertura = Asiento.objects.get(
				consorcio=ejercicio.consorcio,
				fecha_asiento__range=[ejercicio.inicio, ejercicio.cierre],
				principal=1
			)
	except:
		ejercicio.asiento_apertura = None


	# Para tomar el asiento de cierre de resultados
	try:
		ejercicio.asiento_cierre_res = Asiento.objects.get(
				consorcio=ejercicio.consorcio,
				fecha_asiento__range=[ejercicio.inicio, ejercicio.cierre],
				principal=2
			)
	except:
		ejercicio.asiento_cierre_res = None


	# Para tomar el asiento de cierre patrimonial
	try:
		ejercicio.asiento_cierre_pat = Asiento.objects.get(
				consorcio=ejercicio.consorcio,
				fecha_asiento__range=[ejercicio.inicio, ejercicio.cierre],
				principal=3
			)
	except:
		ejercicio.asiento_cierre_pat = None

	return ejercicio

def asientosNumerados(ejercicio, prefetch_operaciones=False):
	asientos = Asiento.objects.filter(
			consorcio=ejercicio.consorcio,
			fecha_asiento__range=[ejercicio.inicio, ejercicio.cierre]
		).order_by('fecha_asiento', 'id')

	if prefetch_operaciones:
		operaciones_qs = Operacion.objects.select_related('cuenta').order_by('haber', 'id')
		asientos = asientos.prefetch_related(
				Prefetch('operaciones', queryset=operaciones_qs, to_attr='operaciones_ordenadas')
			)

	i = 1
	for a in asientos:
		a.numero = i
		i += 1
	return asientos
