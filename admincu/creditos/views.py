from django.shortcuts import render, redirect
from datetime import timedelta, date
from django.contrib import messages
from django.urls import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.db import transaction
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Count, Sum
from django.views import generic
from django.utils.decorators import method_decorator
from formtools.wizard.views import SessionWizardView
from functools import partial, wraps
from django.core.files.storage import FileSystemStorage
from tablib import Dataset
from django.conf import settings
from decimal import Decimal


from admincu.funciones import *
from admincu.generic import OrderQS
from consorcios.models import *
from arquitectura.models import *
from arquitectura.forms import *
from .models import *
from .forms import *
from contabilidad.asientos.funciones import asiento_liq
from .manager import *
from .filters import *
from comprobantes.funciones import *
from reportes.models import Cierre

envioAFIP = 'Liquidacion guardada. En los proximos minutos se enviara la información a AFIP. Te informaremos los resultados.'


@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class Index(OrderQS):

	""" Index de liquidaciones y creditos """

	model = Liquidacion
	filterset_class = LiquidacionFilter
	template_name = 'creditos/index.html'
	paginate_by = 10

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		# Saldo total de creditos pendientesdo total de creditos pendientes
		saldo = Credito.objects.filter(consorcio=consorcio(self.request), fin__isnull=True, liquidacion__estado="confirmado").aggregate(saldo=Sum('capital'))['saldo']
		# Ultimo periodo
		ultima_liquidacion = Liquidacion.objects.filter(consorcio=consorcio(self.request), estado='confirmado').order_by('-id').first()
		context.update(locals())
		return context


@method_decorator(group_required('socio'), name='dispatch')
class IndexSocio(OrderQS):

	"""
		Index para el socio.
	"""

	model = Credito
	template_name = "creditos/socio/index.html"
	filterset_class = CreditoFilterSocio
	paginate_by = 100

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context['bloqueo'] = bloqueador(self.get_queryset())
		context['bloqueo_descuento'] = bloqueador_descuentos(self.get_queryset())
		context['hoy'] = date.today()
		context['creditos'] = self.get_queryset()
		context['expensas_pagas'] = consorcio(self.request).exp.first()
		context['mercado_pago'] = consorcio(self.request).mercado_pago
		return context

	def get_queryset(self):
		nada = super().get_queryset(capital__lt=0)

		from itertools import chain
		socio = self.request.user.socio_set.first()
		creditos_dominio_ocupante = Credito.objects.filter(
			padre__isnull=True,
			liquidacion__estado="confirmado",
			dominio__in=socio.socio.all()
		).order_by('-id')
		creditos_dominio_propietario = Credito.objects.filter(
			padre__isnull=True,
			liquidacion__estado="confirmado",
			dominio__in=socio.propietario.all()
		).order_by('-id')
		creditos_socio_sin_dominio = Credito.objects.filter(
			padre__isnull=True,
			liquidacion__estado="confirmado",
			dominio__isnull=True,
			socio=socio
		).order_by('-id')
		creditos = list(chain(creditos_dominio_ocupante, creditos_dominio_propietario, creditos_socio_sin_dominio))
		return creditos


class WizardLiquidacionManager:

	""" Administrador de liquidaciones """

	TEMPLATES = {
		"inicial": "creditos/nuevo/inicial.html",
		"individuales": "creditos/nuevo/individuales.html",
		"masivo": "creditos/nuevo/masivo.html",
		"grupo": "creditos/nuevo/masivo.html",
		"plazos": "creditos/nuevo/plazos.html",
		"confirmacion": "creditos/nuevo/confirmacion.html",
		"preconceptos": "creditos/nuevo/preconceptos.html",
		"conceptos": "creditos/nuevo/conceptos.html",
		"importacion": "creditos/nuevo/importacion.html",
		"revision": "creditos/nuevo/revision.html",
		"cuota_social": "creditos/nuevo/cuota_social.html",
		"cuota_convenio":"creditos/nuevo/cuota_convenio.html"
	}

	def obtener_accesorios(self, ingresos):
		fecha_operacion = self.get_cleaned_data_for_step('inicial')['fecha_operacion']
		accesorios = Accesorio.objects.filter(ingreso__in=ingresos, finalizacion__isnull=True, plazo__isnull=False).distinct()
		for a in accesorios:
			a.fecha = fecha_operacion + timedelta(days=a.plazo)
		return accesorios

	def hacer_creditos(self, tipo):

		"""
		Crea lista de DICCIONARIOS de creditos. No lista de objetos
		Para poder utilizar mejor en manager.py
		"""

		data_inicial = self.get_cleaned_data_for_step('inicial')
		data_cuota_social = self.get_cleaned_data_for_step('cuota_social')
		data_cuota_convenio = self.get_cleaned_data_for_step('cuota_convenio')
		data_creditos = self.get_cleaned_data_for_step(tipo)
		data_plazos = self.get_cleaned_data_for_step('plazos')
		creditos = []
		socios = Socio.objects.filter(consorcio=consorcio(self.request), es_socio=True, baja__isnull=True, nombre_servicio_mutual__isnull=True)
		dominios = Dominio.objects.filter(consorcio=consorcio(self.request), padre__isnull=True, socio__isnull=False)
		q_socios = dominios.count()
		q_dominios = dominios.count()
		total_m2 = dominios.aggregate(suma=Sum('superficie_total'))['suma']

		if tipo == "individuales":
			for d in data_creditos:
				if d:
					if d['subtotal']:
						credito = {
							'consorcio':consorcio(self.request),
							'periodo':data_inicial['fecha_operacion'],
							'ingreso':d['ingreso'],
							'capital':d['subtotal'],
							'detalle': d['detalle'],
						}
						# Establecer o cliente o dominio
						destinatario, pk = d['destinatario'].split('-')
						objeto_destinatario = eval(destinatario.capitalize()).objects.get(pk=pk)

						if destinatario == "dominio":
							credito['dominio'] = objeto_destinatario
							credito['socio'] = objeto_destinatario.socio
						elif destinatario == "socio":
							credito['socio'] = objeto_destinatario
							credito['dominio'] = None
						creditos.append(credito)

		elif tipo == "masivo":
			for d in data_creditos:
				if d:
					if d['subtotal']:
						base_credito = {
							'consorcio':consorcio(self.request),
							'periodo':data_inicial['fecha_operacion'],
							'ingreso':d['ingreso'],
						}
						for socio in socios:
							credito = base_credito.copy()
							credito['dominio'] = None
							credito['socio'] = socio

							if d['distribucion'] == "total_socio":
								credito['capital'] = round(d['subtotal']/q_socios,2)
							elif d['distribucion'] == "socio":
								credito['capital'] = round(d['subtotal'],2)
							creditos.append(credito)

		elif tipo == "grupo":
			grupos = Tipo_asociado.objects.filter(id__in=data_inicial['tipo_asociado'])
			todos_los_socios_de_los_grupos = Socio.objects.filter(tipo_asociado__in=grupos,nombre_servicio_mutual__isnull=True,baja__isnull=True)
			q_socios_de_los_grupos = todos_los_socios_de_los_grupos.count()
			for d in data_creditos:
				if d:
					if d['subtotal']:
						base_credito = {
							'consorcio':consorcio(self.request),
							'periodo':data_inicial['fecha_operacion'],
							'ingreso':d['ingreso'],
						}
						for socio in todos_los_socios_de_los_grupos:
							credito = base_credito.copy()
							credito['socio'] = socio
							if d['distribucion'] == "total_socio":
								credito['capital'] = round(d['subtotal']/q_socios_de_los_grupos,2)
							elif d['distribucion'] == "socio":
								credito['capital'] = round(d['subtotal'],2)
							creditos.append(credito)

		elif tipo == "cuota_social":
			for d in data_cuota_social:
				if d:
					if d['subtotal']:
						base_credito = {
							'consorcio':consorcio(self.request),
							'periodo':data_inicial['fecha_operacion'],
							'ingreso':Ingreso.objects.get(consorcio=consorcio(self.request),es_cuota_social=True),
						}
						for socio in Socio.objects.filter(tipo_asociado=d['categorias_asociado'],nombre_servicio_mutual__isnull=True,baja__isnull=True):
							credito = base_credito.copy()
							credito['socio'] = socio
							credito['capital'] = round(d['subtotal'],2)
							creditos.append(credito)

		elif tipo == "cuota_convenio":
			for d in data_cuota_convenio:
				if d:
					if d['subtotal']:
						base_credito = {
							'consorcio':consorcio(self.request),
							'periodo':data_inicial['fecha_operacion'],
							'ingreso':Ingreso.objects.get(consorcio=consorcio(self.request),es_cuota_social=True),
						}
						for socio in Socio.objects.filter(convenio=d['convenios'],nombre_servicio_mutual__isnull=True,baja__isnull=True):
							credito = base_credito.copy()
							credito['socio'] = socio
							credito['capital'] = round(d['subtotal'],2)
							creditos.append(credito)






		return creditos

	def hacer_plazos(self):

		""" Retorna una lista de diccionarios LIMPIO con "accesorio" y "plazo" """

		data_plazos = self.get_cleaned_data_for_step('plazos')
		plazos = []
		for d in data_plazos:
			if d:
				data = {
					'accesorio': Accesorio.objects.get(pk=d['accesorio']),
					'plazo': d['plazo']
				}
				plazos.append(data)
		return plazos

	def hacer_preconceptos(self):

		""" Retorna un QUERYSET con OBJETOS de tipo Credito """

		return Credito.objects.filter(id__in=self.get_cleaned_data_for_step('preconceptos')['conceptos'])

	def hacer_liquidacion(self, tipo, receipt_type):

		""" Retorna una lista de diccionarios a traves del manager para crear liquidacion """

		data_inicial = self.get_cleaned_data_for_step('inicial')
		try:
			fecha_factura = data_inicial['fecha_factura']
		except:
			data_inicial['fecha_factura'] = data_inicial['fecha_operacion']		
		data_creditos = self.hacer_creditos(tipo)
		preconceptos = None if tipo != "masivo" else self.hacer_preconceptos()
		data_plazos = self.hacer_plazos()
		
		liquidacion = LiquidacionCreator(
				data_inicial=data_inicial,
				data_creditos=data_creditos,
				data_plazos=data_plazos,
				preconceptos=preconceptos,
				receipt_type=receipt_type
			)			
		return liquidacion

@method_decorator(group_required('administrativo'), name='dispatch')
class CuotaSocialWizard(WizardLiquidacionManager, SessionWizardView):

	form_list = [
		('inicial', InicialForm),
		('cuota_social', CuotaSocialForm),
		('plazos', PlazoFormSet),
		('confirmacion', ConfirmacionForm)
	]

	def get_template_names(self):
		return [self.TEMPLATES[self.steps.current]]

	def get_context_data(self, form, **kwargs):
		context = super().get_context_data(form=form, **kwargs)
		tipo = "Cuota Social"
		peticion ="liquidacion de comprobantes RG-1415"
		if self.steps.current == 'plazos':
			data_individuales = self.get_cleaned_data_for_step('cuota_social')
			ingresos = [Ingreso.objects.get(consorcio=consorcio(self.request),es_cuota_social=True)]
			accesorios = self.obtener_accesorios(ingresos)

		elif self.steps.current == 'confirmacion':
			data_plazos = self.hacer_plazos()
			liquidacion = self.hacer_liquidacion('cuota_social', receipt_type="101")

		context.update(locals())

		return context


	def get_form_kwargs(self, step):
		kwargs = super().get_form_kwargs()
		if step in ["inicial", "cuota_social"]:
			kwargs.update({
					'consorcio': consorcio(self.request)
				})
		if step == "confirmacion":
			liquidacion = self.hacer_liquidacion('cuota_social', receipt_type="101")
			mostrar = len(liquidacion.listar_documentos()) == 1
			kwargs.update({
					'mostrar': mostrar
				})
		return kwargs

	def get_form(self, step=None, data=None, files=None):
		form = super().get_form(step, data, files)
		formset = False
		if data:
			if 'cuota_social' in data['cuota_social_wizard-current_step']:
				formset = True
		if step == "cuota_social":
			formset = True

		if formset:
			formset = formset_factory(wraps(CuotaSocialForm)(partial(CuotaSocialForm, consorcio=consorcio(self.request))), extra=1)
			form = formset(prefix='cuota_social', data=data)
		return form

	@transaction.atomic
	def done(self, form_list, **kwargs):
		liquidacion = self.hacer_liquidacion('cuota_social', receipt_type="101")
		liquidacion = liquidacion.guardar()
		contado = self.get_cleaned_data_for_step('confirmacion')['confirmacion']
		if contado:
			factura = liquidacion.factura_set.first()
			creditos = factura.incorporar_creditos()
			factura.validar_factura()

			liquidacion.confirmar()
			if liquidacion.estado == "confirmado":
				return redirect('nuevo-rcx-factura', pk=factura.pk)
			else:
				messages.error(self.request, factura.observacion)
		else:
			messages.success(self.request, envioAFIP)
		return redirect('recursos')

@method_decorator(group_required('administrativo'), name='dispatch')
class CuotaConvenioWizard(WizardLiquidacionManager, SessionWizardView):

    form_list = [
        ('inicial', InicialForm),
        ('cuota_convenio', CuotaConvenioForm),
        ('plazos', PlazoFormSet),
        ('confirmacion', ConfirmacionForm)
    ]

    def get_template_names(self):
        return [self.TEMPLATES[self.steps.current]]

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        tipo = "Cuota por Convenio"
        peticion = "liquidacion de comprobantes RG-1415"
        if self.steps.current == 'plazos':
            data_individuales = self.get_cleaned_data_for_step('cuota_convenio')
            ingresos = [Ingreso.objects.get(consorcio=consorcio(self.request), es_cuota_social=True)]
            accesorios = self.obtener_accesorios(ingresos)

        elif self.steps.current == 'confirmacion':
            data_plazos = self.hacer_plazos()
            liquidacion = self.hacer_liquidacion('cuota_convenio', receipt_type="101")

        context.update(locals())
        return context

    def get_form_kwargs(self, step):
        kwargs = super().get_form_kwargs()
        if step in ["inicial", "cuota_convenio"]:
            kwargs.update({
                'consorcio': consorcio(self.request)
            })
        if step == "confirmacion":
            liquidacion = self.hacer_liquidacion('cuota_convenio', receipt_type="101")
            mostrar = len(liquidacion.listar_documentos()) == 1
            kwargs.update({
                'mostrar': mostrar
            })
        return kwargs

    def get_form(self, step=None, data=None, files=None):
        form = super().get_form(step, data, files)
        formset = False
        if data:
            if 'cuota_convenio' in data['cuota_convenio_wizard-current_step']:
                formset = True
        if step == "cuota_convenio":
            formset = True

        if formset:
            formset = formset_factory(
                wraps(CuotaConvenioForm)(partial(CuotaConvenioForm, consorcio=consorcio(self.request))), 
                extra=1
            )
            form = formset(prefix='cuota_convenio', data=data)
        return form

    @transaction.atomic
    def done(self, form_list, **kwargs):
        liquidacion = self.hacer_liquidacion('cuota_convenio', receipt_type="101")
        liquidacion = liquidacion.guardar()
        contado = self.get_cleaned_data_for_step('confirmacion')['confirmacion']
        if contado:
            factura = liquidacion.factura_set.first()
            creditos = factura.incorporar_creditos()
            factura.validar_factura()

            liquidacion.confirmar()
            if liquidacion.estado == "confirmado":
                return redirect('nuevo-rcx-factura', pk=factura.pk)
            else:
                messages.error(self.request, factura.observacion)
        else:
            messages.success(self.request, envioAFIP)
        return redirect('recursos')



@method_decorator(group_required('administrativo'), name='dispatch')
class IndividualesWizard(WizardLiquidacionManager, SessionWizardView):

	form_list = [
		('inicial', InicialForm),
		('individuales', IndividualesForm),
		('plazos', PlazoFormSet),
		('confirmacion', ConfirmacionForm)
	]

	def get_template_names(self):
		return [self.TEMPLATES[self.steps.current]]

	def get_context_data(self, form, **kwargs):
		context = super().get_context_data(form=form, **kwargs)
		tipo = "Individuales"
		if self.steps.current == 'plazos':
			data_individuales = self.get_cleaned_data_for_step('individuales')
			ingresos = set([data['ingreso'] for data in data_individuales if data])
			accesorios = self.obtener_accesorios(ingresos)

		elif self.steps.current == 'confirmacion':
			data_plazos = self.hacer_plazos()
			liquidacion = self.hacer_liquidacion('individuales', receipt_type="11")

		context.update(locals())

		return context


	def get_form_kwargs(self, step):
		kwargs = super().get_form_kwargs()
		if step in ["inicial", "individuales"]:
			kwargs.update({
					'consorcio': consorcio(self.request)
				})
		if step == "confirmacion":
			liquidacion = self.hacer_liquidacion('individuales', receipt_type="11")
			mostrar = len(liquidacion.listar_documentos()) == 1
			kwargs.update({
					'mostrar': mostrar
				})
		return kwargs

	def get_form(self, step=None, data=None, files=None):
		form = super().get_form(step, data, files)
		formset = False
		if data:
			if 'individuales' in data['individuales_wizard-current_step']:
				formset = True
		if step == "individuales":
			formset = True

		if formset:
			formset = formset_factory(wraps(IndividualesForm)(partial(IndividualesForm, consorcio=consorcio(self.request))), extra=1)
			form = formset(prefix='individuales', data=data)
		return form

	@transaction.atomic
	def done(self, form_list, **kwargs):
		liquidacion = self.hacer_liquidacion('individuales', receipt_type="11")
		liquidacion = liquidacion.guardar()
		contado = self.get_cleaned_data_for_step('confirmacion')['confirmacion']
		if contado:
			factura = liquidacion.factura_set.first()
			creditos = factura.incorporar_creditos()
			factura.validar_factura()

			liquidacion.confirmar()
			if liquidacion.estado == "confirmado":
				return redirect('nuevo-rcx-factura', pk=factura.pk)
			else:
				messages.error(self.request, factura.observacion)
		else:
			messages.success(self.request, envioAFIP)
		return redirect('recursos')






@method_decorator(group_required('administrativo'), name='dispatch')
class RecursoWizard(WizardLiquidacionManager, SessionWizardView):

	form_list = [
		('inicial', InicialForm),
		('individuales', IndividualesRecursoForm),
		('plazos', PlazoFormSet),
		('confirmacion', ConfirmacionForm)
	]

	def get_template_names(self):
		return [self.TEMPLATES[self.steps.current]]

	def get_context_data(self, form, **kwargs):
		context = super().get_context_data(form=form, **kwargs)
		peticion = 'Carga de Recursos'
		tipo = "Provenientes de servicios mutuales"
		peticion2 = "Carga de recursos"		
		if self.steps.current == 'plazos':
			data_individuales = self.get_cleaned_data_for_step('individuales')
			ingresos = set([data['ingreso'] for data in data_individuales if data])
			accesorios = self.obtener_accesorios(ingresos)

		elif self.steps.current == 'confirmacion':
			data_plazos = self.hacer_plazos()
			liquidacion = self.hacer_liquidacion('individuales',receipt_type="104")

		context.update(locals())

		return context

	def get_form_kwargs(self, step):
		kwargs = super().get_form_kwargs()
		if step == "individuales":
				kwargs.update({
				'consorcio': consorcio(self.request),
				})
		if step == "inicial":
			kwargs.update({
				'consorcio': consorcio(self.request),
				'rename_factura': True,
				})
		if step == "confirmacion":
			liquidacion = self.hacer_liquidacion('individuales', receipt_type="104")
			mostrar = len(liquidacion.listar_documentos()) == 1
			kwargs.update({
					'mostrar': mostrar,
				})
		return kwargs

	def get_form(self, step=None, data=None, files=None):
		form = super().get_form(step, data, files)
		formset = False
		if data:
			if 'individuales' in data['recurso_wizard-current_step']:
				formset = True
		if step == "individuales":
			formset = True

		if formset:
			formset = formset_factory(wraps(IndividualesRecursoForm)(partial(IndividualesRecursoForm, consorcio=consorcio(self.request))), extra=1)
			form = formset(prefix='individuales', data=data)
		return form

	@transaction.atomic
	def done(self, form_list, **kwargs):
		liquidacion = self.hacer_liquidacion('individuales', receipt_type="104")
		liquidacion = liquidacion.guardar()
		contado = self.get_cleaned_data_for_step('confirmacion')['confirmacion']
		if contado:
			factura = liquidacion.factura_set.first()
			creditos = factura.incorporar_creditos()
			factura.validar_factura()

			liquidacion.confirmar()
			if liquidacion.estado == "confirmado":
				return redirect('nuevo-rcx-factura', pk=factura.pk)
			else:
				messages.error(self.request, factura.observacion)
		else:
			messages.success(self.request, envioAFIP)
		return redirect('recursos')




@method_decorator(group_required('administrativo'), name='dispatch')
class MasivoWizard(WizardLiquidacionManager, SessionWizardView):

	form_list = [
		('inicial', InicialForm),
		('masivo', MasivoFormSet),
		('plazos', PlazoFormSet),
		('preconceptos', PreConceptoForm),
		('confirmacion', ConfirmacionForm)
	]

	def get_template_names(self):
		return [self.TEMPLATES[self.steps.current]]

	def get_context_data(self, form, **kwargs):
		context = super().get_context_data(form=form, **kwargs)
		tipo = "Masivo"
		data_masivo = self.get_cleaned_data_for_step('masivo')
		if data_masivo:
			ingresos = set([data['ingreso'] for data in data_masivo if data])
			accesorios = self.obtener_accesorios(ingresos)


		if self.steps.current == 'confirmacion':
			data_preconceptos = self.hacer_preconceptos()
			data_plazos = self.hacer_plazos()
			liquidacion = self.hacer_liquidacion('masivo', receipt_type="11")

		context.update(locals())

		return context


	def get_form_kwargs(self, step):
		kwargs = super().get_form_kwargs()
		if step in ["inicial", "preconceptos"]:
			kwargs.update({
					'consorcio': consorcio(self.request)
				})
		return kwargs

	def get_form(self, step=None, data=None, files=None):
		form = super().get_form(step, data, files)
		formset = False
		if data:
			if 'masivo' in data['masivo_wizard-current_step']:
				formset = True
		if step == "masivo":
			formset = True

		if formset:
			formset = formset_factory(wraps(MasivoForm)(partial(MasivoForm, consorcio=consorcio(self.request))), extra=1)
			form = formset(prefix='masivo', data=data)
		return form

	@transaction.atomic
	def done(self, form_list, **kwargs):
		liquidacion = self.hacer_liquidacion('masivo', receipt_type="11")
		liquidacion = liquidacion.guardar()
		messages.success(self.request, envioAFIP)
		return redirect('recursos')


@method_decorator(group_required('administrativo'), name='dispatch')
class GrupoWizard(WizardLiquidacionManager, SessionWizardView):

	form_list = [
		('inicial', InicialForm),
		('grupo', MasivoFormSet),
		('plazos', PlazoFormSet),
		('confirmacion', ConfirmacionForm)
	]

	def get_template_names(self):
		return [self.TEMPLATES[self.steps.current]]

	def get_context_data(self, form, **kwargs):
		context = super().get_context_data(form=form, **kwargs)
		tipo = "Por Grupos"
		data_grupo = self.get_cleaned_data_for_step('grupo')
		if data_grupo:
			ingresos = set([data['ingreso'] for data in data_grupo if data])
			accesorios = self.obtener_accesorios(ingresos)

		if self.steps.current == 'confirmacion':
			data_plazos = self.hacer_plazos()
			liquidacion = self.hacer_liquidacion('grupo', receipt_type="11")

		context.update(locals())

		return context


	def get_form_kwargs(self, step):
		kwargs = super().get_form_kwargs()
		if step == "inicial":
			kwargs.update({
					'consorcio': consorcio(self.request),
					'ok_grupos': True,
				})
		return kwargs

	def get_form(self, step=None, data=None, files=None):
		form = super().get_form(step, data, files)
		formset = False
		if data:
			if 'grupo' in data['grupo_wizard-current_step']:
				formset = True
		if step == "grupo":
			formset = True

		if formset:
			formset = formset_factory(wraps(MasivoForm)(partial(MasivoForm, consorcio=consorcio(self.request))), extra=1)
			form = formset(prefix='grupo', data=data)
		return form

	@transaction.atomic
	def done(self, form_list, **kwargs):
		liquidacion = self.hacer_liquidacion('grupo', receipt_type="11")
		liquidacion = liquidacion.guardar()
		messages.success(self.request, envioAFIP)
		return redirect('recursos')

@method_decorator(group_required('administrativo'), name='dispatch')
class CindividualesWizard(WizardLiquidacionManager, SessionWizardView):

	form_list = [
		('inicial', InicialForm),
		('individuales', IndividualesForm),
		('plazos', PlazoFormSet),
		('confirmacion', ConfirmacionForm)
	]

	def get_template_names(self):
		return [self.TEMPLATES[self.steps.current]]

	def get_context_data(self, form, **kwargs):
		context = super().get_context_data(form=form, **kwargs)
		tipo = "Individuales"
		peticion ="liquidacion de comprobantes RG-1415"
		if self.steps.current == 'plazos':
			data_individuales = self.get_cleaned_data_for_step('individuales')
			ingresos = set([data['ingreso'] for data in data_individuales if data])
			accesorios = self.obtener_accesorios(ingresos)

		elif self.steps.current == 'confirmacion':
			data_plazos = self.hacer_plazos()
			liquidacion = self.hacer_liquidacion('individuales', receipt_type="101")

		context.update(locals())

		return context


	def get_form_kwargs(self, step):
		kwargs = super().get_form_kwargs()
		if step in ["inicial", "individuales"]:
			kwargs.update({
					'consorcio': consorcio(self.request)
				})
		if step == "confirmacion":
			liquidacion = self.hacer_liquidacion('individuales', receipt_type="101")
			mostrar = len(liquidacion.listar_documentos()) == 1
			kwargs.update({
					'mostrar': mostrar
				})
		return kwargs

	def get_form(self, step=None, data=None, files=None):
		form = super().get_form(step, data, files)
		formset = False
		if data:
			if 'individuales' in data['cindividuales_wizard-current_step']:
				formset = True
		if step == "individuales":
			formset = True

		if formset:
			formset = formset_factory(wraps(IndividualesForm)(partial(IndividualesForm, consorcio=consorcio(self.request))), extra=1)
			form = formset(prefix='individuales', data=data)
		return form

	@transaction.atomic
	def done(self, form_list, **kwargs):
		liquidacion = self.hacer_liquidacion('individuales', receipt_type="101")
		liquidacion = liquidacion.guardar()
		contado = self.get_cleaned_data_for_step('confirmacion')['confirmacion']
		if contado:
			factura = liquidacion.factura_set.first()
			creditos = factura.incorporar_creditos()
			factura.validar_factura()

			liquidacion.confirmar()
			if liquidacion.estado == "confirmado":
				return redirect('nuevo-rcx-factura', pk=factura.pk)
			else:
				messages.error(self.request, factura.observacion)
		else:
			messages.success(self.request, envioAFIP)
		return redirect('recursos')


@method_decorator(group_required('administrativo'), name='dispatch')
class CmasivoWizard(WizardLiquidacionManager, SessionWizardView):

	form_list = [
		('inicial', InicialForm),
		('masivo', MasivoFormSet),
		('plazos', PlazoFormSet),
		('preconceptos', PreConceptoForm),
		('confirmacion', ConfirmacionForm)
	]

	def get_template_names(self):
		return [self.TEMPLATES[self.steps.current]]

	def get_context_data(self, form, **kwargs):
		context = super().get_context_data(form=form, **kwargs)
		tipo = "Masivo"
		data_masivo = self.get_cleaned_data_for_step('masivo')
		peticion = "liquidacion de comprobantes RG-1415"
		if data_masivo:
			ingresos = set([data['ingreso'] for data in data_masivo if data])
			accesorios = self.obtener_accesorios(ingresos)


		if self.steps.current == 'confirmacion':
			data_preconceptos = self.hacer_preconceptos()
			data_plazos = self.hacer_plazos()
			liquidacion = self.hacer_liquidacion('masivo', receipt_type="101")

		context.update(locals())

		return context

	def get_form_kwargs(self, step):
		kwargs = super().get_form_kwargs()
		if step in ["inicial", "preconceptos"]:
			kwargs.update({
					'consorcio': consorcio(self.request)
				})
		return kwargs

	def get_form(self, step=None, data=None, files=None):
		form = super().get_form(step, data, files)
		formset = False
		if data:
			if 'masivo' in data['cmasivo_wizard-current_step']:
				formset = True
		if step == "masivo":
			formset = True

		if formset:
			formset = formset_factory(wraps(MasivoForm)(partial(MasivoForm, consorcio=consorcio(self.request))), extra=1)
			form = formset(prefix='masivo', data=data)
		return form

	@transaction.atomic
	def done(self, form_list, **kwargs):
		liquidacion = self.hacer_liquidacion('masivo', receipt_type="101")
		liquidacion = liquidacion.guardar()
		messages.success(self.request, envioAFIP)
		return redirect('recursos')


@method_decorator(group_required('administrativo'), name='dispatch')
class CgruposWizard(WizardLiquidacionManager, SessionWizardView):

	form_list = [
		('inicial', InicialForm),
		('grupo', MasivoFormSet),
		('plazos', PlazoFormSet),
		('confirmacion', ConfirmacionForm)
	]

	def get_template_names(self):
		return [self.TEMPLATES[self.steps.current]]

	def get_context_data(self, form, **kwargs):
		context = super().get_context_data(form=form, **kwargs)
		tipo = "Por Grupos"
		peticion = "liquidacion de comprobantes RG-1415"		
		data_grupo = self.get_cleaned_data_for_step('grupo')
		if data_grupo:
			ingresos = set([data['ingreso'] for data in data_grupo if data])
			accesorios = self.obtener_accesorios(ingresos)

		if self.steps.current == 'confirmacion':
			data_plazos = self.hacer_plazos()
			liquidacion = self.hacer_liquidacion('grupo', receipt_type="101")

		context.update(locals())

		return context


	def get_form_kwargs(self, step):
		kwargs = super().get_form_kwargs()
		if step == "inicial":
			kwargs.update({
					'consorcio': consorcio(self.request),
					'ok_grupos': True,
				})
		return kwargs

	def get_form(self, step=None, data=None, files=None):
		form = super().get_form(step, data, files)
		formset = False
		if data:
			if 'grupo' in data['cgrupos_wizard-current_step']:
				formset = True
		if step == "grupo":
			formset = True

		if formset:
			formset = formset_factory(wraps(MasivoForm)(partial(MasivoForm, consorcio=consorcio(self.request))), extra=1)
			form = formset(prefix='grupo', data=data)
		return form

	@transaction.atomic
	def done(self, form_list, **kwargs):
		liquidacion = self.hacer_liquidacion('grupo', receipt_type="101")
		liquidacion = liquidacion.guardar()
		messages.success(self.request, envioAFIP)
		return redirect('recursos')


@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class RegistroLiquidaciones(OrderQS):

	""" Registro de liquidaciones """

	# model = Liquidacion
	model = Liquidacion
	template_name = "creditos/registros/liquidaciones.html"
	filterset_class = LiquidacionFilter
	paginate_by = 50


@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class RegistroCreditos(OrderQS):

	""" Registro de creditos """

	model = Credito
	filterset_class = CreditoFilter
	template_name = "creditos/registros/creditos.html"
	paginate_by = 50

	def get_queryset(self):
		return super().get_queryset(padre__isnull=True, liquidacion__estado="confirmado")


class HeaderExeptMixin:

	def dispatch(self, request, *args, **kwargs):
		try:
			objeto = self.model.objects.get(consorcio=consorcio(self.request), pk=kwargs['pk'])
		except:
			messages.error(request, 'No se pudo encontrar.')
			return redirect('recursos')

		return super().dispatch(request, *args, **kwargs)


@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class Ver(HeaderExeptMixin, generic.DetailView):

	""" Ver una liquidacion """

	model = Liquidacion
	template_name = 'creditos/ver/liquidacion.html'

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		liquidacion = self.get_object()
		creditos = liquidacion.credito_set.filter(liquidacion=liquidacion, padre__isnull=True)
		context.update(locals())
		return context

	def dispatch(self, request, *args, **kwargs):
		disp = super().dispatch(request, *args, **kwargs)
		if disp.status_code == 200 and self.get_object().estado in ["errores", "en_proceso"]:
			messages.error(request, 'No se pudo encontrar.')
			return redirect('recursos')
		return disp


@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class VerErrores(HeaderExeptMixin, generic.DeleteView):

	""" Ver una liquidacion con errores """

	model = Liquidacion
	template_name = 'creditos/ver/liquidacion-errores.html'
	success_url = '/recursos/'

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		liquidacion = self.get_object()
		facturas_invalidas = liquidacion.factura_set.filter(receipt__receipt_number__isnull=True)
		context.update(locals())
		return context

	def delete(self, request, *args, **kwargs):
		liquidacion = self.get_object()
		liquidacion.estado = "en_proceso"
		liquidacion.save()
		messages.success(self.request, envioAFIP)
		return HttpResponseRedirect(self.success_url)

	def dispatch(self, request, *args, **kwargs):
		disp = super().dispatch(request, *args, **kwargs)
		if disp.status_code == 200 and self.get_object().estado in ["confirmado", "en_proceso"]:
			messages.error(request, 'No se pudo encontrar.')
			return redirect('recursos')
		return disp


@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class PDFLiquidacion(HeaderExeptMixin, generic.DetailView):

	""" Ver PDF de una liquidacion """

	model = Liquidacion
	template_name = 'creditos/ver/liquidacion.html' # Solo para que no arroje error

	def get(self, request, *args, **kwargs):
		liquidacion = self.get_object()
		liquidacion.hacer_pdf()
		response = HttpResponse(liquidacion.pdf, content_type='application/pdf')
		nombre = "Liquidacion_%s.pdf" % (liquidacion.formatoAfip())
		content = "inline; filename=%s" % nombre
		response['Content-Disposition'] = content
		return response

	def dispatch(self, request, *args, **kwargs):
		disp = super().dispatch(request, *args, **kwargs)
		if disp.status_code == 200 and self.get_object().estado in ["errores", "en_proceso"]:
			messages.error(request, 'No se pudo encontrar.')
			return redirect('recursos')
		return disp


@method_decorator(group_required('administrativo', 'contable', 'socio'), name='dispatch')
class PDFFactura(HeaderExeptMixin, generic.DetailView):

	""" Ver PDF de una Factura """

	model = Factura
	template_name = 'creditos/ver/liquidacion.html' # Solo para que no arroje error

	def get(self, request, *args, **kwargs):
		factura = self.get_object()
		response = HttpResponse(factura.pdf, content_type='application/pdf')
		nombre = "{}_{}.pdf".format(
			factura.receipt.receipt_type.code,
			factura.formatoAfip(),
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
class IndexConceptos(generic.ListView):

	""" Index y registro de conceptos """

	model = Credito
	filterset_class = CreditoFilter
	template_name = "creditos/conceptos/index.html"

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context['conceptos'] = Credito.objects.filter(consorcio=consorcio(self.request), liquidacion__isnull=True)
		return context


@method_decorator(group_required('administrativo'), name='dispatch')
class ConceptoWizard(WizardLiquidacionManager, SessionWizardView):

	""" Nuevos conceptos """

	form_list = [
		('inicial', InicialForm),
		('conceptos', ConceptosForm),
		('plazos', PlazoFormSet)
	]

	def hacer_creditos(self):

		"""
		Crea lista de DICCIONARIOS de creditos. No lista de objetos
		Para poder utilizar mejor en manager.py
		"""

		data_inicial = self.get_cleaned_data_for_step('inicial')
		data_conceptos = self.get_cleaned_data_for_step('conceptos')
		data_plazos = self.get_cleaned_data_for_step('plazos')
		ingreso = data_inicial['ingreso']
		creditos = []

		for d in data_conceptos:
			if d:
				if d['subtotal']:
					credito = {
						'consorcio':consorcio(self.request),
						'periodo':data_inicial['fecha_operacion'],
						'ingreso':ingreso,
						'capital':d['subtotal'],
						'detalle': d['detalle']
					}
					# Establecer o cliente o dominio
					destinatario, pk = d['destinatario'].split('-')
					objeto_destinatario = eval(destinatario.capitalize()).objects.get(pk=pk)

					if destinatario == "dominio":
						credito['dominio'] = objeto_destinatario
						credito['socio'] = objeto_destinatario.socio
					elif destinatario == "socio":
						credito['socio'] = objeto_destinatario
						credito['dominio'] = None

					creditos.append(credito)
		return creditos


	def get_template_names(self):
		return [self.TEMPLATES[self.steps.current]]

	def get_context_data(self, form, **kwargs):
		context = super().get_context_data(form=form, **kwargs)
		peticion = "Carga de Conceptos previos"
		tipo = "Individuales"
		data_inicial = self.get_cleaned_data_for_step('inicial')
		if data_inicial:
			accesorios = self.obtener_accesorios([data_inicial['ingreso']])

		context.update(locals())

		return context


	def get_form_kwargs(self, step):
		kwargs = super().get_form_kwargs()
		if step in ["inicial", "conceptos"]:
			kwargs.update({
					'consorcio': consorcio(self.request),
				})
		if step == "inicial":
			kwargs.update({
				'ok_conceptos': True
			})
		return kwargs

	def get_form(self, step=None, data=None, files=None):
		form = super().get_form(step, data, files)
		formset = False
		if data:
			if 'conceptos' in data['concepto_wizard-current_step']:
				formset = True
		if step == "conceptos":
			formset = True

		if formset:
			formset = formset_factory(wraps(ConceptosForm)(partial(ConceptosForm, consorcio=consorcio(self.request))), extra=1)
			form = formset(prefix='conceptos', data=data)
		return form

	@transaction.atomic
	def done(self, form_list, **kwargs):
		data_inicial = self.get_cleaned_data_for_step('inicial')
		data_inicial['punto'] = consorcio(self.request).contribuyente.points_of_sales.first()
		data_inicial['concepto'] = ConceptType.objects.get(code="2") # "Producto", "Servicio", "Productos y servicios"
		data_inicial['fecha_factura'] = None
		data_creditos = self.hacer_creditos()
		data_plazos = self.hacer_plazos()
		conceptos = LiquidacionCreator(data_inicial=data_inicial, data_creditos=data_creditos, data_plazos=data_plazos, receipt_type=104)
		grupo_de_creditos = conceptos.reagrupar_creditos()
		creditos = []
		for grupo in grupo_de_creditos:
			for c in grupo:
				creditos.append(conceptos.hacer_credito(c))
		Credito.objects.bulk_create(creditos)
		messages.success(self.request, "Conceptos Guardados con exito")
		return redirect('conceptos')


@method_decorator(group_required('administrativo'), name='dispatch')
class ConceptoImportacionWizard(WizardLiquidacionManager, SessionWizardView):

	""" Index y registro de conceptos """

	file_storage = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, 'conceptos'))

	form_list = [
		('importacion', ImportacionForm),
		('revision', ConfirmacionForm),
		('plazos', PlazoFormSet),
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
		columnas_necesarias = ['ingreso', 'asociado', 'periodo', 'capital', 'detalle']
		columnas_archivo = datos.headers
		errores = ['Falta la columna "{}" en el archivo que deseas importar'.format(columna) for columna in columnas_necesarias if not columna in columnas_archivo]
		if errores:
			return errores


		data_ingresos = set(datos['ingreso'])
		ingresos = {}
		for i in data_ingresos:
			if not i in ingresos.keys():
				try:
					ingresos[i] = Ingreso.objects.get(consorcio=consorcio(self.request), nombre=i)
				except:
					pass

		data_asociado = set(datos['asociado'])
		asociados = {}
		for d in data_asociado:
			if not d in asociados.keys():
				try:
					asociados[d] = Socio.objects.get(consorcio=consorcio(self.request), numero_asociado=int(d))
				except:
					pass

		return {
			'ingresos': ingresos,
			'asociados': asociados,
		}

	def obtener_accesorios(self, ingresos):
		accesorios = Accesorio.objects.filter(ingreso__in=ingresos, finalizacion__isnull=True, plazo__isnull=False).distinct()
		for a in accesorios:
			a.fecha = date.today() + timedelta(days=a.plazo)
		return accesorios

	def convertirFecha(self, valor):
		inicio_excel = date(1900, 1, 1)
		diferencia = timedelta(days=int(valor)-2)
		dia = (inicio_excel + diferencia)
		return dia

	def hacer_creditos(self, datos, objetos_limpios):

		"""
			Retorna un diccionario con diccionarios, uno para ingresos y otro para dominios
			Clave: lo que coloco el usuario
			Valor: El objeto en si
		"""

		creditos = []
		errores = []

		datos = datos.dict

		fila = 2 # Fila posterior a la de los titulos de las columnas
		for d in datos:
			if d['ingreso'] and d['asociado'] and d['periodo']:
				try:
					ingreso = objetos_limpios['ingresos'][d['ingreso']]
					try:
						asociado = objetos_limpios['asociados'][d['asociado']]
						try:
							periodo = self.convertirFecha(d['periodo'])
							try:
								capital = float(d['capital'])
								creditos.append({
									'consorcio':consorcio(self.request),
									'periodo':periodo,
									'ingreso':ingreso,
									'socio':asociado,
									'capital':capital,
									'detalle':d['detalle'],
								})
							except:
								errores.append("Linea {}: Debe escribir un numero en capital".format(fila))
						except:
							errores.append("Linea {}: Debe escribir una fecha valida en periodo".format(fila))
					except:
						errores.append("Linea {}: No se reconoce el numero de asociado".format(fila))
				except:
					errores.append("Linea {}: No se reconoce el tipo de ingreso".format(fila))


			fila += 1

		return creditos, errores


	def get_template_names(self):
		return [self.TEMPLATES[self.steps.current]]

	def get_context_data(self, form, **kwargs):
		context = super().get_context_data(form=form, **kwargs)
		peticion = "Carga de Conceptos previos"
		tipo = "Importacion"
		archivo = self.get_cleaned_data_for_step('importacion')
		if archivo:
			archivo = self.get_cleaned_data_for_step('importacion')['archivo']
			datos = self.leer_datos(archivo)
			objetos_limpios = self.limpiar_datos(datos)
		if self.steps.current == 'revision':
			if type(objetos_limpios) == dict:
				creditos, errores = self.hacer_creditos(datos, objetos_limpios)
			else:
				errores = objetos_limpios

		elif self.steps.current == 'plazos':
			accesorios = self.obtener_accesorios(objetos_limpios['ingresos'].values())
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
		data_creditos, errores = self.hacer_creditos(datos, objetos_limpios)
		data_plazos = self.hacer_plazos()
		conceptos = LiquidacionCreator(data_inicial=data_inicial, data_creditos=data_creditos, data_plazos=data_plazos, receipt_type=104)
		grupo_de_creditos = conceptos.reagrupar_creditos()
		creditos = []
		for grupo in grupo_de_creditos:
			for c in grupo:
				creditos.append(conceptos.hacer_credito(c))
		Credito.objects.bulk_create(creditos)
		messages.success(self.request, "Conceptos Guardados con exito")
		return redirect('conceptos')



@method_decorator(group_required('administrativo'), name='dispatch')
class EditarConcepto(HeaderExeptMixin, generic.UpdateView):

	""" Para modificar una instancia de cualquier modelo excepto Punto """

	template_name = "creditos/conceptos/editar.html"
	model = Credito
	form_class = CreditoForm
	success_url = "/facturacion/conceptos/"

	@transaction.atomic
	def form_valid(self, form):
		retorno = super().form_valid(form)
		objeto = self.get_object()
		objeto.save()
		return retorno

	def get_form_kwargs(self):
		kwargs = super().get_form_kwargs()
		kwargs.update({
				'consorcio': consorcio(self.request),
			})
		return kwargs

	def dispatch(self, request, *args, **kwargs):
		disp = super().dispatch(request, *args, **kwargs)
		if disp.status_code == 200 and self.get_object().liquidacion:
			messages.error(request, 'No se pudo encontrar.')
			return redirect('conceptos')
		return disp


@method_decorator(group_required('administrativo'), name='dispatch')
class EliminarConcepto(generic.ListView):

	""" Para eliminar un queryset de conceptos """

	template_name = "creditos/conceptos/eliminar.html"
	model = Credito

	def get_queryset(self):
		return self.model.objects.filter(id__in=self.request.POST.getlist('conceptos[]'), consorcio=consorcio(self.request))

	def post(self, request, *args, **kwargs):
		conceptos = self.get_queryset()
		if self.request.POST.get('Save'):
			conceptos.delete()
			messages.success(self.request, "Conceptos eliminados con exito")
			return HttpResponseRedirect('/facturacion/conceptos')

		return render(request, self.template_name, locals())

@method_decorator(group_required('administrativo'), name='dispatch')
class LiquidarConcepto(generic.ListView):

	""" Para liquidar conceptos sin facturas """

	template_name = "creditos/conceptos/liquidar.html"
	model = Credito

	def get_queryset(self):
		return self.model.objects.filter(id__in=self.request.POST.getlist('conceptos[]'), consorcio=consorcio(self.request)).order_by("socio")

	def post(self, request, *args, **kwargs):
		conceptos = self.get_queryset()
		if self.request.POST.get('Save'):
			print("Hola trolo")
			return HttpResponseRedirect('/facturacion/conceptos')

		return render(request, self.template_name, locals())		