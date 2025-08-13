from django.shortcuts import render, redirect, get_object_or_404
from django.utils.decorators import method_decorator
from admincu.generic import OrderQS
from comprobantes.models import Comprobante, Cobro
from admincu.funciones import group_required, consorcio
from comprobantes.filters import ComprobanteFilter, ComprobanteFilterSocio
from expensas_pagas.models import CobroExp
from django_mercadopago.models import Preference
from django.db.models import Count
from django.views.generic import View
from .models import Solicitud, SolicitudLinea
from .forms import SolicitudForm, SolicitudLineaFormSet
from django.forms import modelformset_factory
from arquitectura.models import Establecimiento, Socio, Cotizacion, ZonasPorCultivo
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.http import JsonResponse
from django.db import transaction
from types import SimpleNamespace
from .utils_pdf import solicitud_pdf_response

class _NoFilter:
	def __init__(self, data=None, queryset=None, **kwargs):
		self.qs = queryset

@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class IndexSolicitud(OrderQS):
	""" Index de solicitudes """
	model = Solicitud
	template_name = 'index_fosea.html'
	paginate_by = 10
	# Si tenés un filterset para Solicitud, dejá esta línea.
	# Si no, podés comentarla/quitarla.
	filterset_class = _NoFilter

	def get_queryset(self, **kwargs):
		# Restringimos por consorcio como hacés en otras vistas
		qs = super().get_queryset(**kwargs)
		return qs.filter(consorcio=consorcio(self.request)).order_by('-id')

# Create your views here.
# views.py
class CrearSolicitudView(View):
	template_name = 'crear_solicitud.html'

	def get(self, request):
		form = SolicitudForm(request=request)
		tmp = Solicitud(consorcio=consorcio(request))
		formset = SolicitudLineaFormSet(instance=tmp, prefix='form')  # usa tmp con consorcio seteado
		return render(request, self.template_name, {'form': form, 'formset': formset})

	def post(self, request):
		accion = request.POST.get('accion', 'guardar')
		form = SolicitudForm(request.POST, request=request)

		if form.is_valid():
			solicitud = form.save(commit=False)
			solicitud.consorcio = consorcio(request)

			formset = SolicitudLineaFormSet(request.POST, instance=solicitud, prefix='form')
			if formset.is_valid():
				with transaction.atomic():
					solicitud.save()
					formset.save()
				solicitud.refresh_from_db()
				if accion == 'imprimir':
					# devuelve PDF en una pestaña nueva gracias a formtarget="_blank"
					return solicitud_pdf_response(solicitud, request)
				# acción por defecto: guardar y volver al índice
				return redirect('fosea')

			# form ok / formset con errores
			return render(request, self.template_name, {'form': form, 'formset': formset})

		# form inválido: rearmar formset con tmp para no perder filas
		tmp = Solicitud(consorcio=consorcio(request))
		formset = SolicitudLineaFormSet(request.POST, instance=tmp, prefix='form')
		return render(request, self.template_name, {'form': form, 'formset': formset})



def obtener_establecimientos(request):
	socio_id = request.GET.get('socio_id')
	print(f"[DEBUG] socio_id recibido: {socio_id}")
	data = []
	if socio_id:
		establecimientos = Establecimiento.objects.filter(socio__id=socio_id).distinct()
		print(f"[DEBUG] Establecimientos encontrados: {[e.nombre for e in establecimientos]}")
		data = [{'id': est.id, 'nombre': est.nombre} for est in establecimientos]
	return JsonResponse({'establecimientos': data})

def datos_establecimiento(request):
	est_id = request.GET.get('id')
	if est_id:
		try:
			est = Establecimiento.objects.select_related('zona').get(id=est_id)
			data = {
				'departamento': est.dpto,
				'gps': est.gps or '',
				'zona': est.zona.nombre if est.zona else '',
			}
			return JsonResponse(data)
		except Establecimiento.DoesNotExist:
			return JsonResponse({}, status=404)
	return JsonResponse({}, status=400)

def cotizacion_por_cultivo(request):
	cultivo_id = request.GET.get("cultivo_id")
	fecha = request.GET.get("fecha")

	if cultivo_id:
		cotizacion = (
			Cotizacion.objects
			.filter(producto_id=cultivo_id)
			.order_by("-fecha")
			.first()
		)
		if cotizacion:
			return JsonResponse({"cotizacion": float(cotizacion.cotizacion)})
	return JsonResponse({"cotizacion": None})

def aporte_por_zona_cultivo(request):
	cultivo_id = request.GET.get('cultivo_id')
	establecimiento_id = request.GET.get('establecimiento_id')

	if cultivo_id and establecimiento_id:
		try:
			est = Establecimiento.objects.select_related('zona').get(id=establecimiento_id)
			zona = est.zona
			if zona:
				zp = ZonasPorCultivo.objects.get(zona=zona, cultivo_id=cultivo_id)
				return JsonResponse({
					'aporte': float(zp.aporte_sin_siniestro),
					'franquicia': float(zp.franquicia),
				})
		except (Establecimiento.DoesNotExist, ZonasPorCultivo.DoesNotExist):
			pass
	return JsonResponse({'aporte': None, 'franquicia': None}, status=404)

def obtener_subsidio_max(request):
	establecimiento_id = request.GET.get('establecimiento_id')
	cultivo_id = request.GET.get('cultivo_id')

	try:
		establecimiento = Establecimiento.objects.get(pk=establecimiento_id)
		zona = establecimiento.zona  # asumimos que Establecimiento tiene un FK a Zona
		zpc = ZonasPorCultivo.objects.get(zona=zona, cultivo_id=cultivo_id)
		return JsonResponse({'subsidio_maximo': float(zpc.subsidio_maximo)})
	except (Establecimiento.DoesNotExist, ZonasPorCultivo.DoesNotExist):
		return JsonResponse({'error': 'No encontrado'}, status=404)


# views.py
@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class EditarSolicitudView(View):
	template_name = 'editar_solicitud.html'

	def get(self, request, pk):
		solicitud = get_object_or_404(Solicitud, pk=pk, consorcio=consorcio(request))
		form = SolicitudForm(instance=solicitud, request=request)
		formset = SolicitudLineaFormSet(instance=solicitud, prefix='form')
		return render(request, self.template_name, {'form': form, 'formset': formset, 'solicitud': solicitud})

	def post(self, request, pk):
		accion = request.POST.get('accion', 'guardar')
		solicitud = get_object_or_404(Solicitud, pk=pk, consorcio=consorcio(request))

		form = SolicitudForm(request.POST, instance=solicitud, request=request)
		formset = SolicitudLineaFormSet(request.POST, instance=solicitud, prefix='form')

		if form.is_valid() and formset.is_valid():
			with transaction.atomic():
				solicitud.save()
				formset.save()
			solicitud.refresh_from_db()
			if accion == 'imprimir':
				return solicitud_pdf_response(solicitud, request)
			return redirect('fosea')

		return render(request, self.template_name, {'form': form, 'formset': formset, 'solicitud': solicitud})
