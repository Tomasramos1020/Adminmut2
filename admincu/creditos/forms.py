from django import forms
from datetime import timedelta
from django.contrib.auth.models import User
from django.forms import Textarea, TextInput, NullBooleanSelect, Select
from django_afip.models import *
from django.forms import formset_factory
from django.core.validators import MinValueValidator

from admincu.forms import *
from consorcios.models import *
from .models import *


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

	""" Formulario inicial de liquidaciones """

	punto = forms.ModelChoiceField(queryset=PointOfSales.objects.none(), empty_label="-- Seleccionar Punto de gestion --", label="Punto de gestion")
	concepto = forms.ModelChoiceField(queryset=ConceptType.objects.all(), empty_label="-- Seleccionar Tipo de operacion --", label="Tipo de operacion")
	fecha_operacion = forms.DateField(label="Fecha de la operacion", widget=forms.TextInput(attrs={'placeholder':'YYYY-MM-DD'}))
	fecha_factura = forms.DateField(label="Fecha de la factura", widget=forms.TextInput(attrs={'placeholder':'YYYY-MM-DD'}))
	ingreso = forms.ModelChoiceField(queryset=Ingreso.objects.none(), empty_label="-- Seleccionar Ingreso --", label="Ingresos")
	tipo_asociado = forms.MultipleChoiceField(choices=((None,None),))

	def __init__(self, *args, **kwargs):
		consorcio = kwargs.pop('consorcio')

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
			self.fields.pop('fecha_factura')




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




