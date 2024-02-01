from django.shortcuts import render, redirect
from django.views import generic
from django.urls import reverse_lazy
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.forms.utils import ErrorList


from .models import *
from consorcios.models import *
from admincu.funciones import *
from .forms import *



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
		transporte = Transporte.objects.filter(consorcio=consorcio(self.request)).count()
		notas_pedido = Notas_Pedido.objects.filter(consorcio=consorcio(self.request)).count()
		comp_venta = Comp_Venta.objects.filter(consorcio=consorcio(self.request)).count()
		consol_carga = Consol_Carga.objects.filter(consorcio=consorcio(self.request)).count()
		guia_distri = Guia_Distri.objects.filter(consorcio=consorcio(self.request)).count()
		informe = Informe.objects.filter(consorcio=consorcio(self.request)).count()
		recibo_provee = Recibo_Provee.objects.filter(consorcio=consorcio(self.request)).count()
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


}



class Listado(generic.ListView):

	""" Lista del modelo seleccionado """

	template_name = 'elemento.html'

	def get_queryset(self, **kwargs):
		objetos = eval(self.kwargs['modelo']).objects.filter(
			consorcio=consorcio(self.request), nombre__isnull=False)
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
