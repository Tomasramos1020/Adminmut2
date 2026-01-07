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
from .models import Solicitud, SolicitudLinea, Siniestro, SiniestroLinea
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
from .forms import CotizacionForm, CotizacionLineaForm, CotizacionLineaFormSet, SiniestroForm, SiniestroLineaFormSet
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

@method_decorator(group_required('administrativo', 'contable', 'fosea'), name='dispatch')
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

	def get_context_data(self, **kwargs):
		ctx = super().get_context_data(**kwargs)

		# asegurar que 'lista' sea lo que consume la tabla
		page_obj = ctx.get('page_obj')
		lista = list(page_obj.object_list) if page_obj else list(ctx.get('object_list', []))
		ctx['lista'] = lista

		if not lista:
			return ctx

		# === cálculo liviano por Python, sin Prefetch problemático ===
		# 1) Traer líneas solo con lo necesario
		ids = [s.pk for s in lista]
		lineas = (SolicitudLinea.objects
					.filter(solicitud_id__in=ids)
					.values('solicitud_id', 'hectarea', 'participacion','subsidio_max', 'aporte_max'))

		agrup = defaultdict(list)
		for l in lineas:
			agrup[l['solicitud_id']].append((
				Decimal(l['hectarea'] or 0),
				Decimal(l['participacion'] or 0),
				Decimal(l['subsidio_max'] or 0),
				Decimal(l['aporte_max'] or 0),
			))

		# 2) Mapa consorcio -> última cotización de Soja
		cons_ids = {getattr(s.consorcio, 'id', None) for s in lista if getattr(s, 'consorcio', None)}
		cons_ids.discard(None)

		valor_soja_por_cons = {}
		if cons_ids:
			cot_qs = (Cotizacion.objects
						.filter(consorcio_id__in=cons_ids, producto__nombre__iexact='Soja')
						.only('consorcio_id', 'fecha', 'cotizacion')
						.order_by('consorcio_id', '-fecha'))
			for c in cot_qs:
				if c.consorcio_id not in valor_soja_por_cons:
					valor_soja_por_cons[c.consorcio_id] = Decimal(c.cotizacion or 0)

		# 3) Inyectar valores calculados en cada solicitud de la lista
		for s in lista:
			pares = agrup.get(s.pk, ())
			hect_totales = Decimal('0')
			hect_reales = Decimal('0')
			aporte_total_qq_sum = Decimal('0')

			for ha, part, subsidio_max, aporte_max in pares:
				ha = ha or Decimal('0')
				part = part or Decimal('0')
				subsidio_max = subsidio_max or Decimal('0')
				aporte_max = aporte_max or Decimal('0')

				# ha reales de la línea
				ha_reales_linea = (ha * part / Decimal('100'))

				# aporte QQ de la línea = ha reales * subsidio_max * (aporte_max/100)
				aporte_linea = ha * subsidio_max * (aporte_max / Decimal('100'))

				hect_totales += ha				
				hect_reales += ha_reales_linea
				aporte_total_qq_sum += aporte_linea
			hect_totales = hect_totales.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)	
			hect_reales = hect_reales.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
			aporte_total_qq_sum = aporte_total_qq_sum.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

			cons_id = getattr(s.consorcio, 'id', None)
			valor_soja = valor_soja_por_cons.get(cons_id, Decimal('0'))
			suscripcion = Decimal(getattr(s, 'suscripcion', 0) or 0)

			if valor_soja:
				valor_hec_real = ((valor_soja / Decimal('100')) * suscripcion).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
				total_suscripcion = (hect_reales * valor_hec_real).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
			else:
				valor_hec_real = Decimal('0.00')
				total_suscripcion = Decimal('0.00')

			# atributos para el template
			s.hectareas_totales_calc = hect_totales
			s.hectareas_reales_calc = hect_reales
			s.aporte_total_qq_calc = aporte_total_qq_sum
			s.total_suscripcion_calc = total_suscripcion
		return ctx


def get_soja_id_por_consorcio(cons):
	return (Cultivo.objects
			.filter(consorcio=cons, nombre__iexact="Soja")
			.values_list("id", flat=True)
			.first())

# Create your views here.
# views.py
# views.py
class CrearSolicitudView(View):
	template_name = 'crear_solicitud.html'

	def get(self, request):
		cons = consorcio(request)
		form = SolicitudForm(request=request)
		tmp = Solicitud(consorcio=cons)
		formset = SolicitudLineaFormSet(
			instance=tmp,
			prefix='form',
			form_kwargs={'request': request, 'consorcio': cons}
		)
		ctx = {'form': form, 'formset': formset, 'soja_id': get_soja_id_por_consorcio(cons)}
		return render(request, self.template_name, ctx)

	def post(self, request):
		cons = consorcio(request)
		accion = request.POST.get('accion', 'guardar')
		form = SolicitudForm(request.POST, request=request)

		if form.is_valid():
			solicitud = form.save(commit=False)
			solicitud.consorcio = cons

			formset = SolicitudLineaFormSet(
				request.POST,
				instance=solicitud,
				prefix='form',
				form_kwargs={'request': request, 'consorcio': cons}
			)
			if formset.is_valid():
				with transaction.atomic():
					solicitud.save()
					formset.save()
				solicitud.refresh_from_db()
				if accion == 'imprimir':
					return solicitud_pdf_response(solicitud, request)
				if accion == 'pagare':
					return redirect('pagare_solicitud', pk=solicitud.pk)
				return redirect('fosea')

			ctx = {'form': form, 'formset': formset, 'soja_id': get_soja_id_por_consorcio(cons)}
			return render(request, self.template_name, ctx)

		# form inválido → rearmar formset conservando filas + filtrado
		tmp = Solicitud(consorcio=cons)
		formset = SolicitudLineaFormSet(
			request.POST,
			instance=tmp,
			prefix='form',
			form_kwargs={'request': request, 'consorcio': cons}
		)
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
@method_decorator(group_required('administrativo', 'contable', 'fosea'), name='dispatch')
class EditarSolicitudView(View):
	template_name = 'editar_solicitud.html'

	def get(self, request, pk):
		cons = consorcio(request)
		solicitud = get_object_or_404(Solicitud, pk=pk, consorcio=cons)
		form = SolicitudForm(instance=solicitud, request=request)
		formset = SolicitudLineaFormSet(
			instance=solicitud,
			prefix='form',
			form_kwargs={'request': request, 'consorcio': cons}
		)
		ctx = {'form': form, 'formset': formset, 'solicitud': solicitud, 'soja_id': get_soja_id_por_consorcio(cons)}
		return render(request, self.template_name, ctx)

	def post(self, request, pk):
		cons = consorcio(request)
		accion = request.POST.get('accion', 'guardar')
		solicitud = get_object_or_404(Solicitud, pk=pk, consorcio=cons)

		form = SolicitudForm(request.POST, instance=solicitud, request=request)
		formset = SolicitudLineaFormSet(
			request.POST,
			instance=solicitud,
			prefix='form',
			form_kwargs={'request': request, 'consorcio': cons}
		)

		if form.is_valid() and formset.is_valid():
			with transaction.atomic():
				solicitud = form.save()
				formset.save()
			solicitud.refresh_from_db()

			if accion == 'imprimir':
				return solicitud_pdf_response(solicitud, request)
			if accion == 'pagare':
				return redirect('pagare_solicitud', pk=solicitud.pk)
			return redirect('fosea')

		ctx = {'form': form, 'formset': formset, 'solicitud': solicitud, 'soja_id': get_soja_id_por_consorcio(cons)}
		return render(request, self.template_name, ctx)

# views.py
from django.urls import reverse_lazy
from django.views.generic import DeleteView


@method_decorator(group_required('administrativo', 'contable', 'fosea'), name='dispatch')
class SolicitudDeleteView(DeleteView):
	model = Solicitud
	template_name = 'solicitud_confirm_delete.html'
	success_url = reverse_lazy('registro-solicitudes')  # ajustá al nombre real

	def get_queryset(self):
		"""
		Seguridad extra: solo puede borrar solicitudes
		del consorcio activo
		"""
		qs = super().get_queryset()
		return qs.filter(consorcio=consorcio(self.request))

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




from collections import defaultdict

@method_decorator(group_required('administrativo', 'contable', 'fosea'), name='dispatch')
class Registro(OrderQS):
	model = Solicitud
	filterset_class = SolicitudFilter
	template_name = 'registros/solicitudes.html'
	paginate_by = 50

	def get_context_data(self, **kwargs):
		ctx = super().get_context_data(**kwargs)

		# --- IMPORTANTE: conservar el Page original ---
		page_obj = ctx.get('page_obj')
		ctx['lista'] = page_obj     # <<--- el paginador necesita esto tal cual
		if not page_obj:
			return ctx

		# pero para cálculos usamos una lista aparte
		solicitudes = list(page_obj)

		# --- 1) Traer líneas ---
		ids = [s.pk for s in solicitudes]
		lineas = (SolicitudLinea.objects
				.filter(solicitud_id__in=ids)
				.values('solicitud_id', 'hectarea', 'participacion', 'subsidio_max', 'aporte_max'))

		agrup = defaultdict(list)
		for l in lineas:
			agrup[l['solicitud_id']].append((
				Decimal(l['hectarea'] or 0),
				Decimal(l['participacion'] or 0),
				Decimal(l['subsidio_max'] or 0),
				Decimal(l['aporte_max'] or 0),
			))

		# --- 2) Cotización de soja ---
		cons_ids = {getattr(s.consorcio, 'id', None) for s in solicitudes if getattr(s, 'consorcio', None)}
		cons_ids.discard(None)

		valor_soja_por_cons = {}
		if cons_ids:
			cot_qs = (Cotizacion.objects
					.filter(consorcio_id__in=cons_ids, producto__nombre__iexact='Soja')
					.only('consorcio_id', 'fecha', 'cotizacion')
					.order_by('consorcio_id', '-fecha'))
			for c in cot_qs:
				if c.consorcio_id not in valor_soja_por_cons:
					valor_soja_por_cons[c.consorcio_id] = Decimal(c.cotizacion or 0)

		# --- 3) Inyectar cálculos ---
		for s in solicitudes:
			pares = agrup.get(s.pk, ())
			hect_totales = Decimal('0')
			hect_reales = Decimal('0')
			aporte_total_qq_sum = Decimal('0')

			for ha, part, subsidio_max, aporte_max in pares:
				ha_reales_linea = (ha * part / Decimal('100'))
				aporte_linea = ha * subsidio_max * (aporte_max / Decimal('100'))

				hect_totales += ha
				hect_reales += ha_reales_linea
				aporte_total_qq_sum += aporte_linea

			# redondeo
			hect_totales = hect_totales.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
			hect_reales = hect_reales.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
			aporte_total_qq_sum = aporte_total_qq_sum.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

			cons_id = getattr(s.consorcio, 'id', None)
			valor_soja = valor_soja_por_cons.get(cons_id, Decimal('0'))
			suscripcion = Decimal(getattr(s, 'suscripcion', 0) or 0)

			if valor_soja:
				valor_hec_real = ((valor_soja / Decimal('100')) * suscripcion).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
				total_suscripcion = (hect_reales * valor_hec_real).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
			else:
				valor_hec_real = Decimal('0.00')
				total_suscripcion = Decimal('0.00')

			# atributos para el template
			s.hectareas_totales_calc = hect_totales
			s.hectareas_reales_calc = hect_reales
			s.aporte_total_qq_calc = aporte_total_qq_sum
			s.total_suscripcion_calc = total_suscripcion

		return ctx


# views.py (o donde tengas tus endpoints fosea)
from django.views.decorators.http import require_GET

@login_required
@require_GET
def franquicia_por_zona_cultivo(request):
	cons = consorcio(request)
	cultivo_id = request.GET.get('cultivo_id')
	establecimiento_id = request.GET.get('establecimiento_id')

	if not (cultivo_id and establecimiento_id):
		return JsonResponse({'franquicia': None}, status=200)

	try:
		est = Establecimiento.objects.get(pk=establecimiento_id, consorcio=cons)
		zpc = ZonasPorCultivo.objects.get(
			consorcio=cons, zona=est.zona_id, cultivo_id=cultivo_id
		)
		return JsonResponse({'franquicia': float(zpc.franquicia)})
	except (Establecimiento.DoesNotExist, ZonasPorCultivo.DoesNotExist):
		return JsonResponse({'franquicia': None}, status=200)

@login_required
@require_GET
def establecimientos_filtrados(request):
	"""
	Devuelve los establecimientos del socio elegido
	que además tengan solicitudes en la campaña seleccionada.
	"""
	cons = consorcio(request)
	socio_id = request.GET.get("socio_id")
	campaña_id = request.GET.get("campaña_id")

	if not socio_id:
		return JsonResponse({"establecimientos": []})

	# Todos los establecimientos del socio en este consorcio
	establecimientos = Establecimiento.objects.filter(
		consorcio=cons, socio__id=socio_id
	)

	# Si se eligió campaña → filtramos por los usados en esa campaña
	if campaña_id:
		usados = SolicitudLinea.objects.filter(
			solicitud__consorcio=cons,
			solicitud__socio_id=socio_id,
			solicitud__campaña_id=campaña_id
		).values_list("establecimiento_id", flat=True).distinct()
		establecimientos = establecimientos.filter(id__in=usados)

	data = [
		{"id": e.id, "nombre": e.nombre}
		for e in establecimientos.order_by("nombre").distinct()
	]
	return JsonResponse({"establecimientos": data})

	
@login_required
@require_GET
def cobertura_por_cultivo(request):
	"""
	Devuelve la cobertura máxima (subsidio_max) del cultivo y establecimiento
	según el socio y la campaña seleccionados.
	"""
	cons = consorcio(request)
	cultivo_id = request.GET.get('cultivo_id')
	establecimiento_id = request.GET.get('establecimiento_id')
	socio_id = request.GET.get('socio_id')
	campaña_id = request.GET.get('campaña_id')

	if not all([cultivo_id, establecimiento_id, socio_id, campaña_id]):
		return JsonResponse({'cobertura': None})

	from fosea.models import SolicitudLinea
	from django.db.models import Max

	max_subsidio = (
		SolicitudLinea.objects
		.filter(
			solicitud__consorcio=cons,
			solicitud__socio_id=socio_id,
			solicitud__campaña_id=campaña_id,
			establecimiento_id=establecimiento_id,
			cultivo_id=cultivo_id,
		)
		.aggregate(Max('subsidio_max'))
		.get('subsidio_max__max')
	)

	return JsonResponse({'cobertura': max_subsidio or None})

from django.db.models import Q

@login_required
@require_GET
def denuncias_disponibles(request):
    cons = consorcio(request)
    socio_id = request.GET.get("socio_id")
    actual_id = request.GET.get("actual_id")  # <- denuncia actual (opcional)

    if not socio_id:
        return JsonResponse({"denuncias": []})

    q = Q(consorcio=cons, socio_id=socio_id) & Q(siniestro__isnull=True)

    # ✅ en edición: incluir la denuncia actual aunque ya esté usada
    if actual_id:
        q = q | (Q(consorcio=cons, socio_id=socio_id) & Q(id=actual_id))

    denuncias = Denuncia.objects.filter(q).distinct().order_by('-fecha')

    data = [
        {"id": d.id, "texto": f"{d.fecha.strftime('%d/%m/%Y')} - {d.campaña}"}
        for d in denuncias
    ]
    return JsonResponse({"denuncias": data})



@method_decorator(group_required('administrativo', 'contable', 'fosea'), name='dispatch')
class CrearSiniestroView(View):
	template_name = 'crear_siniestro.html'

	def get(self, request):
		cons = consorcio(request)
		form = SiniestroForm(request=request)
		tmp = Siniestro(consorcio=cons)  # no se guarda
		formset = SiniestroLineaFormSet(
			instance=tmp,
			prefix='form',
			form_kwargs={'request': request, 'consorcio': cons, 'socio': None},  # socio aún no elegido
		)
		return render(request, self.template_name, {'form': form, 'formset': formset})


	def post(self, request):
		cons = consorcio(request)
		form = SiniestroForm(request.POST, request=request)

		if form.is_valid():
			# Creamos el siniestro pero sin guardar todavía
			siniestro = form.save(commit=False)
			siniestro.consorcio = cons
			socio = siniestro.socio

			# Asignamos los datos al formset
			formset = SiniestroLineaFormSet(
				request.POST,
				instance=siniestro,
				prefix='form',
				form_kwargs={'request': request, 'consorcio': cons, 'socio': socio},
			)

			# ⚠️ Inyectamos manualmente el siniestro con sus datos para que el formset lo use
			# (aunque todavía no esté guardado)
			for f in formset.forms:
				f.instance.siniestro = siniestro

			# Validamos ambos
			if formset.is_valid():
				with transaction.atomic():
					siniestro.save()  # recién acá se guarda realmente
					formset.instance = siniestro
					formset.save()
				return redirect('fosea')
			else:
				# formset inválido → NO se guarda el siniestro
				return render(request, self.template_name, {'form': form, 'formset': formset})

		# form inválido → rearmamos formset vacío
		tmp = Siniestro(consorcio=cons)
		socio_id = request.POST.get('socio')
		socio_obj = Socio.objects.filter(pk=socio_id, consorcio=cons).first() if socio_id else None

		formset = SiniestroLineaFormSet(
			request.POST,
			instance=tmp,
			prefix='form',
			form_kwargs={'request': request, 'consorcio': cons, 'socio': socio_obj},
		)
		return render(request, self.template_name, {'form': form, 'formset': formset})

		

@method_decorator(group_required('administrativo', 'contable', 'fosea'), name='dispatch')
class RegistroSiniestros(OrderQS):
	model = Siniestro
	filterset_class = SiniestroFilter
	template_name = 'registros/siniestros.html'
	paginate_by = 50

	def get_queryset(self):
		# limitar por consorcio
		qs = super().get_queryset().filter(consorcio=consorcio(self.request))
		# ordenar por fecha desc por defecto
		return qs.order_by('-fecha', '-id')

	def get_context_data(self, **kwargs):
		ctx = super().get_context_data(**kwargs)

		page_obj = ctx.get('page_obj')

		# dejar el Page original para el paginador
		ctx['lista'] = page_obj

		# pero usar una lista para el cálculo interno
		lista = list(page_obj) if page_obj else []

		if not lista:
			return ctx

		# 1) Cargar líneas necesarias en una sola consulta "liviana"
		ids = [s.pk for s in lista]
		lineas = (SiniestroLinea.objects
				  .filter(siniestro_id__in=ids)
				  .values('siniestro_id', 'hectareas_afectadas', 'danio_porcentaje',
						  'franquicia_porcentaje', 'cobertura_qq'))

		agrup = defaultdict(list)
		for l in lineas:
			agrup[l['siniestro_id']].append((
				Decimal(l['hectareas_afectadas'] or 0),
				Decimal(l['danio_porcentaje'] or 0),
				Decimal(l['franquicia_porcentaje'] or 0),
				Decimal(l['cobertura_qq'] or 0),
			))

		# 2) Calcular sumas por siniestro (ha afectadas + indemnización total)
		for s in lista:
			pares = agrup.get(s.pk, ())
			ha_total = Decimal('0')
			total_indemnizacion = Decimal('0')

			for ha, danio, franq, cob in pares:
				ha = ha or 0
				exceso = max(Decimal('0'), danio - franq) / Decimal('100')
				ind = ha * cob * exceso
				ha_total += ha
				total_indemnizacion += ind

			s.ha_afectadas_calc = ha_total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
			s.indemnizacion_total_calc = total_indemnizacion.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
			s.cant_lineas_calc = len(pares)

		return ctx

from django.contrib import messages

@method_decorator(group_required('administrativo', 'contable', 'fosea'), name='dispatch')
class EditarSiniestroView(View):
	template_name = 'editar_siniestro.html'  # si preferís, usá 'editar_siniestro.html'

	def get(self, request, pk):
		cons = consorcio(request)
		siniestro = get_object_or_404(Siniestro, pk=pk, consorcio=cons)
		form = SiniestroForm(instance=siniestro, request=request)
		formset = SiniestroLineaFormSet(
			instance=siniestro,
			prefix='form',
			form_kwargs={'request': request, 'consorcio': cons, 'socio': siniestro.socio},
		)
		return render(request, self.template_name, {
			'form': form,
			'formset': formset,
			'siniestro': siniestro,   # por si querés mostrar #ID en el header
			'modo_edicion': True,     # para cambiar título/botones en el template
		})

	def post(self, request, pk):
		cons = consorcio(request)
		siniestro = get_object_or_404(Siniestro, pk=pk, consorcio=cons)

		form = SiniestroForm(request.POST, instance=siniestro, request=request)
		socio_post = Socio.objects.filter(pk=request.POST.get('socio'), consorcio=cons).first() or siniestro.socio

		formset = SiniestroLineaFormSet(
			request.POST,
			instance=siniestro,
			prefix='form',
			form_kwargs={'request': request, 'consorcio': cons, 'socio': socio_post},
		)

		if form.is_valid() and formset.is_valid():
			with transaction.atomic():
				form.save()
				formset.save()
			messages.success(request, "Siniestro actualizado correctamente.")
			return redirect('registro_siniestros')  # o 'fosea' si preferís
		return render(request, self.template_name, {
			'form': form,
			'formset': formset,
			'siniestro': siniestro,
			'modo_edicion': True,
		})

@method_decorator(group_required('administrativo', 'contable', 'fosea'), name='dispatch')
class SiniestroDeleteView(DeleteView):
	model = Siniestro
	template_name = 'siniestro_confirm_delete.html'
	success_url = reverse_lazy('registro_siniestros')

	def get_queryset(self):
		qs = super().get_queryset()
		return qs.filter(consorcio=consorcio(self.request))

@method_decorator(group_required('administrativo', 'contable', 'fosea'), name='dispatch')
class CrearDenunciaView(View):
	template_name = 'crear_denuncia.html'

	def get(self, request):
		cons = consorcio(request)
		form = DenunciaForm(request=request)
		tmp = Denuncia(consorcio=cons)
		formset = DenunciaLineaFormSet(
			instance=tmp,
			prefix='form',
			form_kwargs={'request': request, 'consorcio': cons, 'socio': None}
		)
		return render(request, self.template_name, {'form': form, 'formset': formset})

	def post(self, request):
		cons = consorcio(request)
		form = DenunciaForm(request.POST, request=request)

		if form.is_valid():
			denuncia = form.save(commit=False)
			denuncia.consorcio = cons
			socio = denuncia.socio

			formset = DenunciaLineaFormSet(
				request.POST,
				instance=denuncia,
				prefix='form',
				form_kwargs={'request': request, 'consorcio': cons, 'socio': socio}
			)

			# inyectamos denuncia
			for f in formset.forms:
				f.instance.denuncia = denuncia

			if formset.is_valid():
				with transaction.atomic():
					denuncia.save()
					formset.instance = denuncia
					formset.save()
				return redirect('fosea')

			return render(request, self.template_name, {'form': form, 'formset': formset})

		tmp = Denuncia(consorcio=cons)
		formset = DenunciaLineaFormSet(
			request.POST,
			instance=tmp,
			prefix='form',
			form_kwargs={'request': request, 'consorcio': cons, 'socio': None}
		)
		return render(request, self.template_name, {'form': form, 'formset': formset})

@method_decorator(group_required('administrativo', 'contable', 'fosea'), name='dispatch')
class EditarDenunciaView(View):
	template_name = 'editar_denuncia.html'

	def get(self, request, pk):
		cons = consorcio(request)
		denuncia = get_object_or_404(Denuncia, pk=pk, consorcio=cons)

		form = DenunciaForm(instance=denuncia, request=request)
		formset = DenunciaLineaFormSet(
			instance=denuncia,
			prefix='form',
			form_kwargs={'request': request, 'consorcio': cons, 'socio': denuncia.socio}
		)

		return render(request, self.template_name, {
			'form': form,
			'formset': formset,
			'denuncia': denuncia,
			'modo_edicion': True
		})

	def post(self, request, pk):
		cons = consorcio(request)
		denuncia = get_object_or_404(Denuncia, pk=pk, consorcio=cons)

		form = DenunciaForm(request.POST, instance=denuncia, request=request)
		formset = DenunciaLineaFormSet(
			request.POST,
			instance=denuncia,
			prefix='form',
			form_kwargs={'request': request, 'consorcio': cons, 'socio': denuncia.socio}
		)

		if form.is_valid() and formset.is_valid():
			with transaction.atomic():
				form.save()
				formset.save()
			messages.success(request, "Denuncia actualizada correctamente.")
			return redirect('registro_deudas')

		return render(request, self.template_name, {
			'form': form,
			'formset': formset,
			'denuncia': denuncia,
			'modo_edicion': True
		})

@method_decorator(group_required('administrativo', 'contable', 'fosea'), name='dispatch')
class DenunciaDeleteView(DeleteView):
	model = Denuncia
	template_name = 'denuncia_confirm_delete.html'
	success_url = reverse_lazy('registro_denuncias')

	def get_queryset(self):
		qs = super().get_queryset()
		return qs.filter(consorcio=consorcio(self.request))

@method_decorator(group_required('administrativo', 'contable', 'fosea'), name='dispatch')
class RegistroDenuncias(OrderQS):
	model = Denuncia
	filterset_class = DenunciaFilter
	template_name = 'registros/denuncias.html'
	paginate_by = 50

	def get_queryset(self):
		return super().get_queryset().filter(consorcio=consorcio(self.request))\
			.select_related('socio', 'campaña')\
			.order_by('-fecha','-id')

	def get_context_data(self, **kwargs):
		ctx = super().get_context_data(**kwargs)

		page_obj = ctx.get('page_obj')
		ctx['lista'] = page_obj

		denuncias = list(page_obj) if page_obj else []
		if not denuncias:
			return ctx

		ids = [d.pk for d in denuncias]

		lineas = (DenunciaLinea.objects
			.filter(denuncia_id__in=ids)
			.values('denuncia_id', 'hectareas_afectadas')
		)

		agrup = defaultdict(list)
		for l in lineas:
			agrup[l['denuncia_id']].append(Decimal(l['hectareas_afectadas'] or 0))

		for d in denuncias:
			hs = agrup.get(d.pk, [])
			d.ha_denunciadas_calc = sum(hs).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
			d.cant_lineas_calc = len(hs)

		return ctx


