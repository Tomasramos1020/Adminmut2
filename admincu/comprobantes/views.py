from datetime import datetime, date, timedelta
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse
from django_afip.models import *
from django.db import transaction
from django.db.models import Count
from django_mercadopago.models import Preference, Payment
from django.db.models import Q
from django.views import generic
from django.utils.decorators import method_decorator
from django.core.files.storage import FileSystemStorage
from formtools.wizard.views import SessionWizardView
from django.utils.timezone import now
from tablib import Dataset
from functools import partial, wraps

from django.conf import settings


from admincu.funciones import *
from admincu.generic import OrderQS
from consorcios.models import *
from contabilidad.asientos.funciones import asiento_comp, asiento_compens
from arquitectura.models import *
from .funciones import *
from .forms import *
from .models import *
from .manager import ComprobanteCreator
from .filters import *
from expensas_pagas.models import CobroExp

# cobranzas/views_cobros_totales.py
import os
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction

from tablib import Dataset

from admincu.funciones import consorcio
from contabilidad.models import Cuenta

mensaje_success = "Comprobante generado con exito."


@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class Index(OrderQS):

	""" Index de comprobantes """

	model = Comprobante
	template_name = 'comprobantes/index.html'
	filterset_class = ComprobanteFilter
	paginate_by = 10

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context['a_generar_mp'] = len(
					Cobro.objects.filter(
						consorcio=consorcio(self.request),
						comprobante__isnull=True,
						preference__paid=True,
					).values('preference').annotate(mp=Count('preference'))
				)
		context['a_generar_exp'] = len(CobroExp.objects.filter(
			codigo_consorcio=consorcio(self.request).id,
			documentado__isnull=True
		))
				
		return context


@method_decorator(group_required('socio'), name='dispatch')
class IndexSocio(OrderQS):

	"""
		Index para el socio.
	"""

	model = Comprobante
	template_name = "comprobantes/socio/index.html"
	filterset_class = ComprobanteFilterSocio
	paginate_by = 50

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		socio = self.request.user.socio_set.first()
		context["pagos"] = Preference.objects.filter(
				cobro__socio=socio,
				cobro__comprobante__isnull=True,
				paid=True,
			).distinct()
		return context


	def get_queryset(self):
		return super().get_queryset(
			socio=self.request.user.socio_set.first()
		)


@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class Registro(OrderQS):

	""" Registro de comprobantes """

	model = Comprobante
	filterset_class = ComprobanteFilter
	template_name = 'comprobantes/registros/comprobantes.html'
	paginate_by = 50


class WizardComprobanteManager:

	""" Administrador de comprobantes """

	TEMPLATES = {
		"inicial": "comprobantes/nuevo/inicial.html",
		"creditos": "comprobantes/nuevo/creditos.html",
		"saldos": "comprobantes/nuevo/saldos.html",
		"cajas": "comprobantes/nuevo/cajas.html",
		"descripcion": "comprobantes/nuevo/descripcion.html",
		"importacion": "comprobantes/nuevo/importacion.html",
		"confirmacion": "comprobantes/nuevo/confirmacion.html",
		"revision": "comprobantes/nuevo/revision.html",
	}
	def obtener_creditos(self, socio, tipo, ingreso=None):

		""" Obtiene los creditos a cobrar de un socio """
		if tipo == "Recibo X masivo":
			dominios = socio.socio.all()
			if dominios:
				creditos = Credito.objects.filter(
						dominio__in=dominios,
						fin__isnull=True,
						liquidacion__estado="confirmado",
						).order_by('periodo', 'fecha')
			else:
				creditos = Credito.objects.filter(
						socio=socio,
						ingreso=ingreso,
						liquidacion__estado="confirmado",
						dominio__isnull=True,
						fin__isnull=True, 
						).order_by('periodo', 'fecha')
			return creditos


		data_inicial = self.hacer_inicial(tipo)
		fecha_operacion = data_inicial['fecha_operacion'] if data_inicial['fecha_operacion'] else date.today()
		condonacion = False	

		dominios = socio.socio.all()
		#Ahora están ordenados de más antiguo a más reciente
		if tipo == "Nota de Credito C":
			creditos = Credito.objects.filter(
					socio=socio,
					liquidacion__estado="confirmado",
					dominio__isnull=True,
					fin__isnull=True,
					factura__receipt__receipt_type__code = 11
					).order_by('periodo', 'fecha')
		elif tipo == "Nota de Credito RG 1415":
			creditos = Credito.objects.filter(
					socio=socio,
					liquidacion__estado="confirmado",
					dominio__isnull=True,
					fin__isnull=True,
					).order_by('periodo', 'fecha')
		else:
			creditos = Credito.objects.filter(
					socio=socio,
					liquidacion__estado="confirmado",
					dominio__isnull=True,
					fin__isnull=True,
					).order_by('periodo', 'fecha')
		if creditos:
			cobros_mp = Cobro.objects.filter(
					credito__in=creditos,
					preference__paid=True,
				)
			if cobros_mp:
				excluir = [c.credito.id for c in cobros_mp]
				creditos = creditos.exclude(id__in=excluir)

			for c in creditos:
				if tipo in ["Nota de Credito C", "Nota de Credito RG 1415"] and c.int_desc() < 0:
					c.neto = c.bruto
				else:
					c.neto = c.subtotal(fecha_operacion=fecha_operacion, condonacion=condonacion)
					c.detalle_procesado = c.detalle_acc(fecha_operacion=fecha_operacion, condonacion=condonacion)

				c.interes = c.intereses(fecha_operacion=fecha_operacion) or 0.01

		return creditos

	def obtener_saldos(self, socio):

		""" Obtiene los saldos a favor de un socio """

		saldos = socio.get_saldos(fecha=date.today())
		return saldos


	def hacer_inicial(self, tipo):

		""" Crea la data inicial con el tipo de comprobante que debe realizar """

		data_inicial = self.get_cleaned_data_for_step('inicial')
		if data_inicial:
			data_inicial['tipo'] = tipo
			if tipo in ["Nota de Credito C", "Nota de Credito RG 1415"]:
				data_inicial['fecha_operacion'] = None
				data_inicial['condonacion'] = False
			if tipo == "Recibo X exp":
				data_inicial['fecha_operacion'] = data_inicial['cobroexp'].fecha_cobro
				data_inicial['condonacion'] = False
			if tipo == "Recibo X masivo":
				data_inicial['fecha_operacion'] = None
				data_inicial['condonacion'] = False
		return data_inicial

	def hacer_cobros(self):

		"""
		Crea lista de DICCIONARIOS de cobros. No lista de objetos
		Para poder utilizar mejor en manager.py
		"""

		cobros = []
		data_creditos = self.get_cleaned_data_for_step('creditos')
		if data_creditos:
			for d in data_creditos:
				if d:
					if d['subtotal']:
						data = {
							'credito': Credito.objects.get(id=d['credito']),
							'subtotal': d['subtotal'] # Lo que coloca el usuario
						}
						cobros.append(data)


		return cobros


	def hacer_utilizaciones_de_saldos(self):

		"""
		Crea lista de DICCIONARIOS de saldos. No lista de objetos
		Para poder utilizar mejor en manager.py
		"""

		saldos = []
		data_saldos = self.get_cleaned_data_for_step('saldos')
		if data_saldos:
			for d in data_saldos:
				if d:
					if d['subtotal']:
						data = {
							'saldo': Saldo.objects.get(id=d['saldo']),
							'subtotal': d['subtotal'] # Lo que coloca el usuario
						}
						saldos.append(data)

		return saldos

	def hacer_cajas(self):

		"""
		Crea lista de DICCIONARIOS de caja. No lista de objetos
		Para poder utilizar mejor en manager.py
		"""

		cajas = []
		data_cajas = self.get_cleaned_data_for_step('cajas')
		if data_cajas:
			for d in data_cajas:
				if d:
					if d['subtotal']:
						data = {
							'caja': d['caja'],
							'referencia': d['referencia'],
							'subtotal': d['subtotal'] # Lo que coloca el usuario
						}
						cajas.append(data)
		return cajas

	def hacer_nuevo_saldo(self, **kwargs):

		"""
		Retorna solo el valor del nuevo saldo
		Para poder utilizar mejor en manager.py
		"""

		diferencia = kwargs['total'] - kwargs['suma']
		if diferencia > 0:
			return diferencia
		return

	def hacer_descripcion(self, tipo):

		""" Crea el string descripcion """

		descripcion = ""
		data_inicial = self.hacer_inicial(tipo)
		data_descripcion = self.get_cleaned_data_for_step('descripcion')
		if data_descripcion:
			descripcion += data_descripcion['descripcion']
			if data_inicial['fecha_operacion']:
				descripcion += '* Cobrado el dia {}.'.format(data_inicial['fecha_operacion'])
		return descripcion


@method_decorator(group_required('administrativo'), name='dispatch')
class RCXWizard(WizardComprobanteManager, SessionWizardView):

	form_list = [
		('inicial', InicialForm),
		('creditos', CobroFormSet),
		('saldos', SaldoFormSet),
		('cajas', CajaFormSet),
		('descripcion', DescripcionForm),
		('confirmacion', ConfirmacionForm),
	]

	def calcular_total(self, **kwargs):

		""" Total particular en recibos """

		suma = 0
		try:
			for caja in kwargs['cajas']:
				suma += caja['subtotal']
		except:
			for k, v in kwargs.items():
				if k == "saldos":
					for saldo in v:
						suma -= saldo['subtotal']
				if k == "cobros":
					for cobro in v:
						suma += cobro['subtotal']
		return suma

	def get_template_names(self):
		return [self.TEMPLATES[self.steps.current]]

	def get_context_data(self, form, **kwargs):
		context = super().get_context_data(form=form, **kwargs)
		tipo = "Recibo X"
		extension = 'comprobantes/nuevo/Recibo.html'
		data_inicial = self.hacer_inicial(tipo)
		if data_inicial:
			socio = data_inicial['socio']
			cobros = self.hacer_cobros()
			utilizacion_saldos = self.hacer_utilizaciones_de_saldos()
			cajas = self.hacer_cajas()
			descripcion = self.hacer_descripcion(tipo)
			suma = self.calcular_total(cobros=cobros, saldos=utilizacion_saldos)
			total = self.calcular_total(cajas=cajas)
			nuevo_saldo = self.hacer_nuevo_saldo(
					total=total,
					suma=suma,
				)

			if self.steps.current == 'creditos':
				creditos = self.obtener_creditos(socio, tipo)
				bloqueo = bloqueador(creditos)
				sumar = True

			elif self.steps.current == 'saldos':
				saldos_a_utilizar = self.obtener_saldos(socio)
				validar = "La suma de saldos utilizados no puede ser mayor a {}".format(suma)

			elif self.steps.current == 'cajas':
				validar = "La suma no puede ser menor a {}".format(suma)

			elif self.steps.current == 'confirmacion':
				documento = ComprobanteCreator(
					data_inicial=data_inicial,
					data_descripcion=descripcion,
					data_cobros=cobros,
					data_utilizacion_saldos=utilizacion_saldos,
					data_nuevo_saldo=nuevo_saldo,
					data_cajas=cajas
				)
				cobros, creditos = documento.hacer_cobros_y_creditos()
				saldos = documento.hacer_utilizaciones_de_saldos()
				cajas = documento.hacer_cajas()
				nuevo_saldo = documento.hacer_nuevo_saldo()

		context.update(locals())

		return context

	def get_form_kwargs(self, step):
		kwargs = super().get_form_kwargs()
		if step == "inicial":
			kwargs.update({
					'consorcio': consorcio(self.request)
				})
		return kwargs

	def get_form(self, step=None, data=None, files=None):
		form = super().get_form(step, data, files)
		formset = False
		if data:
			if 'cajas' in data['rcx_wizard-current_step']:
				formset = True
		if step == "cajas":
			formset = True

		if formset:
			formset = formset_factory(wraps(CajaForm)(partial(CajaForm, consorcio=consorcio(self.request))), extra=5)
			form = formset(prefix='cajas', data=data)
		return form

	@transaction.atomic
	def done(self, form_list, **kwargs):
		tipo = "Recibo X"
		cobros = self.hacer_cobros()
		utilizacion_saldos = self.hacer_utilizaciones_de_saldos()
		cajas = self.hacer_cajas()
		suma = self.calcular_total(cobros=cobros, saldos=utilizacion_saldos)
		total = self.calcular_total(cajas=cajas)
		documento = ComprobanteCreator(
			data_inicial=self.hacer_inicial(tipo),
			data_descripcion=self.hacer_descripcion(tipo),
			data_cobros=cobros,
			data_utilizacion_saldos=utilizacion_saldos,
			data_nuevo_saldo=self.hacer_nuevo_saldo(total=total,suma=suma),
			data_cajas=cajas
		)
		evaluacion = documento.guardar()
		if type(evaluacion) == list:
			messages.error(self.request, evaluacion[0])
		else:
			messages.success(self.request, mensaje_success)
		return redirect('cobranzas')


@method_decorator(group_required('administrativo'), name='dispatch')
class RCXFacturaWizard(WizardComprobanteManager, SessionWizardView):

	form_list = [
		('saldos', SaldoFormSet),
		('cajas', CajaFormSet),
		('confirmacion', ConfirmacionForm),
	]

	def get_object(self):

		return Factura.objects.get(pk=self.kwargs['pk'])


	def calcular_total(self, **kwargs):

		""" Total particular en recibos """

		suma = 0
		try:
			for caja in kwargs['cajas']:
				suma += caja['subtotal']
		except:
			for k, v in kwargs.items():
				if k == "saldos":
					for saldo in v:
						suma -= saldo['subtotal']
				if k == "cobros":
					for cobro in v:
						suma += cobro['subtotal']
		return suma


	def get_template_names(self):
		return [self.TEMPLATES[self.steps.current]]

	def hacer_cobros(self):

		""" Particular """

		factura = self.get_object()
		creditos = factura.credito_set.all()
		cobros = []
		for c in creditos:
			data = {
				'credito': c,
				'subtotal': c.subtotal()
			}
			cobros.append(data)
		return cobros

	def hacer_inicial(self, tipo):

		""" Particular """
		factura = self.get_object()
		return {
			'punto': factura.receipt.point_of_sales,
			'socio': factura.socio,
			'fecha_operacion': None,
			'condonacion': False,
			'tipo': tipo
		}


	def get_context_data(self, form, **kwargs):
		context = super().get_context_data(form=form, **kwargs)
		tipo = "Recibo X"
		extension = 'comprobantes/nuevo/Recibo.html'
		factura = self.get_object()
		socio = factura.socio
		data_inicial = self.hacer_inicial(tipo)

		cobros = self.hacer_cobros()
		utilizacion_saldos = self.hacer_utilizaciones_de_saldos()
		cajas = self.hacer_cajas()
		descripcion = self.hacer_descripcion(tipo)
		suma = self.calcular_total(cobros=cobros, saldos=utilizacion_saldos)
		total = self.calcular_total(cajas=cajas)
		nuevo_saldo = self.hacer_nuevo_saldo(
				total=total,
				suma=suma,
			)

		if self.steps.current == 'saldos':
			saldos_a_utilizar = self.obtener_saldos(socio)
			validar = "La suma de saldos utilizados no puede ser mayor a {}".format(suma)

		elif self.steps.current == 'cajas':
			validar = "La suma no puede ser menor a {}".format(suma)

		elif self.steps.current == 'confirmacion':
			documento = ComprobanteCreator(
				data_inicial=data_inicial,
				data_descripcion=descripcion,
				data_cobros=cobros,
				data_utilizacion_saldos=utilizacion_saldos,
				data_nuevo_saldo=nuevo_saldo,
				data_cajas=cajas
			)
			cobros, creditos = documento.hacer_cobros_y_creditos()
			saldos = documento.hacer_utilizaciones_de_saldos()
			cajas = documento.hacer_cajas()
			nuevo_saldo = documento.hacer_nuevo_saldo()

		context.update(locals())

		return context

	def get_form_kwargs(self, step):
		kwargs = super().get_form_kwargs()
		if step == "inicial":
			kwargs.update({
					'consorcio': consorcio(self.request)
				})
		return kwargs

	def get_form(self, step=None, data=None, files=None):
		from functools import partial, wraps
		form = super().get_form(step, data, files)
		formset = False
		if data:
			if 'cajas' in data['rcx_factura_wizard-current_step']:
				formset = True
		if step == "cajas":
			formset = True

		if formset:
			formset = formset_factory(wraps(CajaForm)(partial(CajaForm, consorcio=consorcio(self.request))), extra=5)
			form = formset(prefix='cajas', data=data)
		return form

	@transaction.atomic
	def done(self, form_list, **kwargs):
		tipo = "Recibo X"
		data_inicial = self.hacer_inicial(tipo)
		cobros = self.hacer_cobros()
		utilizacion_saldos = self.hacer_utilizaciones_de_saldos()
		cajas = self.hacer_cajas()
		suma = self.calcular_total(cobros=cobros, saldos=utilizacion_saldos)
		total = self.calcular_total(cajas=cajas)
		documento = ComprobanteCreator(
			data_inicial=self.hacer_inicial(tipo),
			data_descripcion=self.hacer_descripcion(tipo),
			data_cobros=cobros,
			data_utilizacion_saldos=utilizacion_saldos,
			data_nuevo_saldo=self.hacer_nuevo_saldo(total=total,suma=suma),
			data_cajas=cajas
		)
		evaluacion = documento.guardar()
		if type(evaluacion) == list:
			messages.error(self.request, evaluacion[0])
		else:
			messages.success(self.request, mensaje_success)
		return redirect('cobranzas')


@method_decorator(group_required('administrativo'), name='dispatch')
class RCXMPWizard(WizardComprobanteManager, SessionWizardView):

	form_list = [
		('inicial', MPForm),
		('confirmacion', ConfirmacionForm),
	]

	def calcular_total(self, **kwargs):

		""" Total particular en mp """

		suma = 0
		for k, v in kwargs.items():
			if v:
				for cobro in v:
					suma += cobro.subtotal
		return suma

	def get_template_names(self):
		return [self.TEMPLATES[self.steps.current]]

	def get_context_data(self, form, **kwargs):
		context = super().get_context_data(form=form, **kwargs)
		tipo = "Recibo X"
		extension = 'comprobantes/nuevo/Recibo.html'
		data_inicial = self.hacer_inicial(tipo)
		if data_inicial:
			preference = data_inicial['preference']
			payment = preference.payments.filter(status="approved").first()
			cobros = preference.cobro_set.all()
			socio = cobros.first().socio
			data_inicial['socio'] = socio
			data_inicial['fecha_operacion'] = payment.created.date()
			data_inicial['condonacion'] = False
			suma = self.calcular_total(cobros=cobros)
			total = suma
			descripcion = "Cobrado por MercadoPago"

			if self.steps.current == 'confirmacion':
				documento = ComprobanteCreator(
					data_inicial=data_inicial,
					data_descripcion=descripcion,
					data_mp=cobros
				)
				cobros, creditos = documento.hacer_cobros_y_creditos()
				cajas = documento.hacer_cajas()

		context.update(locals())

		return context

	def get_form_kwargs(self, step):
		kwargs = super().get_form_kwargs()
		if step == "inicial":
			kwargs.update({
					'consorcio': consorcio(self.request)
				})
		return kwargs

	@transaction.atomic
	def done(self, form_list, **kwargs):
		tipo = "Recibo X"
		data_inicial = self.hacer_inicial(tipo)
		preference = data_inicial['preference']
		payment = preference.payments.filter(status="approved").first()
		cobros = preference.cobro_set.all()
		data_inicial['socio'] = cobros.first().socio
		data_inicial['fecha_operacion'] = payment.created.date()
		data_inicial['condonacion'] = False
		descripcion = "Cobrado por MercadoPago"
		documento = ComprobanteCreator(
			data_inicial=data_inicial,
			data_descripcion=descripcion,
			data_mp=cobros
		)
		evaluacion = documento.guardar()
		if type(evaluacion) == list:
			messages.error(self.request, evaluacion[0])
		else:
			messages.success(self.request, mensaje_success)
		return redirect('cobranzas')


@method_decorator(group_required('administrativo'), name='dispatch')
class RCXEXPWizard(WizardComprobanteManager, SessionWizardView):

	form_list = [
		('inicial', EXPForm),
		('creditos', CobroFormSet),
		('confirmacion', ConfirmacionForm),
	]

	def calcular_total(self, **kwargs):

		""" Total particular en exp """
		suma = 0
		try:
			for cobro in kwargs['cobros']:
				suma += cobro['subtotal']
		except:
			suma = self.hacer_inicial("Recibo X exp")['cobroexp'].importe_cobrado
		return suma


	def get_template_names(self):
		return [self.TEMPLATES[self.steps.current]]

	def get_context_data(self, form, **kwargs):
		context = super().get_context_data(form=form, **kwargs)
		tipo = "Recibo X exp"
		extension = 'comprobantes/nuevo/Recibo.html'
		data_inicial = self.hacer_inicial(tipo)
		if data_inicial:
			cobroexp = data_inicial['cobroexp']
			socio = Socio.objects.get(id=cobroexp.unidad_funcional)
			data_inicial['socio'] = socio			
			cobros = self.hacer_cobros()
			cajas = [{
					'subtotal': cobroexp.importe_cobrado,
					'referencia':'',
					'caja' : Caja.objects.get(consorcio=consorcio(self.request), nombre='Expensas Pagas')
			}]
			descripcion = "Cobrado Por - Canal de Pago: {} - Fecha: {}".format(Caja.objects.get(id=int(cobroexp.canal_de_pago)).nombre, cobroexp.fecha_cobro)
			data_inicial['condonacion'] = False
			total = cobroexp.importe_cobrado
			suma = self.calcular_total(cobros=cobros)
			total = self.calcular_total()
			nuevo_saldo = self.hacer_nuevo_saldo(
					total=total,
					suma=suma,
				)

			if self.steps.current == 'creditos':
				creditos = self.obtener_creditos(socio, tipo)
				bloqueo = bloqueador(creditos)
				sumar = True
				suma = total
				validar = "La suma de los creditos no puede ser mayor al cobro"


			if self.steps.current == 'confirmacion':
				documento = ComprobanteCreator(
					data_inicial=data_inicial,
					data_descripcion=descripcion,
					data_cobros=cobros,
					data_nuevo_saldo=nuevo_saldo,
					data_cajas=cajas
				)
				cobros, creditos = documento.hacer_cobros_y_creditos()
				cajas = documento.hacer_cajas()
				nuevo_saldo = documento.hacer_nuevo_saldo()

		context.update(locals())

		return context

	def get_form_kwargs(self, step):
		kwargs = super().get_form_kwargs()
		if step == "inicial":
			kwargs.update({
					'consorcio': consorcio(self.request)
				})
		return kwargs

	@transaction.atomic
	def done(self, form_list, **kwargs):
		tipo = "Recibo X exp"
		cobros = self.hacer_cobros()
		data_inicial = self.hacer_inicial(tipo)
		cobroexp = data_inicial['cobroexp']
		cajas = [{
				'subtotal': cobroexp.importe_cobrado,
				'referencia':'',
				'caja' : Caja.objects.get(consorcio=consorcio(self.request), nombre='Expensas Pagas')
		}]
		data_inicial['socio'] = Socio.objects.get(id=cobroexp.unidad_funcional)
		data_inicial['condonacion'] = False
		descripcion = "Cobrado Por - Canal de Pago: {} - Fecha: {}".format(Caja.objects.get(id=int(cobroexp.canal_de_pago)).nombre, cobroexp.fecha_cobro)
		suma = self.calcular_total(cobros=cobros)
		total = self.calcular_total(cajas=cajas)
		documento = ComprobanteCreator(
			data_inicial=data_inicial,
			data_descripcion=descripcion,
			data_cobros=cobros,
			data_nuevo_saldo=self.hacer_nuevo_saldo(total=total,suma=suma),
			data_cajas=cajas
		)
		evaluacion = documento.guardar()
		cobroexp.documentado = date.today() 
		cobroexp.save()
		if type(evaluacion) == list:
			messages.error(self.request, evaluacion[0])
		else:
			messages.success(self.request, mensaje_success)
		return redirect('cobranzas')

@method_decorator(group_required('administrativo'), name='dispatch')
class NCCWizard(WizardComprobanteManager, SessionWizardView):

	form_list = [
		('inicial', InicialForm),
		('creditos', CobroFormSet),
		('descripcion', DescripcionForm),
		('confirmacion', ConfirmacionForm),
	]

	def calcular_total(self, **kwargs):

		""" Total particular en notas de credito """

		suma = 0
		for k, v in kwargs.items():
			if v:
				for cobro in v:
					suma += cobro['subtotal']
		return suma

	def get_template_names(self):
		return [self.TEMPLATES[self.steps.current]]

	def get_context_data(self, form, **kwargs):
		context = super().get_context_data(form=form, **kwargs)
		tipo = "Nota de Credito C"
		extension = 'comprobantes/nuevo/13.html'
		data_inicial = self.hacer_inicial(tipo)
		if data_inicial:
			socio = data_inicial['socio']
			cobros = self.hacer_cobros()
			utilizacion_saldos = self.hacer_utilizaciones_de_saldos()
			descripcion = self.hacer_descripcion(tipo)
			suma = self.calcular_total(cobros=cobros)
			total = suma

			if self.steps.current == 'creditos':
				creditos = self.obtener_creditos(socio, tipo)
				bloqueo = bloqueador(creditos)
				sumar = True
				no_cero = True


			elif self.steps.current == 'confirmacion':
				documento = ComprobanteCreator(
					data_inicial=data_inicial,
					data_descripcion=descripcion,
					data_cobros=cobros,
				)
				cobros, creditos = documento.hacer_cobros_y_creditos()

		context.update(locals())

		return context

	def get_form_kwargs(self, step):
		kwargs = super().get_form_kwargs()
		if step == "inicial":
			kwargs.update({
					'consorcio': consorcio(self.request),
					'ok_ncc': True
				})
		return kwargs


	@transaction.atomic
	def done(self, form_list, **kwargs):
		tipo = "Nota de Credito C"
		documento = ComprobanteCreator(
			data_inicial=self.hacer_inicial(tipo),
			data_descripcion=self.hacer_descripcion(tipo),
			data_cobros=self.hacer_cobros(),
		)
		evaluacion = documento.guardar()
		if type(evaluacion) == list:
			messages.error(self.request, evaluacion[0])
		else:
			messages.success(self.request, mensaje_success)
		return redirect('cobranzas')



@method_decorator(group_required('administrativo'), name='dispatch')
class NCNFWizard(WizardComprobanteManager, SessionWizardView):

	form_list = [
		('inicial', InicialForm),
		('creditos', CobroFormSet),
		('descripcion', DescripcionForm),
		('confirmacion', ConfirmacionForm),
	]

	def calcular_total(self, **kwargs):

		""" Total particular en notas de credito """

		suma = 0
		for k, v in kwargs.items():
			if v:
				for cobro in v:
					suma += cobro['subtotal']
		return suma

	def get_template_names(self):
		return [self.TEMPLATES[self.steps.current]]

	def get_context_data(self, form, **kwargs):
		context = super().get_context_data(form=form, **kwargs)
		tipo = "Nota de Credito RG 1415"
		extension = 'comprobantes/nuevo/13.html'
		data_inicial = self.hacer_inicial(tipo)
		if data_inicial:
			socio = data_inicial['socio']
			cobros = self.hacer_cobros()
			utilizacion_saldos = self.hacer_utilizaciones_de_saldos()
			descripcion = self.hacer_descripcion(tipo)
			suma = self.calcular_total(cobros=cobros)
			total = suma

			if self.steps.current == 'creditos':
				creditos = self.obtener_creditos(socio, tipo)
				bloqueo = bloqueador(creditos)
				sumar = True
				no_cero = True


			elif self.steps.current == 'confirmacion':
				documento = ComprobanteCreator(
					data_inicial=data_inicial,
					data_descripcion=descripcion,
					data_cobros=cobros,
				)
				cobros, creditos = documento.hacer_cobros_y_creditos()

		context.update(locals())

		return context

	def get_form_kwargs(self, step):
		kwargs = super().get_form_kwargs()
		if step == "inicial":
			kwargs.update({
					'consorcio': consorcio(self.request),
					'ok_ncc': True
				})
		return kwargs


	@transaction.atomic
	def done(self, form_list, **kwargs):
		tipo = "Nota de Credito RG 1415"
		documento = ComprobanteCreator(
			data_inicial=self.hacer_inicial(tipo),
			data_descripcion=self.hacer_descripcion(tipo),
			data_cobros=self.hacer_cobros(),
		)
		evaluacion = documento.guardar()
		if type(evaluacion) == list:
			messages.error(self.request, evaluacion[0])
		else:
			messages.success(self.request, mensaje_success)
		return redirect('cobranzas')


class HeaderExeptMixin:

	def dispatch(self, request, *args, **kwargs):
		try:
			objeto = self.model.objects.get(consorcio=consorcio(self.request), pk=kwargs['pk'])
		except:
			messages.error(request, 'No se pudo encontrar.')
			return redirect('cobranzas')

		return super().dispatch(request, *args, **kwargs)


@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class Ver(HeaderExeptMixin, generic.DetailView):

	""" Ver un comprobante """

	template_name = 'comprobantes/ver/comprobante.html'
	model = Comprobante

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context['comprobante'] = self.get_object()
		return context


@method_decorator(group_required('administrativo', 'contable', 'socio'), name='dispatch')
class PDF(HeaderExeptMixin, generic.DetailView):


	""" Ver PDF de un comprobante """

	model = Comprobante
	template_name = 'comprobantes/ver/comprobante.html' # Solo para que no arroje error

	def get(self, request, *args, **kwargs):
		comprobante = self.get_object()
#		if comprobante.pdf_anulado:
#			response = HttpResponse(comprobante.pdf_anulado, content_type='application/pdf')
#		else:
#			response = HttpResponse(comprobante.pdf, content_type='application/pdf')
		# Generar PDF al vuelo, sin leer de media/
		pdf_bytes = comprobante.hacer_pdfs_inst()
		response = HttpResponse(pdf_bytes, content_type='application/pdf')
		nombre = "{}_{}.pdf".format(
			comprobante.tipo(),
			comprobante.nombre(),
		)
		content = "inline; filename=%s" % nombre
		response['Content-Disposition'] = content
		return response

	def dispatch(self, request, *args, **kwargs):
		disp = super().dispatch(request, *args, **kwargs)
		if disp.status_code == 200:
			if request.user.groups.first().name == "socio" and self.get_object().socio != request.user.socio_set.first():
				messages.error(request, 'No se pudo encontrar.')
				return redirect('home')
		return disp


@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class Anular(HeaderExeptMixin, generic.DeleteView):

	""" Para anular un comprobante """

	template_name = 'comprobantes/anular/comprobante.html'
	model = Comprobante

	@transaction.atomic
	def delete(self, request, *args, **kwargs):
		comprobante = self.get_object()
		# messages.error(request, 'Accion inhabilitada')
		saldo_comprobante = comprobante.saldos.filter(padre__isnull=True).first()
		if saldo_comprobante:
			if saldo_comprobante.saldo() != saldo_comprobante.subtotal:
				ultimo_hijo = saldo_comprobante.hijos.last()
				comprobante_destino = ultimo_hijo.comprobante_destino
				messages.error(request, 'Debe anular primero el comprobante {} {}.'.format(comprobante_destino.tipo(), comprobante_destino.nombre()))
				return redirect('ver-comprobante', pk=comprobante.pk)
		comprobante.anular()
		messages.success(request, 'Comprobante anulado con exito.')
		return redirect('ver-comprobante', pk=comprobante.pk)

	def dispatch(self, request, *args, **kwargs):
		disp = super().dispatch(request, *args, **kwargs)
		if disp.status_code == 200:
			comprobante = self.get_object()
			if not comprobante.punto:
				messages.error(request, 'No se puede anular una nota de credito.')
				return redirect('ver-comprobante', pk=comprobante.pk)
		return disp


@method_decorator(group_required('administrativo'), name='dispatch')
class RCXEXPMWizard(WizardComprobanteManager, SessionWizardView):

	form_list = [
		('inicial', EXPMForm),
		('confirmacion', ConfirmacionForm),
	]

	def calcular_total(self, **kwargs):

		""" Total particular en exp """
		suma = 0
		try:
			for cobro in kwargs['cobros']:
				suma += cobro['subtotal']
		except:
			suma = self.hacer_inicial("Recibo X exp")['cobroexp'].importe_cobrado
		return suma



	def get_template_names(self):
		return [self.TEMPLATES[self.steps.current]]

	# Esto es lo que tengo que modificar para el segundo paso: revisión de la imputación de los créditos.
	def get_context_data(self, form, **kwargs):
		context = super().get_context_data(form=form, **kwargs)
		tipo = "Recibo X masivo"
		extension = 'comprobantes/nuevo/Recibo.html'
		data_inicial = self.hacer_inicial(tipo)
		seleccion_multiple = True
		if data_inicial:
			
			if self.steps.current == 'confirmacion':
				documentos = []
				creditos_predocumentados = []
				for cobro in data_inicial['cobroexp']:
					caja = Caja.objects.get(consorcio=consorcio(self.request), id = int(cobro.canal_de_pago))
					socio = Socio.objects.get(id=cobro.unidad_funcional)
					ingreso =  Ingreso.objects.get(consorcio=consorcio(self.request), nombre=cobro.ingreso)
					data_inicial['socio'] = socio
					fecha_operacion = cobro.fecha_cobro
					data_inicial['fecha_operacion'] = fecha_operacion
					creditos = self.obtener_creditos(socio,tipo,ingreso)
					cobros = []
					remanente = cobro.importe_cobrado
					for c in creditos:
						if c not in creditos_predocumentados:
							subtotal = c.subtotal(fecha_operacion=fecha_operacion, condonacion=False)
							#Aquí es donde hay que corregir para que pueda imputar pagos parciales.
							if remanente >= subtotal:
								cobros.append({
									"credito" : c,
									"subtotal" : subtotal,
								})
								remanente -= subtotal
							creditos_predocumentados.append(c)
							
					nuevo_saldo = remanente	or None
					cajas = [{
						'subtotal': cobro.importe_cobrado,
						'referencia':'',
						'caja' : caja
					}]
					descripcion = "{} - Cobrado Por - Canal de Pago: {} - Fecha: {}".format(Ingreso.objects.get(consorcio=consorcio(self.request), nombre=cobro.ingreso), Caja.objects.get(id=int(cobro.canal_de_pago)).nombre, cobro.fecha_cobro)
					data_inicial['tipo'] = "Recibo X exp"
					documento = ComprobanteCreator(
						data_inicial=data_inicial,
						data_descripcion=descripcion,
						data_cobros=cobros,
						data_nuevo_saldo=nuevo_saldo,
						data_cajas=cajas
					)
					cobros, creditos = documento.hacer_cobros_y_creditos()
					documentos.append(documento)
				masivo = True
			
		context.update(locals())

		return context

	def get_form_kwargs(self, step):
		kwargs = super().get_form_kwargs()
		if step == "inicial":
			kwargs.update({
					'consorcio': consorcio(self.request)
				})
		return kwargs

	

	@transaction.atomic
	def done(self, form_list, **kwargs):
		tipo = "Recibo X masivo"
		#cobros = self.hacer_cobros()
		data_inicial = self.hacer_inicial(tipo)
		if data_inicial:
			
			creditos_predocumentados = []
			for cobro in data_inicial['cobroexp']:
			
				caja = Caja.objects.get(consorcio=consorcio(self.request), id = int(cobro.canal_de_pago))
				socio = Socio.objects.get(id=cobro.unidad_funcional)
				ingreso =  Ingreso.objects.get(consorcio=consorcio(self.request), nombre=cobro.ingreso)
				data_inicial['socio'] = socio
				fecha_operacion = cobro.fecha_cobro
				data_inicial['fecha_operacion'] = fecha_operacion
				creditos = self.obtener_creditos(socio,tipo,ingreso)
				cobros = []
				remanente = cobro.importe_cobrado
				for c in creditos:
					if c not in creditos_predocumentados:
						subtotal = c.subtotal(fecha_operacion=fecha_operacion, condonacion=False)
						if remanente >= subtotal:
							cobros.append({
								"credito" : c,
								"subtotal" : subtotal,
							})
							remanente -= subtotal
						creditos_predocumentados.append(c)
						
				nuevo_saldo = remanente	
				cajas = [{
					'subtotal': cobro.importe_cobrado,
					'referencia':'',
					'caja' : caja
				}]
				descripcion = "{} - Cobrado Por - Canal de Pago: {} - Fecha: {}".format(Ingreso.objects.get(consorcio=consorcio(self.request), nombre=cobro.ingreso), Caja.objects.get(id=int(cobro.canal_de_pago)).nombre, cobro.fecha_cobro)
				data_inicial['tipo'] = "Recibo X exp"
				documento = ComprobanteCreator(
					data_inicial=data_inicial,
					data_descripcion=descripcion,
					data_cobros=cobros,
					data_nuevo_saldo=nuevo_saldo,
					data_cajas=cajas
				)
				evaluacion = documento.guardar(masivo=True)
				cobro.documentado = date.today() 
				cobro.save()
				if type(evaluacion) == list:
					messages.error(self.request, evaluacion[0])
				else:
					messages.success(self.request, mensaje_success)
		return redirect('cobranzas')


@method_decorator(group_required('administrativo'), name='dispatch')
class CobrosImportacionWizard(WizardComprobanteManager, SessionWizardView):

	""" Index y registro de conceptos """

	file_storage = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, 'cobros'))

	form_list = [
		('importacion', ImportacionForm),
		('revision', ConfirmacionForm),
	]

	def leer_datos(self, archivo):

		""" Retorna los datos limpios """

		datos = Dataset()
		return datos.load(in_stream=archivo.read(), format='xls')

	def limpiar_datos(self, datos):

		"""
			Retorna un diccionario con diccionarios, uno para ingresos y otro para dominios
			Clave: lo que coloco el usuario
			Valor: El objeto en si
		"""

		# Validacion de columnas
		columnas_necesarias = ['socio', 'fecha', 'importe', 'caja', 'ingreso']
		columnas_archivo = datos.headers
		errores = ['Falta la columna "{}" en el archivo que deseas importar'.format(columna) for columna in columnas_necesarias if not columna in columnas_archivo]
		if errores:
			return errores


		data_socios = set(datos['socio'])
		socios = {}
		for s in data_socios:
			if not s in socios.keys():
				print(s)
				try:
					socios[s] = Socio.objects.get(consorcio=consorcio(self.request), cuit=str(int(s)))
				except:
					pass

		data_cajas = set(datos['caja'])
		cajas = {}
		for c in data_cajas:
			if not c in cajas.keys():
				try:
					cajas[c] = Caja.objects.get(consorcio=consorcio(self.request), id=c)
				except:
					pass

		data_ingresos = datos['ingreso']
		ingresos = {}
		for i in data_ingresos:
			if not i in ingresos.keys():
				try:
					ingresos[i] = Ingreso.objects.get(consorcio=consorcio(self.request), nombre=i)
				except:
					pass

		return {
			'socios': socios,
			'cajas': cajas,
			'ingresos':ingresos,
		}


	def convertirFecha(self, valor):
		inicio_excel = date(1900, 1, 1)
		diferencia = timedelta(days=int(valor)-2)
		dia = (inicio_excel + diferencia)
		return dia

	def hacer_cobros(self, datos, objetos_limpios):

		"""
			Retorna un diccionario con diccionarios, uno para ingresos y otro para dominios
			Clave: lo que coloco el usuario
			Valor: El objeto en si
		"""

		cobros = []
		errores = []

		datos = datos.dict

		fila = 2 # Fila posterior a la de los titulos de las columnas
		for d in datos:
			if d['caja'] and d['socio'] and d['fecha'] and d['importe'] and d['ingreso']:
				try:
					caja = objetos_limpios['cajas'][d['caja']]
					try:
						socio = objetos_limpios['socios'][d['socio']]
						try:
							fecha = self.convertirFecha(d['fecha'])
							try:
								importe = float(d['importe'])
								try: 
									ingreso = objetos_limpios['ingresos'][d['ingreso']]
									cobros.append({
									'codigo_consorcio':consorcio(self.request).id,
									'fecha_cobro':fecha,
									'canal_de_pago':caja,
									'unidad_funcional':socio,
									'importe_cobrado':importe,
									'ingreso':ingreso,
								})
								except:
									errores.append("Linea {}: No se reconoce el ingreso".format(fila))
							except:
								errores.append("Linea {}: Debe escribir un numero en importe".format(fila))
						except:
							errores.append("Linea {}: Debe escribir una fecha valida en fecha".format(fila))
					except:
						errores.append("Linea {}: No se reconoce el socio".format(fila))
				except:
					errores.append("Linea {}: No se reconoce el metodo de cobro".format(fila))


			fila += 1

		return cobros, errores


	def get_template_names(self):
		return [self.TEMPLATES[self.steps.current]]

	def get_context_data(self, form, **kwargs):
		context = super().get_context_data(form=form, **kwargs)
		extension = 'comprobantes/nuevo/Recibo.html'
		peticion = "Carga de Cobros"
		tipo = "Importacion"
		archivo = self.get_cleaned_data_for_step('importacion')
		if archivo:
			archivo = self.get_cleaned_data_for_step('importacion')['archivo']
			datos = self.leer_datos(archivo)
			objetos_limpios = self.limpiar_datos(datos)
		if self.steps.current == 'revision':
			if type(objetos_limpios) == dict:
				cobros, errores = self.hacer_cobros(datos, objetos_limpios)
			else:
				errores = objetos_limpios

		context.update(locals())
		return context

	@transaction.atomic
	def done(self, form_list, **kwargs):
		data_inicial = {
			"punto": consorcio(self.request).contribuyente.points_of_sales.first(),
			"fecha_operacion": None,
			"concepto": None,
			"fecha_factura": None
		}
		archivo = self.get_cleaned_data_for_step('importacion')['archivo']
		datos = self.leer_datos(archivo)
		objetos_limpios = self.limpiar_datos(datos)
		cobros, errores = self.hacer_cobros(datos, objetos_limpios)
		cobrosexp = []
		for cobro in cobros:
			cobrosexp.append(CobroExp(
				codigo_consorcio=cobro['codigo_consorcio'],
				fecha_cobro=cobro['fecha_cobro'],
				canal_de_pago=cobro['canal_de_pago'].id,
				unidad_funcional=cobro['unidad_funcional'].id,
				importe_cobrado=cobro['importe_cobrado'],
				ingreso=cobro['ingreso']			
			))
		CobroExp.objects.bulk_create(cobrosexp)
		messages.success(self.request, "Cobros guardados con exito")
		return redirect('cobranzas')



@method_decorator(group_required('administrativo'), name='dispatch')
class CobrosImportacionTotalesWizard(WizardComprobanteManager, SessionWizardView):
	"""
	Wizard NUEVO: importa totales por socio (sin ingreso),
	setea punto/caja/fecha manualmente y genera Recibos X masivos
	imputando 1) cuotas sociales primero, 2) resto por antigüedad.
	"""
	file_storage = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, 'cobros'))

	form_list = [
		('importacion', ImportacionTotalesForm),
		('parametros', ParametrosTotalesForm),
		('revision', forms.Form),  # Confirmación simple (usa el template)
	]

	TEMPLATES = {
		'importacion': 'comprobantes/nuevo/importacion_totales.html',
		'parametros': 'comprobantes/nuevo/parametros_totales.html',
		'revision'  : 'comprobantes/nuevo/revision_totales.html',
	}

	# ---------- Utilidades de lectura/limpieza ----------
	def leer_datos(self, archivo):
		"""Lee .xlsx y retorna Dataset"""
		datos = Dataset()
		# Intento xlsx, si falla pruebo xls
		try:
			return datos.load(in_stream=archivo.read(), format='xlsx')
		except Exception:
			archivo.seek(0)
			return datos.load(in_stream=archivo.read(), format='xls')

	def _to_decimal(self, val):
		if val in (None, ""):
			raise InvalidOperation("vacío")
		if isinstance(val, (int, float, Decimal)):
			return Decimal(str(val)).quantize(Decimal("0.01"))
		# string
		s = str(val).replace(",", ".").strip()
		return Decimal(s).quantize(Decimal("0.01"))

	def limpiar_totales(self, datos):
		"""
		Espera columnas: socio, importe
		- socio: CUIT del socio (como en tu importador actual)
		- importe: total a cobrar (se agrupa si hay múltiples filas por socio)
		Retorna (agrupados, socios_mapeados, errores)
		"""
		columnas_necesarias = ['socio', 'importe']
		columnas_archivo = datos.headers
		faltantes = [c for c in columnas_necesarias if c not in columnas_archivo]
		if faltantes:
			return None, None, [f'Falta la columna "{c}" en el archivo' for c in faltantes]

		cons = consorcio(self.request)
		errores = []
		# Agrupar importes por socio
		agrupados = {}  # cuit_str -> Decimal total
		socios_mapeados = {}  # cuit_str -> Socio

		for i, row in enumerate(datos.dict, start=2):  # fila 2 = primera luego de encabezados
			cuit_raw = row.get('socio')
			imp_raw = row.get('importe')
			if not cuit_raw:
				errores.append(f"Fila {i}: faltó CUIT en 'socio'")
				continue
			try:
				# como en tu importador: get por cuit normalizado a int -> str
				cuit_str = str(int(cuit_raw))
			except Exception:
				errores.append(f"Fila {i}: 'socio' no parece CUIT válido ({cuit_raw})")
				continue
			try:
				imp = self._to_decimal(imp_raw)
			except Exception:
				errores.append(f"Fila {i}: 'importe' inválido ({imp_raw})")
				continue

			agrupados[cuit_str] = (agrupados.get(cuit_str, Decimal("0.00")) + imp).quantize(Decimal("0.01"))
			if cuit_str not in socios_mapeados:
				try:
					socios_mapeados[cuit_str] = Socio.objects.get(consorcio=cons, cuit=cuit_str)
				except Socio.DoesNotExist:
					errores.append(f"Fila {i}: no se encontró Socio con CUIT {cuit_str} en el consorcio")

		return agrupados, socios_mapeados, errores

	# ---------- Lógica de priorización / imputación ----------
	def ordenar_creditos_por_antiguedad(self, qs):
		"""
		Orden por antigüedad: vencimiento, luego periodo, luego fecha, luego id
		(algunos pueden tener nulos, por eso usamos tuplas seguras)
		"""
		def key(c):
			vto = c.vencimiento or date.min
			per = c.periodo or date.min
			fec = c.fecha or date.min
			return (vto, per, fec, c.id)
		return sorted(qs, key=key)

	def obtener_creditos_priorizados(self, socio, fecha_operacion):
		"""
		Devuelve lista ordenada:
		  1) cuotas sociales (Ingreso.es_cuota_social=True) por antigüedad
		  2) resto por antigüedad
		Solo créditos con saldo > 0 a la fecha_operacion y no finalizados a esa fecha.
		"""
		cons = consorcio(self.request)
		base = (Credito.objects
				.filter(consorcio=cons, socio=socio, padre__isnull=True)
				.select_related('ingreso'))

		# Filtrado por saldo a nivel Python (método saldo_en_fecha)
		vivos = [c for c in base if c.saldo_en_fecha(fecha_operacion) > Decimal('0.00')]

		sociales = [c for c in vivos if getattr(c.ingreso, 'es_cuota_social', False)]
		resto    = [c for c in vivos if not getattr(c.ingreso, 'es_cuota_social', False)]

		sociales = self.ordenar_creditos_por_antiguedad(sociales)
		resto    = self.ordenar_creditos_por_antiguedad(resto)

		return sociales + resto

	def imputar(self, socio, monto, fecha_operacion, aceptar_parciales=False):
		"""
		Devuelve (cobros, remanente)
		cobros = [{"credito": c, "subtotal": Decimal}, ...]
		Remanente si no alcanza para un crédito completo (o si no aceptamos parciales).
		"""
		rem = Decimal(monto)
		cobros = []
		for c in self.obtener_creditos_priorizados(socio, fecha_operacion):
			if rem <= 0:
				break
			subtotal = c.subtotal(fecha_operacion=fecha_operacion, condonacion=False)
			if subtotal <= 0:
				continue

			if rem >= subtotal:
				cobros.append({"credito": c, "subtotal": subtotal})
				rem -= subtotal
			else:
				if aceptar_parciales:
					cobros.append({"credito": c, "subtotal": rem})
					rem = Decimal('0.00')
				else:
					# no aceptamos parcial: dejamos remanente tal cual y pasamos al siguiente socio
					break
		return cobros, rem

	# ---------- Wizard plumbing ----------
	def get_template_names(self):
		return [self.TEMPLATES[self.steps.current]]

	def get_form_kwargs(self, step):
		kwargs = super().get_form_kwargs(step)
		if step == 'parametros':
			kwargs['consorcio'] = consorcio(self.request)
		return kwargs

	def get_context_data(self, form, **kwargs):
		context = super().get_context_data(form=form, **kwargs)
		extension = 'comprobantes/nuevo/Recibo.html'
		tipo = "Recibo X masivo"

		archivo_data = self.get_cleaned_data_for_step('importacion')
		if archivo_data:
			datos = self.leer_datos(archivo_data['archivo'])
			agrupados, socios_mapeados, errores = self.limpiar_totales(datos)
		else:
			agrupados = socios_mapeados = errores = None

		preview = []
		if self.steps.current == 'revision' and agrupados and socios_mapeados:
			params = self.get_cleaned_data_for_step('parametros') or {}
			caja = params.get('caja')
			punto = params.get('punto')
			fecha_op = params.get('fecha_operacion') or date.today()
			aceptar_parciales = bool(params.get('aceptar_parciales') or False)

			# Armar pre-visualización por socio
			for cuit_str, total in agrupados.items():
				socio = socios_mapeados.get(cuit_str)
				if not socio:
					continue
				cobros, rem = self.imputar(
					socio=socio,
					monto=total,
					fecha_operacion=fecha_op,
					aceptar_parciales=aceptar_parciales,
				)
				preview.append({
					"socio": socio,
					"cuit": cuit_str,
					"importe_total": total,
					"items": cobros,            # lista de {"credito", "subtotal"}
					"remanente": rem,
					"caja": caja,
					"punto": punto,
					"fecha": fecha_op,
				})

		context.update({
			"extension": extension,
			"tipo": tipo,
			"agrupados": agrupados,
			"socios_mapeados": socios_mapeados,
			"errores": errores,
			"preview": preview,
		})
		return context

	@transaction.atomic
	def done(self, form_list, **kwargs):
		# Releer archivo
		archivo = self.get_cleaned_data_for_step('importacion')['archivo']
		datos = self.leer_datos(archivo)
		agrupados, socios_mapeados, errores = self.limpiar_totales(datos)

		if not agrupados or not socios_mapeados:
			messages.error(self.request, "No hay datos válidos para procesar.")
			return redirect('cobranzas')

		params = self.get_cleaned_data_for_step('parametros') or {}
		caja = params.get('caja')
		punto = params.get('punto')
		fecha_op = params.get('fecha_operacion') or date.today()
		aceptar_parciales = bool(params.get('aceptar_parciales') or False)
		descripcion_base = params.get('descripcion_base') or ""

		cons = consorcio(self.request)
		ok, errs = 0, 0

		for cuit_str, total in agrupados.items():
			socio = socios_mapeados.get(cuit_str)
			if not socio:
				continue

			cobros, rem = self.imputar(
				socio=socio,
				monto=total,
				fecha_operacion=fecha_op,
				aceptar_parciales=aceptar_parciales,
			)

			data_inicial = {
				"punto": punto,
				"fecha_operacion": fecha_op,
				"concepto": None,
				"fecha_factura": None,
				"tipo": "Recibo X masivo",
				"socio": socio,
			}
			data_cajas = [{
				"subtotal": total,
				"referencia": "",
				"caja": caja,
			}]
			desc = (descripcion_base or "Cobro total importado")
			descripcion = f"{desc} - Socio: {socio} - Fecha: {fecha_op} - Caja: {caja}"

			documento = ComprobanteCreator(
				data_inicial=data_inicial,
				data_descripcion=descripcion,
				data_cobros=cobros,
				data_nuevo_saldo=(rem if rem > 0 else None),
				data_cajas=data_cajas,
			)
			evaluacion = documento.guardar(masivo=True)
			if isinstance(evaluacion, list):
				errs += 1
				messages.error(self.request, evaluacion[0])
			else:
				ok += 1

		if ok:
			messages.success(self.request, f"Se generaron {ok} recibos masivos.")
		if errs:
			messages.warning(self.request, f"{errs} recibos no pudieron generarse. Revisá los mensajes de error.")

		return redirect('cobranzas')


SESSION_KEY_IDS = "rcx_desde_creditos_ids"
@method_decorator(group_required('administrativo'), name='dispatch')
class RCXDesdeCreditosWizard(WizardComprobanteManager, SessionWizardView):
    """
    Paso 1: parámetros (punto, fecha, caja, etc.)
    Paso 2: confirmación (preview de lo que se va a generar)
    Luego genera 1 recibo por socio con los créditos seleccionados.
    """
    form_list = [
        ('parametros', ParametrosDesdeCredForm),   # ya la tenés
        ('confirmacion', forms.Form),              # pantalla de confirmación simple
    ]

    TEMPLATES = {
        'parametros': 'comprobantes/nuevo/parametros_desde_creditos.html',
        'confirmacion': 'comprobantes/nuevo/confirmacion_desde_creditos.html',
    }

    # ---------- Hook clave para evitar el error del ManagementForm ----------
    def post(self, request, *args, **kwargs):
        """
        Si llega un POST desde el listado (con creditos[]), guardo esos IDs en sesión
        y redirijo con GET al wizard. Así el wizard ya renderiza su propio ManagementForm.
        """
        if 'creditos[]' in request.POST and request.POST.getlist('creditos[]'):
            ids = request.POST.getlist('creditos[]')
            request.session['rcx_desde_creditos_ids'] = ids
            return redirect('rcx-desde-creditos')
        # Si ya estoy dentro del wizard (tiene current_step), sigo flujo normal
        return super().post(request, *args, **kwargs)

    # ---------- Utilidades ----------
    def get_template_names(self):
        return [self.TEMPLATES[self.steps.current]]

    def get_selected_creditos(self):
        """
        Obtiene los créditos elegidos (guardados en sesión por el POST inicial).
        """
        ids = self.request.session.get('rcx_desde_creditos_ids', [])
        if not ids:
            return Credito.objects.none()
        # Podés filtrar por consorcio(self.request) si querés acotar
        return (Credito.objects
                .filter(id__in=ids)
                .select_related('socio', 'ingreso', 'factura'))

    def imputar_credito(self, credito, fecha_op, aceptar_parciales):
        """
        Devuelve el subtotal a cobrar para este crédito según fecha.
        Si aceptar_parciales=False, cobra el total del subtotal de ese crédito
        o nada si no alcanza (pero como no tenemos el monto por socio acá,
        usamos siempre el subtotal completo del crédito).
        """
        subtotal = credito.subtotal(fecha_operacion=fecha_op, condonacion=False)
        # Si querés lógica más fina de parciales por crédito, ajustá acá.
        return max(Decimal('0.00'), Decimal(subtotal or 0))

    # ---------- Contexto de cada paso ----------
    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        extension = 'comprobantes/nuevo/Recibo.html'
        tipo = "Recibo X"
        creditos = self.get_selected_creditos()

        if self.steps.current == 'confirmacion':
            params = self.get_cleaned_data_for_step('parametros') or {}
            fecha_op = params.get('fecha_operacion') or now().date()
            aceptar_parciales = bool(params.get('aceptar_parciales') or False)

            # Armar preview agrupado por socio
            preview = []
            por_socio = defaultdict(list)
            for c in creditos:
                por_socio[c.socio_id].append(c)

            for socio_id, lista in por_socio.items():
                socio = lista[0].socio
                items = []
                total = Decimal('0.00')
                for cred in lista:
                    sub = self.imputar_credito(cred, fecha_op, aceptar_parciales)
                    if sub > 0:
                        items.append({'credito': cred, 'subtotal': sub})
                        total += sub

                preview.append({
                    'socio': socio,
                    'items': items,
                    'total': total,
                })

            context.update({
                'preview': preview,
                'fecha_op': fecha_op,
                'extension': extension,
                'tipo': tipo,
            })
        else:
            context.update({
                'extension': extension,
                'tipo': tipo,
                'creditos': creditos,
            })
        return context

    def get_form_kwargs(self, step):
        kwargs = super().get_form_kwargs(step)
        if step == 'parametros':
            kwargs['consorcio'] = consorcio(self.request)
        return kwargs

    # ---------- Ejecución ----------
    @transaction.atomic
    def done(self, form_list, **kwargs):
        params = self.get_cleaned_data_for_step('parametros') or {}
        punto = params.get('punto')
        caja = params.get('caja')
        fecha_op = params.get('fecha_operacion') or now().date()
        desc_base = params.get('descripcion_base') or ""
        aceptar_parciales = bool(params.get('aceptar_parciales') or False)

        creditos = self.get_selected_creditos()
        if not creditos.exists():
            messages.error(self.request, "No hay créditos seleccionados.")
            return redirect('cobranzas')

        # Agrupar por socio
        por_socio = defaultdict(list)
        for c in creditos:
            por_socio[c.socio_id].append(c)

        ok = err = 0
        for socio_id, lista in por_socio.items():
            socio = lista[0].socio

            # Armo data_cobros con los subtotales calculados por crédito
            data_cobros = []
            total_recibo = Decimal('0.00')
            for cred in lista:
                sub = self.imputar_credito(cred, fecha_op, aceptar_parciales)
                if sub > 0:
                    data_cobros.append({'credito': cred, 'subtotal': sub})
                    total_recibo += sub

            if total_recibo <= 0:
                continue

            data_inicial = {
                'punto': punto,
                'socio': socio,
                'fecha_operacion': fecha_op,
                'condonacion': False,
                'tipo': 'Recibo X',
            }
            data_cajas = [{
                'caja': caja,
                'referencia': '',
                'subtotal': total_recibo,
            }]
            descripcion = f"{desc_base} - Socio: {socio} - Fecha: {fecha_op}"

            documento = ComprobanteCreator(
                data_inicial=data_inicial,
                data_descripcion=descripcion,
                data_cobros=data_cobros,
                data_nuevo_saldo=None,
                data_cajas=data_cajas,
            )
            evaluacion = documento.guardar(masivo=True)
            if isinstance(evaluacion, list):
                err += 1
                messages.error(self.request, evaluacion[0])
            else:
                ok += 1

        # Limpio la selección para no reusar por error
        self.request.session.pop('rcx_desde_creditos_ids', None)

        if ok:
            messages.success(self.request, f"Se generaron {ok} recibos.")
        if err:
            messages.warning(self.request, f"{err} recibos no pudieron generarse. Revisá los mensajes.")
        return redirect('cobranzas')