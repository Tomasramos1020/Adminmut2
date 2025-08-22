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
from .forms import *
from django.forms import modelformset_factory
from arquitectura.models import Establecimiento, Socio, Cotizacion, ZonasPorCultivo, Cultivo, Zona
from django.template.loader import render_to_string
from django.http import HttpResponse, JsonResponse
from django.db import transaction
from types import SimpleNamespace
from .utils_pdf import solicitud_pdf_response
from decimal import Decimal, ROUND_HALF_UP
from weasyprint import HTML
from .utils_pdf import calcular_total_garantia
from django.contrib.auth.decorators import login_required
from .forms import CotizacionForm, CotizacionLineaForm, CotizacionLineaFormSet
from django.utils.timezone import now
from django.urls import reverse
from django.core.exceptions import ObjectDoesNotExist
from django.views.decorators.http import require_http_methods
from django.middleware.csrf import get_token
from arquitectura.forms import EstablecimientoForm
from .filters import *



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


def get_soja_id_por_consorcio(cons):
	return (Cultivo.objects
			.filter(consorcio=cons, nombre__iexact="Soja")
			.values_list("id", flat=True)
			.first())

# Create your views here.
# views.py
class CrearSolicitudView(View):
	template_name = 'crear_solicitud.html'

	def get(self, request):
		cons = consorcio(request)
		form = SolicitudForm(request=request)
		tmp = Solicitud(consorcio=cons)
		formset = SolicitudLineaFormSet(instance=tmp, prefix='form') # usa tmp con consorcio seteado
		ctx = {'form': form, 'formset': formset, 'soja_id': get_soja_id_por_consorcio(cons)}
		return render(request, self.template_name, ctx)

	def post(self, request):
		cons = consorcio(request)
		accion = request.POST.get('accion', 'guardar')
		form = SolicitudForm(request.POST, request=request)

		if form.is_valid():
			solicitud = form.save(commit=False)
			solicitud.consorcio = cons

			formset = SolicitudLineaFormSet(request.POST, instance=solicitud, prefix='form')
			if formset.is_valid():
				with transaction.atomic():
					solicitud.save()
					formset.save()
				solicitud.refresh_from_db()
				if accion == 'imprimir':
					# devuelve PDF en una pestaña nueva gracias a formtarget="_blank"
					return solicitud_pdf_response(solicitud, request)
				if accion == 'pagare':
					# Pestaña nueva gracias a formtarget="_blank"
					return redirect('pagare_solicitud', pk=solicitud.pk)
				# acción por defecto: guardar y volver al índice
				return redirect('fosea')

			# form ok / formset con errores
			ctx = {'form': form, 'formset': formset, 'soja_id': get_soja_id_por_consorcio(cons)}
			return render(request, self.template_name, ctx)

		# form inválido: rearmar formset con tmp para no perder filas
		tmp = Solicitud(consorcio=cons)
		formset = SolicitudLineaFormSet(request.POST, instance=tmp, prefix='form')
		ctx = {'form': form, 'formset': formset, 'soja_id': get_soja_id_por_consorcio(cons)}
		return render(request, self.template_name, ctx)

@login_required
@require_http_methods(["GET", "POST"])
def establecimiento_modal(request):
	cons = consorcio(request)
	socio_id = request.GET.get('socio_id') or request.POST.get('socio_id')

	if request.method == "GET":
		if not socio_id:
			return HttpResponse(
				"<div style='padding:16px;'>Primero seleccioná un socio para poder crear o elegir el establecimiento.</div>",
				status=422
			)
		# existentes del socio
		existentes = (
			Establecimiento.objects
			.filter(consorcio=cons, socio__id=socio_id)
			.order_by('nombre')
			.distinct()
			.only('id', 'nombre', 'dpto', 'gps', 'zona')
			.select_related('zona')
		)
		form = EstablecimientoModalForm(consorcio=cons)
		html = render_to_string(
			"establecimientos/_modal_form.html",
			{
				"form": form,
				"existentes": existentes,
				"csrf_token": get_token(request),
			},
			request=request
		)
		return HttpResponse(html)

	# POST = crear nuevo
	form = EstablecimientoModalForm(consorcio=cons, data=request.POST)
	if form.is_valid():
		est = form.save(commit=False)
		est.consorcio = cons
		est = form.save()
		form.save_m2m()
		
		if socio_id:
			try:
				s = Socio.objects.get(pk=socio_id, consorcio=cons)
				est.socio.add(s)  # lo seteamos como dueño/relación
			except Socio.DoesNotExist:
				pass

		return JsonResponse({
			"ok": True,
			"id": est.pk,
			"nombre": est.nombre,
			"departamento": est.dpto or "",
			"gps": est.gps or "",
			"zona": est.zona.nombre if getattr(est, "zona", None) else ""
		})

	html = render_to_string(
		"establecimientos/_modal_form.html",
		{
			"form": form,
			"existentes": Establecimiento.objects.none(),  # evita re-consulta si hubo error
			"csrf_token": get_token(request),
		},
		request=request
	)
	return HttpResponse(html, status=422)





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

	if not cultivo_id:
		return JsonResponse({"cotizacion": None})

	cons = consorcio(request)
	qs = Cotizacion.objects.filter(consorcio=cons, producto_id=cultivo_id)
	cot = qs.order_by("-fecha").first()
	return JsonResponse({"cotizacion": float(cot.cotizacion) if cot else None})

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
# views.py
@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class EditarSolicitudView(View):
	template_name = 'editar_solicitud.html'

	def get(self, request, pk):
		cons = consorcio(request)
		solicitud = get_object_or_404(Solicitud, pk=pk, consorcio=cons)
		form = SolicitudForm(instance=solicitud, request=request)
		formset = SolicitudLineaFormSet(instance=solicitud, prefix='form')
		ctx = {'form': form, 'formset': formset, 'solicitud': solicitud,
               'soja_id': get_soja_id_por_consorcio(cons)}
		return render(request, self.template_name, ctx)

	def post(self, request, pk):
		cons = consorcio(request)
		accion = request.POST.get('accion', 'guardar')
		solicitud = get_object_or_404(Solicitud, pk=pk, consorcio=cons)

		form = SolicitudForm(request.POST, instance=solicitud, request=request)
		formset = SolicitudLineaFormSet(request.POST, instance=solicitud, prefix='form')

		if form.is_valid() and formset.is_valid():
			with transaction.atomic():
				# Guardar cambios del form principal
				solicitud = form.save()   # <- IMPORTANTE
				# Guardar líneas
				formset.save()
			solicitud.refresh_from_db()

			if accion == 'imprimir':
				return solicitud_pdf_response(solicitud, request)

			if accion == 'pagare':
				# Si tenés una función que devuelve el PDF del pagaré:
				url = reverse('pagare_solicitud', args=[solicitud.pk])
				return redirect(url)
				# Alternativa si el pagaré es una vista por URL:
				# from django.urls import reverse
				# return redirect(reverse('pagare_solicitud', args=[solicitud.id]))

			return redirect('fosea')
		ctx = {'form': form, 'formset': formset, 'solicitud': solicitud,
               'soja_id': get_soja_id_por_consorcio(cons)}
		return render(request, self.template_name, ctx)

# views.py
 # ajustá el import

class PagareSolicitudPDFView(View):
	def get(self, request, pk):
		solicitud = get_object_or_404(Solicitud, pk=pk, consorcio=consorcio(request))

		# 1) Definí el monto del pagaré:
		#    - si te pasan ?monto= por querystring, lo usa
		#    - si no, ajustá esta parte a tu cálculo "garantía total" o similar
		monto = calcular_total_garantia(solicitud)

		context = {
			"solicitud": solicitud,
			"monto": monto,  # número
			# Datos de texto útiles para el pagaré:
			"acreedor_nombre": solicitud.consorcio.nombre_completo,
			"acreedor_cuit": getattr(solicitud.consorcio, "cuit", ""),
			"deudor_nombre": str(solicitud.socio),
			"deudor_doc": f"{solicitud.socio.tipo_documento} {solicitud.socio.numero_documento}",
			"deudor_cuit": getattr(solicitud.socio, "cuit", ""),
			"deudor_domicilio": solicitud.socio.domicilio,
			"lugar_emision": "Río Cuarto",  # si tenés ciudad en DB, usala
			"fecha_emision": solicitud.fecha,  # date
		}

		html = render_to_string("pdfs/pagare_solicitud.html", context)
		pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()

		resp = HttpResponse(pdf, content_type="application/pdf")
		resp["Content-Disposition"] = f'inline; filename="pagare_solicitud_{solicitud.pk}.pdf"'
		return resp

# ---------- AJAX: parámetros por zona+cultivo ----------
@login_required
def parametros_zona_cultivo(request):
	"""Devuelve subsidio_max, aporte_max (sin siniestro) y franquicia para la zona/cultivo del consorcio."""
	z_id = request.GET.get('zona_id')
	c_id = request.GET.get('cultivo_id')
	data = {'subsidio_max': None, 'aporte_max': None, 'franquicia': None}

	if not (z_id and c_id):
		return JsonResponse(data)

	try:
		zpc = ZonasPorCultivo.objects.get(
			consorcio=consorcio(request),
			zona_id=z_id,
			cultivo_id=c_id
		)
		data = {
			'subsidio_max': str(zpc.subsidio_maximo),         # número plano
			'aporte_max': str(zpc.aporte_sin_siniestro),      # usamos SIN siniestro
			'franquicia': str(zpc.franquicia),
		}
	except ZonasPorCultivo.DoesNotExist:
		pass

	return JsonResponse(data)


# ---------- PDF (WeasyPrint) ----------
def cotizacion_pdf_response(ctx, request):
	"""Genera PDF de la cotización sin guardar nada en la BD."""
	html = render_to_string('pdfs/cotizacion_pdf.html', ctx)
	try:
		from weasyprint import HTML
	except Exception:
		# fallback: devolvemos HTML si no tenés WeasyPrint en local
		return HttpResponse(html)

	pdf = HTML(string=html, base_url=request.build_absolute_uri()).write_pdf()
	resp = HttpResponse(pdf, content_type='application/pdf')
	resp['Content-Disposition'] = 'inline; filename="cotizacion.pdf"'
	return resp

def _d(val):
	# helper para Decimal seguro
	if val is None or val == '':
		return Decimal('0')
	return Decimal(str(val))

def _get_max_subsidio(zona, cultivo):
	"""
	Devuelve el máximo de subsidio (Decimal) para esa zona/cultivo.
	Si no existe registro, devuelve None (sin tope).
	"""
	try:
		param = ZonasPorCultivo.objects.get(zona=zona, cultivo=cultivo)
		# Ajustá el nombre del campo según tu modelo (ej: param.subsidio_max_qq)
		return Decimal(param.subsidio_max).quantize(Decimal('0.01'))
	except (ObjectDoesNotExist, AttributeError, TypeError, ValueError):
		return None

# ---------- VIEW principal ----------
@method_decorator(login_required, name='dispatch')
class CrearCotizacionView(View):
	template_name = 'crear_cotizacion.html'

	# bind = True sólo en POST
	def _build_formset(self, *, bind: bool, request=None, post_data=None):
		kwargs = {
			'form_kwargs': {'request': request},
			'prefix': 'form',
		}
		if bind:
			kwargs['data'] = post_data
		# ⚠️ No pongas kwargs['initial'] = [{}]
		return CotizacionLineaFormSet(**kwargs)


	def get(self, request):
		cons = consorcio(request)
		form = CotizacionForm(request=request)
		formset = self._build_formset(bind=False, request=request)
		ctx = {'form': form, 'formset': formset, 'soja_id': get_soja_id_por_consorcio(cons)}
		return render(request, self.template_name, ctx)

	def post(self, request):
		cons = consorcio(request)
		accion = request.POST.get('accion', 'imprimir')
		form = CotizacionForm(request.POST, request=request)
		formset = self._build_formset(bind=True, request=request, post_data=request.POST)

		if form.is_valid() and formset.is_valid():
			cd = form.cleaned_data

			# ✅ Validación de subsidio_max contra el tope antes de preparar el ctx
			hubo_error_tope = False
			for i, f in enumerate(formset.forms):
				if getattr(f, 'cleaned_data', None) is None:
					continue
				if formset.can_delete and f.cleaned_data.get('DELETE'):
					continue

				zona = f.cleaned_data.get('zona')
				cultivo = f.cleaned_data.get('cultivo')
				subsidio_ingresado = _d(f.cleaned_data.get('subsidio_max') or 0)

				# línea vacía: saltar
				hay_algo = any(
					v not in (None, '', 0, Decimal('0'))
					for k, v in f.cleaned_data.items()
					if k not in ('DELETE',)
				)
				if not hay_algo:
					continue

				# si faltan zona/cultivo, ya lo maneja el form; seguimos
				if zona and cultivo:
					tope = _get_max_subsidio(zona, cultivo)
					if tope is not None and subsidio_ingresado > tope:
						f.add_error(
							'subsidio_max',
							f'El valor ingresado ({subsidio_ingresado}) supera el máximo '
							f'permitido para {zona} / {cultivo}: {tope}.'
						)
						hubo_error_tope = True

			if hubo_error_tope:
				# devolvemos la pantalla con errores; NO imprimimos
				return render(request, self.template_name, {'form': form, 'formset': formset})
			lineas = []
			for f in formset.forms:
				if getattr(f, 'cleaned_data', None) is None:
					continue
				if formset.can_delete and f.cleaned_data.get('DELETE'):
					continue

				l = f.cleaned_data.copy()

				# Recomputo seguro
				hect = _d(l.get('hectarea'))
				subsidio = _d(l.get('subsidio_max'))
				aporte_max = _d(l.get('aporte_max'))
				franquicia = _d(l.get('franquicia'))
				aporte_total = hect * subsidio * (aporte_max / Decimal('100'))
				l['aporte_total_qq'] = aporte_total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

				# Campos “solo PDF” (strings seguros)
				l['gps'] = l.get('gps') or ''
				l['departamento'] = l.get('departamento') or ''
				l['establecimiento'] = l.get('establecimiento') or ''

				lineas.append(l)

			# Resumen por cultivo simple (para tabla de "RESUMEN")
			resumen_cultivo = {}
			for l in lineas:
				cultivo = l['cultivo']   # es instancia; en template se muestra por __str__
				clave = getattr(cultivo, 'nombre', str(cultivo))
				if clave not in resumen_cultivo:
					resumen_cultivo[clave] = {
						'cultivo': cultivo,
						'hectareas': Decimal('0.00'),
						'aporte': Decimal('0.00'),
					}
				resumen_cultivo[clave]['hectareas'] += _d(l.get('hectarea'))
				resumen_cultivo[clave]['aporte'] += _d(l.get('aporte_total_qq'))

			# Valor soja (igual esquema que en Solicitud; usalo también como valor cereal de referencia)
			valor_soja = None
			try:
				soja = Cultivo.objects.filter(consorcio=consorcio(request), nombre__iexact='soja').first()
				if soja:
					coti = Cotizacion.objects.filter(consorcio=consorcio(request), producto=soja).order_by('-fecha').first()
					if coti:
						valor_soja = _d(coti.cotizacion)
			except Exception:
				pass
			# --- Obtener valor de cotización por cultivo (última cotización por producto) ---
			valor_por_cultivo = {}  # dict: cultivo_id -> Decimal o None
			try:
				# IDs de cultivos presentes en las líneas
				cultivo_ids = []
				for v in resumen_cultivo.values():
					c = v['cultivo']
					if getattr(c, 'id', None):
						cultivo_ids.append(c.id)
				cultivo_ids = list(set(cultivo_ids))

				if cultivo_ids:
					# Opción simple (pocas consultas, cantidad de cultivos suele ser baja):
					for cid in cultivo_ids:
						ult = (Cotizacion.objects
							.filter(consorcio=consorcio(request), producto_id=cid)
							.order_by('-fecha')
							.first())
						valor_por_cultivo[cid] = _d(ult.cotizacion) if ult else None
			except Exception:
				pass

			# Hectáreas reales = suma de hectáreas cargadas
			# Hectáreas reales = suma de hectáreas * participación / 100
			total_hectareas_brutas = sum(_d(l.get('hectarea')) for l in lineas)
			hectareas_reales = sum(
				(_d(l.get('hectarea')) * _d(l.get('participacion')) / Decimal('100'))
				for l in lineas
			)


			# Factor y cálculo de suscripción (como tu plantilla de Solicitud)
			# factor = valor_soja / 100 si hay soja, sino 1
			factor = (valor_soja / Decimal('100')) if valor_soja not in (None, Decimal('0')) else Decimal('1')
			suscripcion = _d(cd['suscripcion'])
			valor_hec_real = (factor * suscripcion).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
			total_suscripcion = (valor_hec_real * hectareas_reales).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

			# Suma de aportes en QQ
			suma_aporte_total_qq = sum((v['aporte'] for v in resumen_cultivo.values()), Decimal('0'))

			# Armar "resumen" extendido (por cultivo) con valor cereal y garantía por cultivo
			# Usamos valor_soja como valor_cereal de referencia para todos los cultivos (ajustable si luego querés otro mapping).
			# Armar "resumen" con valor_cereal por cultivo y garantía por cultivo
			resumen = []
			total_hectareas_resumen = Decimal('0')
			total_garantia = Decimal('0')
			tiene_alguna_garantia = False  # para saber si mostrar o no

			for k, v in resumen_cultivo.items():
				cultivo_obj = v['cultivo']
				cid = getattr(cultivo_obj, 'id', None)
				valor_cereal = valor_por_cultivo.get(cid) if cid is not None else None

				# garantía = aporte_qq * valor_cereal (si hay valor)
				garantia = None
				if valor_cereal not in (None, Decimal('0')):
					garantia = (v['aporte'] * valor_cereal).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
					total_garantia += garantia
					tiene_alguna_garantia = True

				resumen.append({
					'cultivo': k,                         # nombre del cultivo
					'hectareas': v['hectareas'],
					'aporte_qq': v['aporte'],
					'valor_cereal': valor_cereal,
					'garantia': garantia,
				})
				total_hectareas_resumen += v['hectareas']

			# Si ninguna línea tuvo valor de cotización, dejar total_garantia en None para no mostrar "$ 0,00"
			if not tiene_alguna_garantia:
				total_garantia = None


			ctx = {
			'campaña': cd['campaña'],
			'fecha': cd['fecha'],
			'suscripcion': suscripcion,
			'socio_texto': cd['socio'],
			'lineas': lineas,

			'resumen_cultivo': resumen_cultivo,
			'resumen': resumen,
			'total_hectareas_resumen': total_hectareas_resumen if resumen else None,
			'suma_aporte_total_qq': suma_aporte_total_qq,
			'total_garantia': total_garantia,

			# cereal y suscripción (factor por soja se mantiene)
			'valor_soja': valor_soja,
			'hectareas_reales': hectareas_reales,     # ojo: ya corregido = sum(ha * participacion/100)
			'total_hectareas_brutas': total_hectareas_brutas,
			'valor_hec_real': valor_hec_real,
			'total_suscripcion': total_suscripcion,

			'consorcio': consorcio(request),
			'ahora': now().date(),
		}


			if accion == 'imprimir':
				return cotizacion_pdf_response(ctx, request)

			return render(request, self.template_name, {
				'form': form, 'formset': formset, 'soja_id':get_soja_id_por_consorcio(cons)
				})

		# Con errores
		return render(request, self.template_name, {
			'form': form, 'formset': formset, 'soja_id': get_soja_id_por_consorcio(cons)
			})

@login_required
def solicitud_pdf(request, pk):
	solicitud = get_object_or_404(Solicitud, pk=pk, consorcio=consorcio(request))
	return solicitud_pdf_response(solicitud, request)


@method_decorator(group_required('administrativo', 'contable'), name='dispatch')
class Registro(OrderQS):

	""" Registro de solicitudes """

	model = Solicitud
	filterset_class = SolicitudFilter
	template_name = 'registros/solicitudes.html'
	paginate_by = 50