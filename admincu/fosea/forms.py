from django import forms
from django.forms import inlineformset_factory
from django.forms import formset_factory, BaseFormSet
from .models import Solicitud, SolicitudLinea, Siniestro, SiniestroLinea, Denuncia, DenunciaLinea
from arquitectura.models import Establecimiento, Socio, ZonasPorCultivo
from admincu.funciones import consorcio
from django.forms.widgets import DateInput
from django.forms import modelformset_factory, inlineformset_factory, BaseInlineFormSet
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet
from arquitectura.models import Campaña, Zona, Cultivo, Establecimiento

# forms.py
class SolicitudForm(forms.ModelForm):
	fecha = forms.DateField(
		widget=forms.DateInput(
			attrs={'type': 'date', 'class': 'form-control'},
			format='%Y-%m-%d',
		),
		input_formats=['%Y-%m-%d', '%d/%m/%Y'],  # acepta ambos al recibir POST
	)
	class Meta:
		model = Solicitud
		fields = ['suscripcion', 'fecha', 'campaña', 'socio']
		widgets = {
			'fecha': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
		}

	def __init__(self, *args, **kwargs):
		request = kwargs.pop('request', None)
		super().__init__(*args, **kwargs)
		if request:
			cons = consorcio(request)
			self.fields['socio'].queryset = (
				self.fields['socio'].queryset
				.filter(consorcio=cons, es_socio=True, baja__isnull=True)
				.exclude(nombre_servicio_mutual__isnull=False)
			)
			self.fields['campaña'].queryset = self.fields['campaña'].queryset.filter(consorcio=cons)
	def clean(self):
		cleaned = super().clean()
		faltantes = []
		for campo in ('campaña', 'fecha', 'suscripcion', 'socio'):
			if not cleaned.get(campo):
				faltantes.append(campo)
		if faltantes:
			raise ValidationError('Completá todos los campos: campaña, fecha, suscripción y socio.')
		return cleaned

	

class SolicitudLineaForm(forms.ModelForm):
	# Campo extra (no se guarda), solo informativo
	franquicia = forms.DecimalField(required=False, disabled=True, max_digits=10, decimal_places=2)

	class Meta:
		model = SolicitudLinea
		fields = [
			'establecimiento',
			'participacion',
			'cultivo',
			'subsidio_max',
			'aporte_max',
			'aporte_total_qq',
			'hectarea',
		]
		widgets = {
			'establecimiento': forms.Select(attrs={'class': 'form-control'}),
			'participacion': forms.NumberInput(attrs={'class': 'form-control'}),
			'cultivo': forms.Select(attrs={'class': 'form-control'}),
			'subsidio_max': forms.NumberInput(attrs={'class': 'form-control'}),
			'aporte_max': forms.NumberInput(attrs={'class': 'form-control'}),
			'aporte_total_qq': forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
			'hectarea': forms.NumberInput(attrs={'class': 'form-control'}),
		}

	def clean(self):
		cleaned = super().clean()
		est = cleaned.get('establecimiento')
		cultivo = cleaned.get('cultivo')
		subsidio_max = cleaned.get('subsidio_max') or Decimal('0')
		aporte_max = cleaned.get('aporte_max') or Decimal('0')
		hectarea = cleaned.get('hectarea') or Decimal('0')

		if not (est and cultivo and hectarea):
			return cleaned

		# Validación contra subsidio máximo por zona/cultivo
		if est and est.zona_id and cultivo:
			try:
				zpc = ZonasPorCultivo.objects.get(zona=est.zona, cultivo=cultivo)
				if subsidio_max > zpc.subsidio_maximo:
					self.add_error('subsidio_max', f'No puede superar {zpc.subsidio_maximo}.')
			except ZonasPorCultivo.DoesNotExist:
				pass

		# Recalcular en servidor (evita manipulaciones del cliente)
		aporte_total = cleaned.get('aporte_total_qq') or Decimal('0')
		cleaned['aporte_total_qq'] = aporte_total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
		if aporte_total <= 0:
			self.add_error('aporte_total_qq', 'El aporte total debe ser mayor a 0.')
		return cleaned

	def __init__(self, *args, **kwargs):
		request = kwargs.pop('request', None)
		cons = kwargs.pop('consorcio', None)
		super().__init__(*args, **kwargs)

		if request and not cons:
			cons = consorcio(request)

		if cons:
			# Si Cultivo tiene FK a Consorcio:
			try:
				self.fields['cultivo'].queryset = (
					self.fields['cultivo'].queryset.filter(consorcio=cons)
				)
			except Exception:
				# Fallback si Cultivo NO tiene FK directo a Consorcio:
				from .models import Cultivo, ZonasPorCultivo
				self.fields['cultivo'].queryset = Cultivo.objects.filter(
					zonasporcultivo__zona__consorcio=cons
				).distinct()

			# Por las dudas, también ajustá Establecimiento al consorcio
			if 'establecimiento' in self.fields:
				self.fields['establecimiento'].queryset = (
					self.fields['establecimiento'].queryset.filter(consorcio=cons)
				)


class LineasBaseFormSet(BaseInlineFormSet):
	def clean(self):
		super().clean()
		lineas_validas = 0

		# Campos núcleo que definen si la fila es "real"
		CORE_FIELDS = ('establecimiento', 'cultivo', 'hectarea')

		for form in self.forms:
			if getattr(form, "cleaned_data", None) is None:
				continue

			cd = form.cleaned_data

			if self.can_delete and cd.get("DELETE"):
				continue

			# ▶ Solo consideramos "hay algo" si tocó un campo núcleo
			def _hay_nucleo(cd):
				return any(cd.get(k) not in (None, "", 0, Decimal("0")) for k in CORE_FIELDS)

			# Si Django permite fila vacía, descartá filas sin núcleo
			if form.empty_permitted and not _hay_nucleo(cd):
				# Si cambió algo pero no completó núcleo => error (opcional)
				if form.has_changed():
					form.add_error(None, "Complete Establecimiento, Cultivo y Hectáreas o elimine la fila.")
				else:
					cd['DELETE'] = True
				continue

			# Llegamos a una línea real
			lineas_validas += 1

			# Regla: aporte_total_qq > 0
			aporte_total = cd.get("aporte_total_qq")
			if aporte_total is None or aporte_total <= 0:
				form.add_error("aporte_total_qq", "Debe ser mayor a 0.")

		if lineas_validas == 0:
			raise ValidationError("Debés cargar al menos una línea de solicitud.")





# Inline formset que ata las líneas a una Solicitud
SolicitudLineaFormSet = inlineformset_factory(
	parent_model=Solicitud,
	model=SolicitudLinea,
	form=SolicitudLineaForm,
	formset=LineasBaseFormSet,   # 👈 importante
	extra=0,
	can_delete=True,
	min_num=1,
	validate_min=True,
)


class CotizacionForm(forms.Form):
	campaña = forms.ModelChoiceField(queryset=Campaña.objects.none())
	fecha = forms.DateField(
		widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
		input_formats=['%Y-%m-%d', '%d/%m/%Y']
	)
	suscripcion = forms.DecimalField(max_digits=10, decimal_places=2)
	socio = forms.CharField(label="Socio", max_length=255)

	def __init__(self, *args, **kwargs):
		request = kwargs.pop('request', None)
		super().__init__(*args, **kwargs)
		if request:
			self.fields['campaña'].queryset = Campaña.objects.filter(consorcio=consorcio(request))
		for name in self.fields:
			self.fields[name].widget.attrs.setdefault('class', 'form-control')

	def clean(self):
		cleaned = super().clean()
		faltantes = []
		for campo in ('campaña', 'fecha', 'suscripcion', 'socio'):
			if not cleaned.get(campo):
				faltantes.append(campo)
		if faltantes:
			raise ValidationError('Completá todos los campos: campaña, fecha, suscripción y socio.')
		return cleaned


class CotizacionLineaForm(forms.Form):
	establecimiento = forms.CharField(max_length=255, required=False)
	departamento = forms.CharField(max_length=100, required=False)
	gps = forms.CharField(max_length=100, required=False)
	zona = forms.ModelChoiceField(queryset=Zona.objects.none(), required=False)
	cultivo = forms.ModelChoiceField(queryset=Cultivo.objects.none(), required=False)
	hectarea = forms.DecimalField(max_digits=10, decimal_places=2, required=False)
	participacion = forms.DecimalField(max_digits=5, decimal_places=2, required=False)
	subsidio_max = forms.DecimalField(max_digits=10, decimal_places=2, required=False)
	franquicia = forms.DecimalField(max_digits=5, decimal_places=2, required=False)
	aporte_max = forms.DecimalField(max_digits=5, decimal_places=2, required=False)
	aporte_total_qq = forms.DecimalField(max_digits=12, decimal_places=2, required=False,
										 widget=forms.NumberInput(attrs={'readonly': 'readonly'}))

	def __init__(self, *args, **kwargs):
		request = kwargs.pop('request', None)
		super().__init__(*args, **kwargs)
		if request:
			self.fields['zona'].queryset = Zona.objects.filter(consorcio=consorcio(request))
			self.fields['cultivo'].queryset = Cultivo.objects.filter(consorcio=consorcio(request))
		for name in self.fields:
			self.fields[name].widget.attrs.setdefault('class', 'form-control')

		# 👇 Hacerlos solo lectura (se envían en POST)
		self.fields['franquicia'  ].widget.attrs['readonly'] = 'readonly'
		self.fields['aporte_max'  ].widget.attrs['readonly'] = 'readonly'

	def clean(self):
		cleaned = super().clean()

		# Detectar fila vacía (todo vacío) => permitimos
		vacios = all(
			(cleaned.get(k) in (None, '', 0, Decimal('0')) or k in ('subsidio_max', 'franquicia', 'aporte_max', 'aporte_total_qq'))
			for k in cleaned.keys()
		)
		if vacios:
			return cleaned

		# Si hay datos: zona y cultivo requeridos
		if not cleaned.get('zona'):
			self.add_error('zona', 'Seleccioná una zona.')
		if not cleaned.get('cultivo'):
			self.add_error('cultivo', 'Seleccioná un cultivo.')

		# Recalcular aporte_total_qq si hay datos numéricos
		hect = cleaned.get('hectarea') or Decimal('0')
		subsidio = cleaned.get('subsidio_max') or Decimal('0')
		aporte_max = cleaned.get('aporte_max') or Decimal('0')
		aporte_total = hect * subsidio * (aporte_max / Decimal('100'))
		cleaned['aporte_total_qq'] = aporte_total

		# Reglas simples
		if aporte_total <= 0:
			self.add_error('aporte_total_qq', 'El aporte total debe ser mayor a 0.')

		return cleaned


class _BaseCotizacionLineaFormSet(BaseFormSet):
	def clean(self):
		super().clean()
		lineas_validas = 0
		for form in self.forms:
			if getattr(form, 'cleaned_data', None) is None:
				continue
			if self.can_delete and form.cleaned_data.get('DELETE'):
				continue

			# considerar vacía
			cd = form.cleaned_data
			hay_algo = any(
				v not in (None, '', 0, Decimal('0'))
				for k, v in cd.items()
				if k not in ('DELETE',)
			)
			if not hay_algo:
				continue

			lineas_validas += 1

			if cd.get('aporte_total_qq') in (None, '') or Decimal(cd.get('aporte_total_qq')) <= 0:
				form.add_error('aporte_total_qq', 'Debe ser mayor a 0.')

		if lineas_validas == 0:
			raise ValidationError('Debés cargar al menos una línea.')

CotizacionLineaFormSet = formset_factory(
	CotizacionLineaForm,
	formset=_BaseCotizacionLineaFormSet,
	extra=1,
	can_delete=True,
	validate_min=False,
)
# forms.py
class EstablecimientoModalForm(forms.ModelForm):
	class Meta:
		model = Establecimiento
		fields = ['nombre', 'dpto', 'gps', 'zona']   # 👈 sin socio_1..5
		labels = {
			'nombre': 'Nombre',
			'dpto': 'Departamento',
			'gps': 'GPS',
			'zona': 'Zona',
		}

	def __init__(self, consorcio=None, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.consorcio = consorcio
		if self.fields.get('zona') is not None and consorcio is not None:
			self.fields['zona'].queryset = Zona.objects.filter(consorcio=consorcio)
		# si necesitás filtrar zona por consorcio, podés hacerlo acá




class SiniestroForm(forms.ModelForm):
	fecha = forms.DateField(
		widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
		input_formats=['%Y-%m-%d', '%d/%m/%Y']
	)

	class Meta:
		model = Siniestro
		fields = ['fecha', 'campaña', 'socio', 'denuncia']
		widgets = {
			'socio': forms.Select(attrs={'class': 'form-control'}),
			'campaña': forms.Select(attrs={'class': 'form-control'}),
			'denuncia': forms.Select(attrs={'class': 'form-control'}),
		}

	def __init__(self, *args, **kwargs):
		request = kwargs.pop('request', None)
		super().__init__(*args, **kwargs)

		if request:
			cons = consorcio(request)

			# Campañas / socios
			self.fields['campaña'].queryset = Campaña.objects.filter(consorcio=cons)
			self.fields['socio'].queryset = (self.fields['socio'].queryset
				.filter(consorcio=cons, es_socio=True, baja__isnull=True)
				.exclude(nombre_servicio_mutual__isnull=False)
			)

			# ✅ Determinar socio elegido (POST o instance)
			socio_id = None
			if self.is_bound:
				socio_id = self.data.get('socio') or self.data.get('siniestro-socio')  # por si cambia el name
			if not socio_id and self.instance and getattr(self.instance, "socio_id", None):
				socio_id = self.instance.socio_id

			# ✅ Queryset de denuncias válido (las disponibles)
			qs = Denuncia.objects.filter(consorcio=cons)
			if socio_id:
				qs = qs.filter(socio_id=socio_id)

			# Solo denuncias sin siniestro
			disponibles = qs.filter(siniestro__isnull=True)

			# ✅ si estás editando y ya tenía una denuncia, incluirla aunque esté “ocupada”
			if self.instance and self.instance.pk and self.instance.denuncia_id:
				disponibles = (disponibles | qs.filter(id=self.instance.denuncia_id)).distinct()

			self.fields['denuncia'].queryset = disponibles.order_by('-fecha')
			self.fields['denuncia'].required = False

		for f in self.fields.values():
			f.widget.attrs.setdefault('class', 'form-control')


	def clean(self):
		cd = super().clean()
		faltan = [k for k in ('fecha','campaña','socio') if not cd.get(k)]
		if faltan:
			raise ValidationError("Completá fecha, campaña y socio.")
		return cd

from django.db.models import Sum

class SiniestroLineaForm(forms.ModelForm):
	franquicia_porcentaje = forms.DecimalField(
		label="Franquicia (%)", max_digits=5, decimal_places=2, required=False, disabled=True
	)
	cobertura_qq = forms.DecimalField(
		label="Cobertura", max_digits=10, decimal_places=2, required=True, disabled=False
	)
	hectareas_afectadas = forms.DecimalField(
		label="Has Afectadas", max_digits=10, decimal_places=2, required=True
	)
	indemnizacion_qq = forms.DecimalField(
	label="Indemnización (QQ)", max_digits=14, decimal_places=2,
	required=False, disabled=True
	)
	indemnizacion_ajustada = forms.DecimalField(
		label="Indemnización Ajustada ($)", max_digits=14, decimal_places=2,
		required=False, disabled=True
	)


	class Meta:
		model = SiniestroLinea
		fields = [
			'establecimiento', 'cultivo',
			'hectareas_afectadas', 'danio_porcentaje',
			'franquicia_porcentaje', 'cobertura_qq',
			'estadio', 'liberacion','indemnizacion_qq',
			'indemnizacion_ajustada',
		]
		widgets = {
			'establecimiento': forms.Select(attrs={'class': 'form-control'}),
			'cultivo': forms.Select(attrs={'class': 'form-control'}),
			'danio_porcentaje': forms.NumberInput(attrs={'class': 'form-control'}),
			'estadio': forms.TextInput(attrs={'class': 'form-control'}),
			'liberacion': forms.Select(attrs={'class': 'form-control'}),
		}


	def __init__(self, *args, **kwargs):
		request = kwargs.pop('request', None)
		cons = kwargs.pop('consorcio', None)
		socio = kwargs.pop('socio', None)  # lo pasamos desde la view
		super().__init__(*args, **kwargs)

		if request and not cons:
			cons = consorcio(request)

		if cons:
			self.fields['cultivo'].queryset = Cultivo.objects.filter(consorcio=cons)
			# Establecimientos del socio:
			if socio:
				self.fields['establecimiento'].queryset = Establecimiento.objects.filter(
					consorcio=cons, socio__id=socio.id
				).distinct()
			else:
				self.fields['establecimiento'].queryset = Establecimiento.objects.filter(consorcio=cons)

	def clean(self):
		cd = super().clean()
		est = cd.get('establecimiento')
		ha_afectadas = cd.get('hectareas_afectadas') or Decimal('0')
		siniestro = getattr(self.instance, 'siniestro', None)

		# Validaciones básicas
		if not est:
			self.add_error('establecimiento', 'Seleccioná el establecimiento.')
		if not cd.get('cultivo'):
			self.add_error('cultivo', 'Seleccioná el cultivo.')
		if ha_afectadas <= 0:
			self.add_error('hectareas_afectadas', 'Debe ser mayor a 0.')

		danio = cd.get('danio_porcentaje') or Decimal('0')
		if danio <= 0:
			self.add_error('danio_porcentaje', 'Debe ser mayor a 0.')

		cob = cd.get('cobertura_qq') or Decimal('0')
		if cob <= 0:
			self.add_error('cobertura_qq', 'Debe ser mayor a 0.')

		return cd

class _LineasSiniestroBaseFormSet(BaseInlineFormSet):
	def clean(self):
		super().clean()
		validas = 0
		siniestro = self.instance  # 💡 Usamos la instancia aunque no tenga pk

		for i, form in enumerate(self.forms, start=1):
			if not hasattr(form, "cleaned_data") or not form.cleaned_data:
				continue
			cd = form.cleaned_data
			if self.can_delete and cd.get("DELETE"):
				continue

			est = cd.get("establecimiento")
			ha_afectadas = cd.get("hectareas_afectadas") or Decimal("0")

			if siniestro and est and siniestro.campaña and siniestro.socio:
				total_ha_solicitud = (
					SolicitudLinea.objects.filter(
						solicitud__campaña=siniestro.campaña,
						solicitud__socio=siniestro.socio,
						solicitud__consorcio=siniestro.consorcio,
						establecimiento=est
					)
					.aggregate(total=Sum("hectarea"))
					.get("total") or Decimal("0")
				)


				if total_ha_solicitud == 0:
					form.add_error(
						"hectareas_afectadas",
						f'El establecimiento "{est}" no tiene solicitudes en la campaña {siniestro.campaña}.'
					)
				elif ha_afectadas > total_ha_solicitud:
					form.add_error(
						"hectareas_afectadas",
						f'Las hectáreas afectadas ({ha_afectadas}) superan las {total_ha_solicitud} declaradas '
						f'en solicitudes del establecimiento en la campaña {siniestro.campaña}.'
					)






SiniestroLineaFormSet = inlineformset_factory(
	parent_model=Siniestro,
	model=SiniestroLinea,
	form=SiniestroLineaForm,
	formset=_LineasSiniestroBaseFormSet,
	extra=0,
	can_delete=True,
	min_num=1,
	validate_min=True,
)

class DenunciaForm(forms.ModelForm):
	fecha = forms.DateField(
		widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
		input_formats=['%Y-%m-%d', '%d/%m/%Y']
	)
	class Meta:
		model = Denuncia
		fields = ['fecha', 'campaña', 'socio']
		widgets = {
			'campaña': forms.Select(attrs={'class': 'form-control'}),
			'socio': forms.Select(attrs={'class': 'form-control'}),
		}

	def __init__(self, *args, **kwargs):
		request = kwargs.pop('request', None)
		super().__init__(*args, **kwargs)

		if request:
			cons = consorcio(request)
			self.fields['campaña'].queryset = Campaña.objects.filter(consorcio=cons)
			self.fields['socio'].queryset = Socio.objects.filter(consorcio=cons)

class DenunciaLineaForm(forms.ModelForm):
	class Meta:
		model = DenunciaLinea
		fields = ['establecimiento', 'cultivo', 'hectareas_afectadas', 'observacion']
		widgets = {
			'establecimiento': forms.Select(attrs={'class': 'form-control'}),
			'cultivo': forms.Select(attrs={'class': 'form-control'}),
			'hectareas_afectadas': forms.NumberInput(attrs={'class': 'form-control'}),
			'observacion': forms.TextInput(attrs={'class': 'form-control'}),
		}

	def __init__(self, *args, **kwargs):
		request = kwargs.pop('request', None)
		cons = kwargs.pop('consorcio', None)
		socio = kwargs.pop('socio', None)
		campaña = kwargs.pop('campaña', None)
		super().__init__(*args, **kwargs)

		if request and not cons:
			cons = consorcio(request)

		if cons:
			self.fields['cultivo'].queryset = Cultivo.objects.filter(consorcio=cons)
			establecimientos_qs = Establecimiento.objects.filter(consorcio=cons)
			if socio:
				establecimientos_qs = establecimientos_qs.filter(socio__id=socio.id)

				campaña_id = getattr(campaña, "id", campaña)
				if campaña_id:
					usados = (SolicitudLinea.objects
						.filter(
							solicitud__consorcio=cons,
							solicitud__socio_id=socio.id,
							solicitud__campaña_id=campaña_id
						)
						.values_list("establecimiento_id", flat=True)
						.distinct()
					)
					establecimientos_qs = establecimientos_qs.filter(id__in=usados)

			# Si la línea ya existe, incluimos su establecimiento aunque no cumpla filtro
			if self.instance and self.instance.pk and self.instance.establecimiento_id:
				establecimientos_qs = establecimientos_qs | Establecimiento.objects.filter(
					pk=self.instance.establecimiento_id
				)

			self.fields['establecimiento'].queryset = establecimientos_qs.distinct()

	def clean(self):
		cd = super().clean()
		if not cd.get('establecimiento'):
			self.add_error('establecimiento', 'Seleccioná el establecimiento.')
		if not cd.get('cultivo'):
			self.add_error('cultivo', 'Seleccioná el cultivo.')
		if (cd.get('hectareas_afectadas') or 0) <= 0:
			self.add_error('hectareas_afectadas', 'Debe ser mayor a 0.')
		return cd

class _LineasDenunciaBaseFormSet(BaseInlineFormSet):
	def clean(self):
		super().clean()
		validas = 0

		for form in self.forms:
			if not hasattr(form, "cleaned_data") or not form.cleaned_data:
				continue
			if self.can_delete and form.cleaned_data.get("DELETE"):
				continue
			validas += 1

		if validas == 0:
			raise forms.ValidationError("Debe cargar al menos una línea de denuncia.")

DenunciaLineaFormSet = inlineformset_factory(
	parent_model=Denuncia,
	model=DenunciaLinea,
	form=DenunciaLineaForm,
	formset=_LineasDenunciaBaseFormSet,
	extra=0,
	can_delete=True,
	min_num=1,
	validate_min=True,
)
