from django import forms
from datetime import timedelta
from django.contrib.auth.models import User
from django.forms import Textarea, TextInput, NullBooleanSelect, Select
from django_afip.models import *
from django.forms import formset_factory
from django.core.validators import MinValueValidator
import django.utils.timezone as dj_tz
from admincu.forms import *
from consorcios.models import *
from .models import *
from arquitectura.models import Convenio

class CreditoForm(FormControl, forms.ModelForm):
	class Meta:
		model = Credito
		fields = [
			'ingreso',
			'periodo', 'capital',
			'detalle'
		]
		labels = {
			'capital': "Subtotal",
		}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['ingreso'].queryset = Ingreso.objects.filter(consorcio=consorcio)

	def label_from_instance(self, obj):
		return "{} - {}".format(obj.socio, obj.nombre)



class InicialForm(FormControl, forms.Form):
	punto = forms.ModelChoiceField(queryset=PointOfSales.objects.none(), empty_label="-- Seleccionar Punto de gestion --", label="Punto de gestion")
	concepto = forms.ModelChoiceField(queryset=ConceptType.objects.all(), empty_label="-- Seleccionar Tipo de operacion --", label="Tipo de operacion")
	fecha_operacion = forms.DateField(label="Fecha de la operacion", widget=forms.DateInput(attrs={'type': 'date', 'placeholder':'YYYY-MM-DD'}))
	fecha_factura = forms.DateField(label="Fecha de la factura", widget=forms.DateInput(attrs={'type': 'date', 'placeholder':'YYYY-MM-DD'}))
	ingreso = forms.ModelChoiceField(queryset=Ingreso.objects.none(), empty_label="-- Seleccionar Ingreso --", label="Ingresos")
	tipo_asociado = forms.MultipleChoiceField(choices=((None,None),))

	def __init__(self, *args, **kwargs):
		consorcio = kwargs.pop('consorcio')

		# 👉 kwargs opcionales para límites (solo se pasan en wizard de Factura C)
		self.limit_fecha_factura = kwargs.pop('limit_fecha_factura', False)
		self.limit_fecha_operacion = kwargs.pop('limit_fecha_operacion', False)
		self.backdate_limit_days = int(kwargs.pop('backdate_limit_days', 0) or 0)

		try:
			ok_grupos = kwargs.pop('ok_grupos')
		except:
			ok_grupos = False

		try:
			ok_conceptos = kwargs.pop('ok_conceptos')
		except:
			ok_conceptos = False

		try:
			rename_factura = kwargs.pop('rename_factura')
		except:
			rename_factura = False

		super().__init__(*args, **kwargs)

		if ok_grupos:
			gr = Tipo_asociado.objects.filter(consorcio=consorcio, baja__isnull=True)
			GRUPO_CHOICES = ((g.id, g.nombre) for g in gr)
			self.fields['tipo_asociado'].choices = GRUPO_CHOICES
		else:
			self.fields.pop('tipo_asociado')

		self.fields['punto'].queryset = PointOfSales.objects.filter(owner=consorcio.contribuyente)

		if ok_conceptos:
			self.fields.pop('punto')
			self.fields.pop('concepto')
			self.fields.pop('fecha_factura')
			self.fields['ingreso'].queryset = Ingreso.objects.filter(consorcio=consorcio)
		else:
			self.fields.pop('ingreso')

		if rename_factura:
			# si otro wizard renombra/oculta la fecha de factura
			self.fields.pop('fecha_factura', None)

		# 👉 Aplicar min/max HTML en los date inputs cuando corresponde
		today = dj_tz.localtime(dj_tz.now()).date()


		if 'fecha_factura' in self.fields and self.limit_fecha_factura and self.backdate_limit_days > 0:
			min_date = today - timedelta(days=self.backdate_limit_days)
			self.fields['fecha_factura'].widget.attrs.update({
				'type': 'date',
				'min': min_date.isoformat(),
				'max': today.isoformat(),
				'title': f'Permitido entre {min_date.isoformat()} y {today.isoformat()} (máx. {self.backdate_limit_days} días hacia atrás).'
			})

		if 'fecha_operacion' in self.fields and self.limit_fecha_operacion and self.backdate_limit_days > 0:
			min_date = today - timedelta(days=self.backdate_limit_days)
			self.fields['fecha_operacion'].widget.attrs.update({
				'type': 'date',
				'min': min_date.isoformat(),
				'max': today.isoformat(),
				'title': f'Permitido entre {min_date.isoformat()} y {today.isoformat()} (máx. {self.backdate_limit_days} días hacia atrás).'
			})

	# ✅ Validación server-side (robusta)
	def clean_fecha_factura(self):
		fecha = self.cleaned_data.get('fecha_factura')
		if not fecha or not self.limit_fecha_factura or self.backdate_limit_days <= 0:
			return fecha

		today = dj_tz.localtime(dj_tz.now()).date()

		min_date = today - timedelta(days=self.backdate_limit_days)

		if fecha < min_date or fecha > today:
			raise forms.ValidationError(
				f"La fecha de la factura debe estar entre {min_date:%Y-%m-%d} y {today:%Y-%m-%d} (máx. {self.backdate_limit_days} días hacia atrás)."
			)
		return fecha

	def clean(self):
		data = super().clean()
		if self.limit_fecha_operacion and self.backdate_limit_days > 0:
			fecha_op = data.get('fecha_operacion')
			if fecha_op:
				today = dj_tz.localtime(dj_tz.now()).date()
				min_date = today - timedelta(days=self.backdate_limit_days)
				if fecha_op < min_date or fecha_op > today:
					self.add_error(
						'fecha_operacion',
						f"La fecha de operación debe estar entre {min_date:%Y-%m-%d} y {today:%Y-%m-%d} (máx. {self.backdate_limit_days} días hacia atrás)."
					)

		# (opcional) coherencia: fecha_operacion <= fecha_factura
		ff = data.get('fecha_factura')
		fo = data.get('fecha_operacion')
		if ff and fo and fo > ff:
			self.add_error('fecha_operacion', "La fecha de operación no puede ser posterior a la fecha de la factura.")

		return data





#	def clean_fecha_factura(self):

		""" validacion de fecha de factura """

#		data = self.cleaned_data

#		validacion = data['punto'].receipts.filter(issued_date__gt=data['fecha_factura'], receipt_type=ReceiptType.objects.get(code="11"))
#		if validacion:
#			raise forms.ValidationError("El punto de venta seleccionado ha generado facturas con fecha posterior a la indicada.")

#		if date.today() + timedelta(days=10) < data['fecha_factura'] or data['fecha_factura'] < date.today() - timedelta(days=10):
#			raise forms.ValidationError("No puede diferir en mas de 10 dias de la fecha de hoy.")
#		return data['fecha_factura']



class ConceptosForm(FormControl, forms.Form):

	""" Formulario individuales de liquidaciones """

	destinatario = forms.ChoiceField(label="Destinatario")
	subtotal = forms.DecimalField(max_digits=20, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
	detalle = forms.CharField(max_length=30, required=False)

	def __init__(self, consorcio, *args, **kwargs):
		super().__init__(*args, **kwargs)
		choices = [(None, '-- Seleccione Destinatario --')]
		asociados = Socio.objects.filter(consorcio=consorcio, es_socio=True, baja__isnull=True, nombre_servicio_mutual__isnull=True)
		if asociados:
			choices.append((None, '------ Padron de asociados ------'))
			for s in asociados:
				dato = 'socio-{}'.format(s.id)
				choices.append((dato, s.nombre_completo))
		if consorcio.es_federacion:
			clientes = Socio.objects.filter(consorcio=consorcio, es_socio=False, baja__isnull=True, nombre_servicio_mutual__isnull=True)
			if clientes:
				choices.append((None, '------ Padron de NO asociados ------'))
				for c in clientes:
					dato = 'cliente-{}'.format(s.id)
					choices.append((dato, c.nombre_completo))
		self.fields['destinatario'].choices = choices



class IndividualesRecursoForm(FormControl, forms.Form):

	""" Formulario individuales de liquidaciones """

	destinatario = forms.ChoiceField(label="Destinatario")
	ingreso = forms.ModelChoiceField(queryset=Ingreso.objects.none(), empty_label="-- Seleccionar ingreso --", label="Ingreso")
	subtotal = forms.DecimalField(max_digits=20, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
	detalle = forms.CharField(max_length=30, required=False)

	def __init__(self, consorcio, *args, **kwargs):
		super().__init__(*args, **kwargs)
		choices = [(None, '-- Seleccione Destinatario --')]
		socios_servicios = Socio.objects.filter(consorcio=consorcio, es_socio=True, baja__isnull=True, nombre_servicio_mutual__isnull=False)
		if socios_servicios:
			choices.append((None, '------ Grupos de asociados globales por servicios mutuales------'))
			for socio in socios_servicios:
				dato = 'socio-{}'.format(socio.id)
				choices.append((dato, socio.nombre))

		asociados = Socio.objects.filter(consorcio=consorcio, es_socio=True, baja__isnull=True, nombre_servicio_mutual__isnull=True)
		if asociados:
			choices.append((None, '------ Padron de asociados ------'))
			for s in asociados:
				dato = 'socio-{}'.format(s.id)
				choices.append((dato, s.nombre_completo))
		if consorcio.es_federacion:
			clientes = Socio.objects.filter(consorcio=consorcio, es_socio=False, baja_isnull=True)
			if clientes:
				choices.append((None, '------ Padron de NO asociados ------'))
				for cliente in clientes:
					dato = 'socio-{}'.format(cliente.id)
					choices.append((dato, cliente.nombre_completo))
		self.fields['destinatario'].choices = choices
		self.fields['ingreso'].queryset = Ingreso.objects.filter(consorcio=consorcio)

class IndividualesForm(FormControl, forms.Form):

	""" Formulario individuales de liquidaciones """

	destinatario = forms.ChoiceField(label="Destinatario")
	ingreso = forms.ModelChoiceField(queryset=Ingreso.objects.none(), empty_label="-- Seleccionar ingreso --", label="Ingreso")
	subtotal = forms.DecimalField(max_digits=20, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
	detalle = forms.CharField(max_length=30, required=False)

	def __init__(self, consorcio, *args, **kwargs):
		super().__init__(*args, **kwargs)
		choices = [(None, '-- Seleccione Destinatario --')]
		asociados = Socio.objects.filter(consorcio=consorcio, es_socio=True, baja__isnull=True, nombre_servicio_mutual__isnull=True)
		if asociados:
			choices.append((None, '------ Padron de asociados ------'))
			for s in asociados:
				dato = 'socio-{}'.format(s.id)
				choices.append((dato, s.nombre_completo))
		if consorcio.es_federacion:
			clientes = Socio.objects.filter(consorcio=consorcio, es_socio=False, baja__isnull=True)
			if clientes:
				choices.append((None, '------ Padron de NO asociados ------'))
				for cliente in clientes:
					dato = 'socio-{}'.format(cliente.id)
					choices.append((dato, cliente.nombre_completo))
		
		self.fields['destinatario'].choices = choices
		self.fields['ingreso'].queryset = Ingreso.objects.filter(consorcio=consorcio)




class PlazoForm(FormControl, forms.Form):

	""" Paso de indicacion de los plazos """

	accesorio = forms.IntegerField()
	plazo = forms.DateField()


PlazoFormSet = formset_factory(
		form=PlazoForm,
		extra=10
	)

DISTRIBUCION_CHOICES = (
	(None, '-- Seleccionar Distribucion --'),
	('socio', 'Por socio'),
	('total_socio', 'Total distribuible por socio')
)

class MasivoForm(FormControl, forms.Form):

	""" Formulario masivo de liquidaciones """

	ingreso = forms.ModelChoiceField(queryset=Ingreso.objects.none(), empty_label="-- Seleccionar ingreso --", label="Ingreso")
	distribucion = forms.ChoiceField(choices=DISTRIBUCION_CHOICES)
	subtotal = forms.DecimalField(max_digits=20, decimal_places=2, required=False, validators=[MinValueValidator(Decimal('0.01'))])


	def __init__(self, consorcio, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.fields['ingreso'].queryset = Ingreso.objects.filter(consorcio=consorcio, es_cuota_social=False)


MasivoFormSet = formset_factory(
		form=MasivoForm,
		extra=1,
	)


class PreConceptoForm(FormControl, forms.Form):

	""" Formulario de carga de conceptos en masivo """

	conceptos = forms.MultipleChoiceField(choices=((None,None),), required=False)

	def __init__(self, *args, **kwargs):
		consorcio = kwargs.pop('consorcio')
		super().__init__(*args, **kwargs)
		conceptos = Credito.objects.filter(consorcio=consorcio, liquidacion__isnull=True)
		CONCEPTO_CHOICES = []
		for c in conceptos:
			periodo = "{}-{}".format(c.periodo.year, c.periodo.month)
			nombre = "{}. {} al asociado: {} por ${}".format(
				c.ingreso,
				periodo,
				c.socio,
				c.capital
			)
			CONCEPTO_CHOICES.append((c.id, nombre))
		self.fields['conceptos'].choices = CONCEPTO_CHOICES

class ConfirmacionForm(FormControl, forms.Form):

	""" Confirmacion de liquidacion """

	confirmacion = forms.BooleanField(required=False)

	def __init__(self, *args, **kwargs):
		try:
			mostrar = kwargs.pop('mostrar')
		except:
			mostrar = False
		super().__init__(*args, **kwargs)

		if not mostrar:
			self.fields['confirmacion'].widget = forms.HiddenInput()
		else:
			self.fields['confirmacion'].label = "Seleccione si desea cobrar de contado"

class ImportacionForm(forms.Form):

	""" Importacion de un archivo """

	archivo = ExcelFileField()

class CuotaSocialForm(FormControl, forms.Form):

	""" Formulario individuales de liquidaciones """
	categorias_asociado = forms.ModelChoiceField(queryset=Tipo_asociado.objects.none(), empty_label="-- Seleccionar categoria --", label="Categoria")
	subtotal = forms.DecimalField(max_digits=20, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
	detalle = forms.CharField(max_length=30, required=False)


	def __init__(self, consorcio, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.fields['categorias_asociado'].queryset = Tipo_asociado.objects.filter(consorcio=consorcio, cuota_social=True)

class CuotaConvenioForm(FormControl, forms.Form):
	"""Formulario individuales de liquidaciones por convenio"""
	convenios = forms.ModelChoiceField(queryset=Convenio.objects.none(), empty_label="-- Seleccionar convenio --", label="Convenio")
	subtotal = forms.DecimalField(max_digits=20, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
	detalle = forms.CharField(max_length=30, required=False)


	def __init__(self, consorcio, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.fields['convenios'].queryset = Convenio.objects.filter(consorcio=consorcio)



from django.forms import inlineformset_factory


class FacturaUSDForm(forms.ModelForm):
	class Meta:
		model = FacturaUSD
		# ¡SACAMOS consorcio del form!
		fields = ['fecha', 'socio', 'cotizacion', 'punto']
		widgets = {
			'fecha': forms.DateInput(attrs={'type': 'date'}),
		}

	def __init__(self, *args, **kwargs):
		# el consorcio viene desde la view
		self.consorcio = kwargs.pop('consorcio')
		super().__init__(*args, **kwargs)

		# filtrar punto y socio por consorcio
		self.fields['punto'].queryset = PuntoUSD.objects.filter(consorcio=self.consorcio)
		self.fields['socio'].queryset = Socio.objects.filter(
			consorcio=self.consorcio,
			baja__isnull=True
		)

	def clean_socio(self):
		socio = self.cleaned_data.get('socio')
		if socio and socio.consorcio_id != self.consorcio.id:
			raise forms.ValidationError("El socio no pertenece al consorcio activo.")
		return socio


class CreditoUSDForm(forms.ModelForm):
	class Meta:
		model = CreditoUSD
		# el consorcio y cotización se setean desde la view/factura
		fields = ['ingreso', 'periodo', 'capital_usd', 'detalle']
		widgets = {
			'periodo': forms.DateInput(attrs={'type': 'date'}),
		}

	def __init__(self, *args, **kwargs):
		self.consorcio = kwargs.pop('consorcio')
		super().__init__(*args, **kwargs)
		# filtrar ingresos por consorcio
		self.fields['ingreso'].queryset = Ingreso.objects.filter(consorcio=self.consorcio)


CreditoUSDFormSet = inlineformset_factory(
	parent_model=FacturaUSD,
	model=CreditoUSD,
	form=CreditoUSDForm,
	fields=['ingreso', 'periodo', 'capital_usd', 'detalle'],
	extra=1,
	can_delete=True,
)
