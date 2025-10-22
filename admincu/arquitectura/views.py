from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.models import User, Group
from django_afip.models import PointOfSales
from django.db import transaction
from django.views import generic
from django.utils.decorators import method_decorator
from django.core.exceptions import ValidationError
from django.forms.utils import ErrorList
from django.urls import reverse_lazy
from tablib import Dataset
from django_afip.models import PointOfSales, DocumentType, ConceptType


# import pandas as pd

from django_afip.models import PointOfSales, DocumentType, ConceptType

from django.conf import settings

from formtools.wizard.views import SessionWizardView

from django.core.files.storage import FileSystemStorage


from admincu.funciones import *
from consorcios.models import *
from .models import *
from .forms import *
from creditos.models import Factura
from django.db.models import Q


@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class Index(generic.TemplateView):

	""" Index de parametros """

	template_name = 'arquitectura/index.html'

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		cons = consorcio(self.request)
		ingresos = Ingreso.objects.filter(
			consorcio=consorcio(self.request)).count()
		gastos = Gasto.objects.filter(
			consorcio=consorcio(self.request)).count()
		puntos = PointOfSales.objects.filter(
			owner=consorcio(self.request).contribuyente).count()
		cajas = Caja.objects.filter(consorcio=consorcio(self.request)).count()
		intereses = Accesorio.objects.filter(consorcio=consorcio(
			self.request), clase='interes', finalizacion__isnull=True).count()
		descuentos = Accesorio.objects.filter(consorcio=consorcio(
			self.request), clase='descuento', finalizacion__isnull=True).count()
		bonificaciones = Accesorio.objects.filter(consorcio=consorcio(
			self.request), clase='bonificacion', finalizacion__isnull=True).count()
		cajas = Caja.objects.filter(consorcio=consorcio(self.request)).count()
		socios = Socio.objects.filter(consorcio=consorcio(
			self.request), es_socio=True, baja__isnull=True, nombre_servicio_mutual__isnull=True).count()
		tipo_asociado = Tipo_asociado.objects.filter(
			consorcio=consorcio(self.request), baja__isnull=True).count()
		acreedores = Acreedor.objects.filter(
			consorcio=consorcio(self.request)).count()
		servicios_mutuales = Servicio_mutual.objects.filter(
			consorcio=consorcio(self.request), baja__isnull=True).count()
		convenios = Convenio.objects.filter(
			consorcio=consorcio(self.request), baja__isnull=True).count()
		clientes = Socio.objects.filter(
			consorcio=consorcio(self.request), es_socio=False, baja__isnull=True).count()
		zonas_cultivo = ZonasPorCultivo.objects.filter(
			consorcio=consorcio(self.request)).count()
		cotizaciones = Cotizacion.objects.filter(
			consorcio=consorcio(self.request)).count()
		establecimientos = Establecimiento.objects.filter(
			consorcio=consorcio(self.request)).count()
		
		
		context.update(locals())
		return context


PIVOT = {
	'Ingreso': ['Recursos', ingresoForm],
	'Gasto': ['Gastos', gastoForm],
	'Caja': ['Cajas', cajaForm],
	'Punto': ['Puntos de gestion', ],
	'Socio': ['Padron de Asociados', socioForm],
	'Tipo_asociado': ['Categorias de Asociados', grupoForm],
	'Acreedor': ['Proveedores', acreedorForm],
	'Servicio_mutual': ['Servicios Mutuales', servicioForm],
	'Convenio': ['Convenios', convenioForm],
	'Cliente':['No asociados', clienteForm],
	'ZonasPorCultivo':['Zonas por cultivo', ZonasPorCultivoForm],
	'Cotizacion':['Cotizaciones', CotizacionForm],
	'Establecimiento':['Establecimientos', EstablecimientoForm],

}


@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class Listado(generic.ListView):

	""" Lista del modelo seleccionado """

	template_name = 'arquitectura/parametro.html'

	def get_queryset(self, **kwargs):
		if self.kwargs['modelo'] == "Punto":
			objetos = PointOfSales.objects.filter(owner=consorcio(
				self.request).contribuyente).order_by('number')
		elif self.kwargs['modelo'] == "Cliente":
			objetos = Socio.objects.filter(consorcio=consorcio(self.request), es_socio=False)
		else:
			objetos = eval(self.kwargs['modelo']).objects.filter(
				consorcio=consorcio(self.request))
			if self.kwargs['modelo'] == "Socio":
				objetos = objetos.filter(Q(baja__isnull=True) | Q(
					nombre_servicio_mutual__isnull=True) | Q(es_socio=True))
		return objetos

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		cons = consorcio(self.request)
		modelo = self.kwargs['modelo']
		nombre_parametro = PIVOT[modelo][0]
		if modelo == "Convenio" and cons.convenios and cons.es_federacion:
			nombre_parametro = "Servicios AE"
		context.update({
			"parametro": modelo,
			"nombre_parametro": nombre_parametro,
			"cons": cons,
		})
		return context


@group_required('administrativo', 'contable')
def arq_puntos(request):
	if valid_demo(request.user):
		return redirect('parametro', modelo="Punto")

	try:
		puntos = consorcio(request).contribuyente.fetch_points_of_sales()
	except:
		messages.error(
			request, 'Hubo un error al consultar en la base de datos de AFIP. Intentalo nuevamente y si el error persiste comunicate con el encargado de sistemas.')

	return redirect('parametro', modelo="Punto")


@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class Crear(generic.CreateView):

	""" Para crear una nueva instancia de cualquier modelo excepto Punto """

	template_name = 'arquitectura/instancia.html'
	model = None

	def get_form_class(self):
		return PIVOT[self.kwargs['modelo']][1]

	def get_form_kwargs(self):
		kwargs = super().get_form_kwargs()
		kwargs['consorcio'] = consorcio(self.request)
		return kwargs

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		parametro = self.kwargs['modelo']
		pregunta = PIVOT[self.kwargs['modelo']][0]
		alerta = "Solo podes modificar estas opciones en un %s principal. Si necesita ayuda comuniquese con el encargado de sistema" % parametro
		context.update(locals())
		return context

	def get_success_url(self, **kwargs):
		return reverse_lazy('parametro', args=(self.kwargs['modelo'],))

	@transaction.atomic
	def form_valid(self, form):
		objeto = form.save(commit=False)
		objeto.consorcio = consorcio(self.request)
		try:
			objeto.validate_unique()
			if self.kwargs['modelo'] == "Cliente":
				objeto.es_socio = False
			if self.kwargs['modelo'] == "Socio":
				objeto.cuit = objeto.numero_documento
				if objeto.estado == 'baja':
					objeto.baja = date.today()
				if objeto.consorcio.cuit_nasociado:
					objeto.numero_asociado = objeto.cuit
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
			if kwargs['modelo'] == "Cliente":
				objeto = Socio.objects.get(consorcio=consorcio(self.request), pk=kwargs['pk'], es_socio=False)
			else:
				objeto = eval(kwargs['modelo']).objects.get(
				consorcio=consorcio(self.request), pk=kwargs['pk'])
		except:
			messages.error(request, 'No se pudo encontrar.')
			return redirect('parametros')

		return super().dispatch(request, *args, **kwargs)


@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class Instancia(HeaderExeptMixin, Crear, generic.UpdateView):

	""" Para modificar una instancia de cualquier modelo excepto Punto """

	def get_object(self, queryset=None):
		if self.kwargs['modelo'] == "Cliente":
			objeto = Socio.objects.get(pk=self.kwargs['pk'], es_socio=False)
		else:	
			objeto = eval(self.kwargs['modelo']).objects.get(pk=self.kwargs['pk'])
		return objeto

	@transaction.atomic
	def form_valid(self, form):
		retorno = super().form_valid(form)
		objeto = self.get_object()
		if self.kwargs['modelo'] in ["Cliente", "Socio"]:
			facturas = Factura.objects.filter(
				socio=objeto, receipt__receipt_number__isnull=True)
			for factura in facturas:
				factura.receipt.document_type = objeto.tipo_documento
				factura.receipt.document_number = objeto.numero_documento
				factura.receipt.save()
		return retorno


@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class ListadoAccesorio(generic.ListView):

	""" Lista de accesorios, descuento o intereses """

	template_name = 'arquitectura/parametro.html'
	model = Accesorio

	def get_queryset(self, **kwargs):
		return Accesorio.objects.filter(consorcio=consorcio(self.request), clase=self.kwargs['clase']).order_by('-id')

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["parametro"] = self.kwargs['clase']
		context["nombre_parametro"] = PIVOT[self.kwargs['clase']][0]
		return context


@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class CrearAccesorio(generic.CreateView):

	""" Crear un accesorio, descuento o interes """

	template_name = 'arquitectura/instancia.html'
	model = Accesorio

	def get_form_class(self):
		return PIVOT[self.kwargs['clase']][1]

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context['pregunta'] = PIVOT[self.kwargs['clase']][0]
		return context

	def get_form_kwargs(self):
		kwargs = super().get_form_kwargs()
		kwargs['consorcio'] = consorcio(self.request)
		return kwargs

	def get_success_url(self, **kwargs):
		return reverse_lazy('listado_accesorio', args=(self.kwargs['clase'],))

	@transaction.atomic
	def form_valid(self, form):
		objeto = form.save(commit=False)
		objeto.consorcio = consorcio(self.request)
		objeto.clase = self.kwargs['clase']
		objeto.save()
		form.save_m2m()
		anteriores = Accesorio.objects.filter(
			consorcio=objeto.consorcio,
			clase=objeto.clase,
			ingreso__in=objeto.ingreso.all(),
			finalizacion__isnull=True,
			plazo__isnull=True if not objeto.plazo else False
		)
		if anteriores:
			anteriores.update(finalizacion=date.today())
		mensaje = "{} guardado con exito".format(self.kwargs['clase'])
		messages.success(self.request, mensaje)
		return super().form_valid(form)


@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class Finalizar(HeaderExeptMixin, generic.UpdateView):

	""" Finalizar un grupo o socio """

	template_name = 'arquitectura/instancia.html'
	form_class = hiddenForm

	def get_object(self, queryset=None):
		if self.kwargs['modelo'] == "Cliente":
			objeto = Socio.objects.get(pk=self.kwargs['pk'], es_socio=False)
		else:
			objeto = eval(self.kwargs['modelo']).objects.get(pk=self.kwargs['pk'])
		return objeto

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		pregunta = self.get_object()
		respuesta = "Estas por dar de baja del sistema al {} {}. Si estas seguro de continuar presiona guardar.".format(
			self.kwargs['modelo'], pregunta)
		context.update(locals())
		return context

	def get_success_url(self, **kwargs):
		return reverse_lazy('parametros')

	@transaction.atomic
	def form_valid(self, form):
		objeto = self.get_object()
		objeto.baja = date.today()
		objeto.estado = 'baja'
		objeto.save()
		if self.kwargs['modelo'] == "Socio":
			if objeto.usuarios.all():
				for usuario in objeto.usuarios.all():
					usuario.is_active = False
					usuario.save()
		return redirect('parametro', modelo=self.kwargs['modelo'])


@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class Reactivar(HeaderExeptMixin, generic.UpdateView):

	""" Reactivar un grupo o socio """

	template_name = 'arquitectura/instancia.html'
	form_class = hiddenForm

	def get_object(self, queryset=None):
		if self.kwargs['modelo'] == "Cliente":
			objeto = Socio.objects.get(pk=self.kwargs['pk'], es_socio=False)
		else:
			objeto = eval(self.kwargs['modelo']).objects.get(pk=self.kwargs['pk'])
		return objeto

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		pregunta = self.get_object()
		respuesta = "Estas deshacer la baja del {} {}. Si estas seguro de continuar presiona guardar.".format(
			self.kwargs['modelo'], pregunta)
		context.update(locals())
		return context

	def get_success_url(self, **kwargs):
		return reverse_lazy('parametros')

	@transaction.atomic
	def form_valid(self, form):
		objeto = self.get_object()
		objeto.baja = None
		objeto.estado = 'vigente'
		objeto.save()
		if self.kwargs['modelo'] == "Socio":
			if objeto.usuarios.all():
				for usuario in objeto.usuarios.all():
					usuario.is_active = True
					usuario.save()
		return redirect('parametro', modelo=self.kwargs['modelo'])


@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class PDFCodigo(generic.DetailView):

	""" Ver PDF del codigo de socio """

	model = Socio
	# Solo para que no arroje error
	template_name = 'arquitectura/pdfs/codigo-socio.html'

	def get(self, request, *args, **kwargs):
		from django.http import HttpResponse
		socio = self.get_object()
		response = HttpResponse(
			socio.hacer_pdf(), content_type='application/pdf')
		nombre = "{}.pdf".format(socio.codigo)
		content = "inline; filename=%s" % nombre
		response['Content-Disposition'] = content
		return response

	def dispatch(self, request, *args, **kwargs):
		try:
			socio = Socio.objects.get(
				consorcio=consorcio(self.request), pk=kwargs['pk'])
		except:
			messages.error(request, 'No se pudo encontrar.')
			return redirect('parametros')

		return super().dispatch(request, *args, **kwargs)


@method_decorator(group_required('administrativo'), name='dispatch')
class SociosImportacionWizard(SessionWizardView):

	""" Index y registro de conceptos """

	file_storage = FileSystemStorage(
		location=os.path.join(settings.MEDIA_ROOT, 'socios'))

	TEMPLATES = {
		# "tipo_importacion": "arquitectura/importacion_socios/tipo_importacion.html",
		"importacion": "arquitectura/importacion_socios/importacion.html",
		"revision": "arquitectura/importacion_socios/confirmacion.html",
	}

	form_list = [
		# ('tipo_importacion', Tipo_ImportacionForm),
		('importacion', ImportacionForm),
		('revision', ConfirmacionForm),
	]

	def leer_datos(self, archivo):
		""" Retorna los datos limpios """

		datos = Dataset()
		try:
			datos.load(in_stream=archivo.read(), format='xls')
			if not datos.headers:
				raise ValueError("El archivo no contiene encabezados válidos.")
			return datos
		except Exception as e:
			print(f"Error leyendo archivo: {e}")
			raise	

	def validar_repetidos_cuit(self, datos):
		data_cuit = datos['cuit']

		seen = set()

		for c in data_cuit:
			if not c in seen:
				seen.add(c)
			else:
				print('cuit repetido en el archivo')
				return "No puede haber cuits repetidos en el archivo, el CUIT: {} esta repetido".format(c)

	def validar_repetidos_numero_asociado(self, datos):
		try:
			data_numeroasoc = datos['numero_asociado']

			seen = set()

			for c in data_numeroasoc:
				if not c in seen:
					seen.add(c)
				else:
					print('numero de asociado repetido en el archivo')
					return "No puede haber numeros de asociado repetidos en el archivo, el Numero de asociado: {} esta repetido".format(c)
		except:
			pass					

	def limpiar_datos(self, datos):
		"""
				Retorna un diccionario con diccionarios, uno para ingresos y otro para dominios
				Clave: lo que coloco el usuario
				Valor: El objeto en si
		"""

		# Validacion de columnas
		if consorcio(self.request).cuit_nasociado:
			columnas_necesarias = ['cuit', 'apellido', 'nombre', 'fecha_alta', 'tipo_persona', 'tipo_asociado','genero', 'provincia', 'localidad', 'calle', 'fecha_nacimiento',
								'es_extranjero', 'numero_calle', 'piso', 'departamento', 'codigo_postal', 'telefono', 'profesion', 'mail', 'notificaciones']
		else:
			columnas_necesarias = ['cuit', 'apellido', 'nombre', 'fecha_alta', 'tipo_persona', 'tipo_asociado','genero', 'numero_asociado','provincia', 'localidad', 'calle', 'fecha_nacimiento',
								'es_extranjero', 'numero_calle', 'piso', 'departamento', 'codigo_postal', 'telefono', 'profesion', 'mail', 'notificaciones']
		if consorcio(self.request).convenios:
			columnas_necesarias.append('convenio')
		columnas_archivo = datos.headers
		errores = ['Falta la columna "{}" en el archivo que deseas importar'.format(
			columna) for columna in columnas_necesarias if not columna in columnas_archivo]
		if errores:
			return errores

		# data_cuit = datos['cuit']
		# cuits_existentes = Socio.objects.filter(consorcio=consorcio(self.request)).values_list('cuit', flat=True)

		# for c in data_cuit:
		# 	c = str(int(c))
		# 	if c in cuits_existentes:
		# 		print('el cuit ya existe')
		# 	else:
		# 		pass

		data_cuit = datos['cuit']
		cuits = {}

		for c in data_cuit:
			try:
				cn = int(c)
				if len(str(cn)) == 11:
					cuits[c] = cn
			except:
				pass

		cuitos = {}

		cuits_existentes = Socio.objects.filter(
			consorcio=consorcio(self.request)).values_list('cuit', flat=True)

		for c in data_cuit:
			try:
				cn = str(int(c))
				if not cn in cuits_existentes:
					cuitos[c] = int(c)
			except:
				pass

		data_cp = datos['codigo_postal']
		cps = {}
		for c in data_cp:
			if not c in cps.keys():
				try:
					cps[c] = int(c)
				except:
					pass

		data_piso = datos['piso']
		pisos = {}
		for p in data_piso:
			if not p in pisos.keys():
				try:
					if p:
						pisos[p] = int(p)
					else:
						pisos[p] = None
				except:
					pass
		data_num_calle = datos['numero_calle']
		numeros_calle = {}
		for n in data_num_calle:
			if not n in numeros_calle.keys():
				try:
					if n:
						numeros_calle[n] = int(n)
					else:
						numeros_calle[n] = None
				except:
					pass

		try:
			data_numeroasoc = datos['numero_asociado']
			numero_asociados = {}
			for c in data_numeroasoc:
				if not c in numero_asociados.keys():
					try:
						numero_asociados[c] = int(c)
					except:
						pass


			numero_asociados_existentes = Socio.objects.filter(
				consorcio=consorcio(self.request)).values_list('numero_asociado', flat=True)

			numeros_asociadoss = {}

			for c in data_numeroasoc:
				try:
					cn = str(int(c))
					if not cn in numero_asociados_existentes:
						numeros_asociadoss[c] = int(c)
				except:
					pass
		except:
			pass


# ta=tipo de asociado, tas=plural
		data_ta = datos['tipo_asociado']
		ta = {}
		for t in data_ta:
			if not t in ta.keys():
				try:
					ta[t] = Tipo_asociado.objects.get(
						consorcio=consorcio(self.request), nombre=t)
				except:
					pass
		try:
			data_convenios = datos['convenio']
			convenios = {}
			for c in data_convenios:
				if not c in convenios.keys():
					try:
						convenios[c] = Convenio.objects.get(
							consorcio=consorcio(self.request), nombre=c
						)
					except:
						pass
		except:
			pass

		data_provincias = datos['provincia']
		provincias = {}
		for p in data_provincias:
			if not p in provincias.keys():
				try:
					provincias[p] = Codigo_Provincia.objects.get(nombre=p)
				except:
					pass
		
		data_esextranjero = datos['es_extranjero']
		es_extranjeros = {}
		for e in data_esextranjero:
			if not e in es_extranjeros.keys():
				try:
					if e == 'si':
						es_extranjeros[e] = True
					if e == 'no':
						es_extranjeros[e] = False
				except:
					pass

		data_tipo_persona = datos['tipo_persona']
		tipo_personas = {}
		for t in data_tipo_persona:
			if not t in tipo_personas.keys():
				try:
					if t == 'fisica':
						tipo_personas[t] = 'fisica'
					if t == 'juridica':
						tipo_personas[t] = 'juridica'
				except:
					pass

		data_notificaciones = datos['notificaciones']
		notificacioness = {}
		for n in data_notificaciones:
			if not n in notificacioness.keys():
				try:
					if n == 'si':
						notificacioness[n] = True
					if n == 'no':
						notificacioness[n] = False
				except:
					pass

		data_genero = datos['genero']
		generos = {}
		for g in data_genero:
			if not g in generos.keys():
				try:
					if g == 'masculino':
						generos[g] = 'masculino'
					if g == 'femenino':
						generos[g] = 'femenino'
					if g == 'no binario':
						generos[g]= 'no_binario'
					if g == 'otro':
						generos[g] = 'otro' 
				except:
					pass





		return {
			'tipo_personas': tipo_personas,
			'notificacioness': notificacioness,
			'es_extranjeros': es_extranjeros,
			'provincias': provincias,
			'tas': ta,
			'convenios':convenios if consorcio(self.request).convenios else None,
			'cuits': cuits,
			'numero_asociados': numero_asociados if not consorcio(self.request).cuit_nasociado else cuits,
			'numeros_calle':numeros_calle,
			'pisos': pisos,
			'cps': cps,
			'cuitos': cuitos,
			'numeros_asociadoss':numeros_asociadoss if not consorcio(self.request).cuit_nasociado else cuitos,
			'generos':generos

		}

	def convertirFecha(self, valor):
		inicio_excel = date(1900, 1, 1)
		diferencia = timedelta(days=int(valor)-2)
		dia = (inicio_excel + diferencia)
		return dia

	def hacer_socios(self, datos, objetos_limpios):
		socios = []
		errores = []
		datos = datos.dict
		fila = 2

		for d in datos:
			error = self.validar_datos(d, objetos_limpios)
			if error:
				errores.append("Linea {}: {}".format(fila, error))
				print(error)
			else:
				cuit = objetos_limpios['cuits'][d['cuit']]
				apellido = d['apellido']
				nombre = d['nombre']
				fecha_alta = self.convertirFecha(d['fecha_alta'])
				tipo_persona = d['tipo_persona']
				tipo_asociado = objetos_limpios['tas'][d['tipo_asociado']]
				genero = d['genero']
				provincia = objetos_limpios['provincias'][d['provincia']]
				localidad = d['localidad']
				calle = d['calle']
				mail = d['mail']
				profesion = d['profesion']
				telefono = d['telefono']
				codigo_postal = objetos_limpios['cps'][d['codigo_postal']]
				departamento = d['departamento']
				piso = objetos_limpios['pisos'][d['piso']]
				numero_calle = objetos_limpios['numeros_calle'][d['numero_calle']]
				es_extranjero = objetos_limpios['es_extranjeros'][d['es_extranjero']]
				try:
					fecha_nacimiento = self.convertirFecha(
					d['fecha_nacimiento'])
				except:
					fecha_nacimiento = None


				if  consorcio(self.request).cuit_nasociado:
					numero_asociado = objetos_limpios['cuits'][d['cuit']]
				else:				
					numero_asociado = objetos_limpios['numero_asociados'][d['numero_asociado']]
				convenio = None
				if  consorcio(self.request).convenios:
					convenio = objetos_limpios['convenios'][d['convenio']]
				else:
					pass

				notificaciones = objetos_limpios['notificacioness'][d['notificaciones']]

				socio = {
					'codigo_consorcio': consorcio(self.request).id,
					'fecha_alta': fecha_alta,
					'nombre': nombre,
					'cuit': cuit,
					'apellido': apellido,
					'tipo_persona': tipo_persona,
					'tipo_asociado': tipo_asociado,
					'genero': genero,
					'provincia': provincia,
					'localidad': localidad,
					'calle': calle,
					'mail': mail,
					'profesion': profesion,
					'telefono': telefono,
					'codigo_postal': codigo_postal,
					'departamento': departamento,
					'piso': piso,
					'numero_calle': numero_calle,
					'es_extranjero': es_extranjero,
					'fecha_nacimiento': fecha_nacimiento,
					'numero_asociado': numero_asociado,
					'notificaciones': notificaciones
				}
				if  convenio:
					socio['convenio'] = convenio
				socios.append(socio) 
			fila += 1

		return socios, errores

	def validar_datos(self, datos, objetos_limpios):
		if not all([datos['cuit'], datos['nombre'], datos['fecha_alta'], datos['apellido']]):
			return "Todos los campos deben estar llenos"

		try:
			objetos_limpios['tas'][datos['tipo_asociado']]
		except:
			return "Debe escribir un tipo de asociado valido"
		if consorcio(self.request).convenios:
			try:
				objetos_limpios['convenios'][datos['convenio']]
			except:
				return "Debe escribir un nombre de convenio valido"
		else:
			pass		
		try:
			objetos_limpios['tipo_personas'][datos['tipo_persona']]
		except:
			return "Debe escribir un tipo de persona valido"

		try:
			objetos_limpios['es_extranjeros'][datos['es_extranjero']]
		except:
			return "Debe escribir si o no en la columna es_extranjeros"

		try:
			objetos_limpios['notificacioness'][datos['notificaciones']]
		except:
			return "Debe escribir si o no en la columna notificaciones"
		try:
			objetos_limpios['provincias'][datos['provincia']]
		except:
			return "Debe escribir una provincia valida"

		try:
			objetos_limpios['cuits'][datos['cuit']]
		except:
			return "Debe escribir un CUIT válido, debe ser un número de 11 dígitos"

		# try:
		# 	objetos_limpios['cuites'][datos['cuit']]
		# except:
		# 	return "CUIT repetido dentro del archivo"

		try:
			objetos_limpios['cuitos'][datos['cuit']]
		except:
			return "Este CUIT ya existe"

		# cuits_existentes = Socio.objects.filter(consorcio=consorcio(self.request)).values_list('cuit', flat=True)

		# for c in data_cuit:
		# 	c = str(int(c))
		# 	if c in cuits_existentes:
		# 		return 'el cuit ya existe'
		# 	else:
		# 		pass

		if not consorcio(self.request).cuit_nasociado:
			try:
				objetos_limpios['numero_asociados'][datos['numero_asociado']]

			except:
				return "Debe escribir un numero en la columna numero de asociado"

			try:
				objetos_limpios['numeros_asociadoss'][datos['numero_asociado']]
			except:
				return "Este numero de asociado ya existe"
		else:
			pass

		try:
			objetos_limpios['numeros_calle'][datos['numero_calle']]

		except:
			return "Debe escribir un numero en la columna numero_calle"

		try:
			objetos_limpios['pisos'][datos['piso']]

		except:
			return "Debe escribir un numero en la columna piso"

		try:
			objetos_limpios['cps'][datos['codigo_postal']]

		except:
			return "Debe escribir un numero en la columna codigo postal"

		try:
			self.convertirFecha(datos['fecha_alta'])
		except:
			return "Debe escribir una fecha válida en fecha alta"

		if datos['fecha_nacimiento']:
			try:
				self.convertirFecha(datos['fecha_nacimiento'])
			except:
				return "Debe escribir una fecha válida en fecha nacimiento"
		else:
			None
		try:
			objetos_limpios['generos'][datos['genero']]
		except:
			return "Debe escribir masculino, femenino, no binario o otro en la columna genero"





		return None

	def get_template_names(self):
		return [self.TEMPLATES[self.steps.current]]

	def get_context_data(self, form, **kwargs):
		context = super().get_context_data(form=form, **kwargs)	
		extension = 'comprobantes/nuevo/Recibo.html'
		es_importacion_de_socios = 'importacion'
		peticion = "Carga de Cobros"
		tipo = "Importacion"
		archivo = self.get_cleaned_data_for_step('importacion')
		if archivo:
			archivo = self.get_cleaned_data_for_step('importacion')['archivo']
			datos = self.leer_datos(archivo)
			repetidos_cuit = self.validar_repetidos_cuit(datos)
			repetidos_numeros_asociados = self.validar_repetidos_numero_asociado(datos)
			if consorcio(self.request).cuit_nasociado:
				repetidos_numeros_asociados = None
				pass
			objetos_limpios = self.limpiar_datos(datos)
		if self.steps.current == 'revision':
			if not repetidos_cuit and not repetidos_numeros_asociados:
				if type(objetos_limpios) == dict:
					socios, errores = self.hacer_socios(datos, objetos_limpios)
				else:
					errores = objetos_limpios
			else:
				if repetidos_cuit:
					errores = [repetidos_cuit]
				elif repetidos_numeros_asociados:
					errores = [repetidos_numeros_asociados]	

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
		socios, errores = self.hacer_socios(datos, objetos_limpios)
		socioss = []
		for socio in socios:
			socio_data = {
				'consorcio': consorcio(self.request),
				'mail': socio['mail'],
				'profesion': socio['profesion'],
				'telefono': socio['telefono'],
				'codigo_postal': socio['codigo_postal'],
				'departamento': socio['departamento'],
				'piso': socio['piso'],
				'numero_calle': socio['numero_calle'],
				'es_extranjero': socio['es_extranjero'],
				'fecha_nacimiento': socio['fecha_nacimiento'],
				'numero_asociado': str(socio['numero_asociado']),
				'nombre': socio['nombre'],
				'provincia': socio['provincia'],
				'localidad': socio['localidad'],
				'domicilio': socio['calle'],
				'tipo_asociado': socio['tipo_asociado'],
				'fecha_alta': socio['fecha_alta'],
				'apellido': socio['apellido'],
				'tipo_persona': socio['tipo_persona'],
				'genero': socio['genero'],
				'cuit': socio['cuit'],
				'numero_documento': socio['cuit'],
				'tipo_documento': DocumentType.objects.get(id=1),
				'notificaciones': socio['notificaciones']
			}
			if 'convenio' in socio:
				socio_data['convenio'] = socio['convenio']
			socioss.append(Socio(**socio_data))	
		Socio.objects.bulk_create(socioss)
		messages.success(self.request, "Socios guardados con exito")
		return redirect('parametro', modelo=self.kwargs['modelo'])

@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class ExportacionInaes(generic.ListView):

	""" Index de transferencias """
	template_name = 'arquitectura/exportacion_inaes/exportacion.html'
	paginate_by = 10

	def get_queryset(self, **kwargs):

		socios = Socio.objects.filter(consorcio=consorcio(
			self.request),baja__isnull=True)
		return socios

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context['socios'] = self.get_queryset()
		return context

