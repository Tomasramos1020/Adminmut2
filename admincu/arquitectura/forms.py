from django import forms
from django.contrib.auth.models import User
from django.forms import Textarea, TextInput, NullBooleanSelect, Select, HiddenInput
from consorcios.models import *
from .models import *
from contabilidad.models import *
from django.db.models import Q
from django_afip.models import PointOfSales
from admincu.forms import FormControl

from django.db.models import Max

from admincu.forms import *
import re


class ingresoForm(FormControl, forms.ModelForm):
	class Meta:
		model = Ingreso
		fields = [
			'nombre', 'prorrateo',
			'prioritario', 'cuenta_contable', 'es_cuota_social'
		]
		labels = {
			'nombre': "Nombre del ingreso",
			'prioritario': "Tiene prioridad de cobro?",
			'prorrateo': "Prorratea por m2?",
			'es_cuota_social': "¿Se calcula para articulo 9?"
		}
		widgets = {
			'prorrateo': NullBooleanSelect(),
			'prioritario': NullBooleanSelect(),
		}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		if not self.consorcio.superficie:
			self.fields.pop('prorrateo')
		self.fields['cuenta_contable'].queryset = Plan.objects.get(consorcio=consorcio).cuentas.filter(
				nivel=4,
				).order_by('numero')
		if self.instance.primario:
			self.fields.pop('cuenta_contable')
		if self.consorcio and self.consorcio.es_federacion == False:
			self.fields['es_cuota_social'].widget = forms.HiddenInput()


	def clean_nombre(self):
		nombre = self.cleaned_data['nombre']
		ingresos_del_club = Ingreso.objects.filter(consorcio=self.consorcio)
		if self.instance:
			ingresos_del_club = ingresos_del_club.exclude(pk=self.instance.pk)
		ingresos = []
		for s in ingresos_del_club:
			ingresos.append(s.nombre)
		if nombre in ingresos:
			raise forms.ValidationError("ya existe un ingreso con el nombre indicado")
		return nombre




class gastoForm(FormControl, forms.ModelForm):
	class Meta:
		model = Gasto
		fields = [
			'nombre', 'cuenta_contable'
		]
		labels = {
			'nombre': "Nombre del tipo de gasto",
		}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['cuenta_contable'].queryset = Plan.objects.get(consorcio=consorcio).cuentas.filter(nivel=4).all().order_by('numero')


class cajaForm(FormControl, forms.ModelForm):
	class Meta:
		model = Caja
		fields = ['nombre', 'entidad', 'saldo', 'fecha', 'cuenta_contable']

		labels = {
			'saldo' : "Saldo trasladable",
			'fecha': "Fecha del saldo",
		}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['cuenta_contable'].queryset = Plan.objects.get(consorcio=consorcio).cuentas.filter(nivel=4).filter(
				Q(numero__range=[111000,113000]) |
				Q(numero__range=[211000,221000])
				).order_by('numero')
		if self.instance.primario:
			self.fields.pop('entidad')
			self.fields.pop('cuenta_contable')


class dominioForm(FormControl, forms.ModelForm):
	class Meta:
		model = Dominio
		fields = [
			'propietario', 'socio',
			'numero', 'identificacion',
			'superficie_total', 'superficie_cubierta',
			'domicilio_calle', 'domicilio_numero',
			'domicilio_piso', 'domicilio_oficina',
			'domicilio_sector', 'domicilio_torre',
			'domicilio_manzana', 'domicilio_parcela',
			'domicilio_catastro', 'padre',
			]

		labels = {
			'domicilio_catastro': "Catastro / Matricula",
			'socio': "Ocupante",
			'identificacion': 'Identificacion (ocupante)',
			'padre': 'Unifica con',
			'domicilio_manzana': 'Domicilio manzana / modulo',
		}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		socios = Socio.objects.filter(consorcio=consorcio)
		self.fields['socio'].queryset = socios
		self.fields['propietario'].queryset = socios
		self.fields['padre'].queryset = Dominio.objects.filter(consorcio=consorcio, padre__isnull=True)
		self.fields['padre'].label_from_instance = self.label_from_instance

	def label_from_instance(self, obj):
		return "{} - {}".format(obj.socio, obj.nombre)

	def clean_superficie_total(self):
		superficie_total = self.cleaned_data['superficie_total']
		ingresos = Ingreso.objects.filter(consorcio=self.consorcio)
		prorrateo_superficie = []
		for ingreso in ingresos:
			if ingreso.prorrateo:
				prorrateo_superficie.append(ingreso)
		if prorrateo_superficie and not superficie_total:
			raise forms.ValidationError("Este campo es obligatorio.")
		return superficie_total


class socioForm(FormControl, forms.ModelForm):
	class Meta:
		model = Socio
		fields = [
			'nombre', 'apellido','numero_asociado','tipo_asociado',
			'fecha_alta',  'tipo_persona',
			'numero_documento','fecha_nacimiento','genero',	
			'es_extranjero', 'provincia','localidad','domicilio', 
			'numero_calle','piso','departamento','codigo_postal',
			'telefono','profesion', 
			'mail',   'notificaciones', 'causa_baja',
			'medida_disciplinaria', 'observacion', 'directivo', 'estado', 'presidente',
			'gerente','secretario','tesorero','cant_socios','activos','adherentes','participantes',
			'honorarios','convenio'
			]
		labels = {
			'nombre': "Nombre (obligatorio)",
			'apellido':"Apellido (obligatorio)",
			'provincia':"Provincia (obligatorio)",
			'localidad':"Localidad (obligatorio)",
			'numero_asociado' : "Numero de asociado (obligatorio)",
			'fecha_nacimiento': "Fecha de nacimiento",
			'genero':"Genero",
			'es_extranjero': 'Es extranjero?',
			'tipo_asociado':'Tipo de asociado (obligatorio)',
			'fecha_alta': 'Fecha de alta (obligatorio)',
			'notificaciones': 'Recibe notificaciones?',
			'tipo_persona': 'Tipo de persona (obligatorio)',
			'numero_documento': 'Cuit/Cuil del asociado (obligatorio)',
			'numero_calle': 'Numero de calle',
			'codigo_postal': 'Codigo postal (obligatorio)',
			'causa_baja': 'Causa de la baja',
			'medida_disciplinaria': 'Medida disciplinaria',
			'domicilio': 'Calle (obligatorio)',
			'directivo': '¿Es Directivo o Junta Fiscalizadora?',
			'estado':'Estado del socio',
			'presidente':'Presidente',
			'gerente':'Gerente',
			'tesorero':'Tesorero',
			'secretario':'Secretario',
			'cant_socios':'Cantidad de Socios',
			'activos':'Activos',
			'adherentes':'Adherentes',
			'participantes':'Participantes',
			'honorarios':'Honorarios',
			'genero':'Genero',
			'convenio':'Convenio'			
		}
		widgets = {
			'notificaciones': NullBooleanSelect(),
			'es_extranjero': NullBooleanSelect(),
			'numero_documento': TextInput(attrs={'type': 'number', 'min': '0', 'step':'1', 'required':True}),
			'numero_asociado': TextInput(attrs={'type': 'number', 'min': '0', 'step':'1', 'required':True}),

		}


	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['numero_asociado'].required = True
		self.fields['tipo_asociado'].queryset = Tipo_asociado.objects.filter(consorcio=consorcio, baja__isnull=True)
		self.fields['fecha_alta'].required = True
		self.fields['tipo_asociado'].required = True
		self.fields['numero_asociado'].required = True
		self.fields['nombre'].required = True
		self.fields['numero_documento'].required = True
		self.fields['tipo_persona'].required = True
		self.fields['codigo_postal'].required = True
		self.fields['provincia'].required = True
		self.fields['localidad'].required = True
		self.fields['domicilio'].required = True
		self.fields['apellido'].required = True
		self.fields['convenio'].queryset = Convenio.objects.filter(consorcio=consorcio, baja__isnull=True)

		if self.consorcio and not self.consorcio.convenios:
			self.fields['convenio'].widget = forms.HiddenInput()

		if self.consorcio and self.consorcio.es_federacion:
			self.fields['apellido'].label = 'Matricula (obligatorio)'
			self.fields['tipo_asociado'].label = 'Tipo (obligatorio)'
			self.fields['profesion'].label = 'Delegados'
			self.fields['es_extranjero'].widget = forms.HiddenInput()
			self.fields['numero_documento'].label = 'Cuit (obligatorio)'
			self.fields['directivo'].widget = forms.HiddenInput()
			self.fields['fecha_nacimiento'].label = 'Fecha de constitucion'
			self.fields['tipo_persona'].widget = forms.HiddenInput()
			self.fields['causa_baja'].label = 'Mails de contacto'
			self.fields['medida_disciplinaria'].label = 'Telefono de contacto'
			self.fields['estado'].label = 'Estado'
			self.fields['genero'].widget = forms.HiddenInput()

		if self.consorcio and self.consorcio.cuit_nasociado:
			self.fields['numero_asociado'].widget = forms.HiddenInput()
			self.fields['numero_asociado'].required = False
			
		if self.consorcio and self.consorcio.es_federacion == False:
			self.fields['presidente'].widget = forms.HiddenInput()
			self.fields['secretario'].widget = forms.HiddenInput()	
			self.fields['gerente'].widget = forms.HiddenInput()	
			self.fields['tesorero'].widget = forms.HiddenInput()	
			self.fields['cant_socios'].widget = forms.HiddenInput()	
			self.fields['activos'].widget = forms.HiddenInput()	
			self.fields['adherentes'].widget = forms.HiddenInput()	
			self.fields['participantes'].widget = forms.HiddenInput()	
			self.fields['honorarios'].widget = forms.HiddenInput()	


	def clean_numero_asociado(self):
		numero_asociado = self.cleaned_data['numero_asociado']
		socios_del_club = Socio.objects.filter(consorcio=self.consorcio)
		if not numero_asociado:
			return numero_asociado
		if self.instance:
			socios_del_club = socios_del_club.exclude(pk=self.instance.pk)
		n_asocs = []
		for s in socios_del_club:
			n_asocs.append(s.numero_asociado)
		if numero_asociado in n_asocs:
			raise forms.ValidationError("ya existe un asociado con el numero indicado")
		return numero_asociado

	def clean_numero_documento(self):
		numero_documento = self.cleaned_data['numero_documento']
		socios_del_club = Socio.objects.filter(consorcio=self.consorcio)
		if self.instance:
			socios_del_club = socios_del_club.exclude(pk=self.instance.pk)
		documentos = []
		for s in socios_del_club:
			documentos.append(s.numero_documento)
		if numero_documento in documentos:
			raise forms.ValidationError("ya existe un asociado con el cuit indicado")
		if not re.match(r'^\d{11}$', numero_documento):
			print(numero_documento)
			raise forms.ValidationError("El CUIT debe tener exactamente 11 dígitos")

		return numero_documento






#	def clean_numero_documento(self):
#		numero_documento = self.cleaned_data['numero_documento']
#		socios_del_club = Socio.objects.filter(consorcio=self.consorcio)
#		if self.instance:
#  			socios_del_club = socios_del_club.exclude(pk=self.instance.pk)
#		documentos = []
#		for s in socios_del_club:
#			documentos.append(s.numero_documento)
#		if numero_documento in documentos:
#			raise forms.ValidationError("ya existe un asociado con el numero de documento indicado")
#		return numero_documento

			

		

class acreedorForm(FormControl, forms.ModelForm):
	class Meta:
		model = Acreedor
		fields = [
			'nombre','tipo', 'tipo_documento',
			'numero_documento', 'direccion','genera',
			'cuenta_contable','condicion_iva',
			]
		labels = {
			'tipo': 'Tipo de Gasto',
			'tipo_documento': 'Tipo de documento',
			'genera': 'Genera retenciones?',
			'numero_documento': 'Numero de documento',
			'direccion': 'Direccion',
			'condicion_iva': 'Condicion ante el IVA',
		}
		widgets = {
			'numero_documento': TextInput(attrs={'type': 'number', 'min': '0', 'step':'1', 'required':True})
		}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['tipo'].queryset = Gasto.objects.filter(consorcio=consorcio)
		self.fields['cuenta_contable'].queryset = Plan.objects.get(consorcio=consorcio).cuentas.filter(nivel=4).filter(
				numero__range=[210000,299999]
				).order_by('numero')
		self.fields['tipo_documento'].required = True
		if self.instance.primario:
			self.fields.pop('nombre')
			self.fields.pop('tipo_documento')
			self.fields.pop('numero_documento')
			self.fields.pop('cuenta_contable')
			self.fields.pop('genera')




class interesForm(FormControl, forms.ModelForm):
	class Meta:
		model = Accesorio
		fields = [
			'nombre', 'ingreso',
			'plazo', 'tipo',
			'reconocimiento',
			'monto', 'base_calculo',
			'cuenta_contable'
		]
		labels = {
			'nombre': "Titulo del interes",
			'plazo': "Plazo en dias",
			'tipo': "Tipo de calculo",
			'monto': "Valor de calculo",
			'base_calculo': "Base de calculo",
		}
		help_texts = {
			"plazo":"Dias desde la fecha de facturacion para que opere el vencimiento y empiece a correr el interes",
		}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['cuenta_contable'].queryset = Plan.objects.get(consorcio=consorcio).cuentas.filter(
				nivel=4,
				numero__gte=400000,
				numero__lt=500000,
				).order_by('numero')
		self.fields['ingreso'].queryset = Ingreso.objects.filter(consorcio=consorcio)
		for field in iter(self.fields):
			self.fields[field].required = True


class descuentoForm(FormControl, forms.ModelForm):
	class Meta:
		model = Accesorio
		fields = [
				'nombre','ingreso',
				'plazo',
				'tipo', 'monto',
				'cuenta_contable'
			]
		labels = {
			'nombre': "Titulo del descuento",
			'plazo': "Plazo en dias",
			'tipo': "Tipo de calculo",
			'monto': "Valor de calculo",
		}
		help_texts = {
			"plazo":"Dias de gracia desde la fecha de facturacion",
		}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['cuenta_contable'].queryset = Plan.objects.get(consorcio=consorcio).cuentas.filter(
				nivel=4,
				numero__gte=400000,
				).order_by('numero')
		self.fields['ingreso'].queryset = Ingreso.objects.filter(consorcio=consorcio)
		for field in iter(self.fields):
			self.fields[field].required = True


class bonificacionForm(FormControl, forms.ModelForm):
	class Meta:
		model = Accesorio
		fields = [
				'nombre','ingreso',
				'tipo', 'monto',
				'cuenta_contable'
			]
		labels = {
			'nombre': "Titulo de la bonificacion",
			'tipo': "Tipo de calculo",
			'monto': "Valor de calculo",
		}


	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['cuenta_contable'].queryset = Plan.objects.get(consorcio=consorcio).cuentas.filter(
				nivel=4,
				numero__gte=400000,
				).order_by('numero')
		self.fields['ingreso'].queryset = Ingreso.objects.filter(consorcio=consorcio)
		for field in iter(self.fields):
			self.fields[field].required = True


class grupoForm(FormControl, forms.ModelForm):
	class Meta:
		model = Tipo_asociado
		fields = ['nombre', 'descripcion', 'cuota_social']
		labels = {'nombre':"Nombre", 'descripcion':"Descripcion", 'cuota_social': "¿Esta categoría de asociados paga cuota social?"}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True
		#self.fields['dominios'].queryset = Dominio.objects.filter(consorcio=consorcio)




class convenioForm(FormControl, forms.ModelForm):
	class Meta:
		model = Convenio
		fields = ['nombre','fecha', 'observaciones', 'reglamento' ]
		labels = {
			'nombre':"Nombre",
			'fecha': "Fecha",
			'observaciones': "Texto",
			'reglamento': "Observaciones",			
		}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)

		self.fields['nombre'].required = True

class servicioForm(FormControl, forms.ModelForm):
	class Meta:
		model = Servicio_mutual
		fields = ['nombre','descripcion', 'nombre_reglamento', 'fecha_reglamento' ]
		labels = {
			'nombre':"Nombre del servicio mutual",
			'descripcion': "Reglamento",
			'nombre_reglamento': "Nombre del reglamento",
			'fecha_reglamento': "fecha de la aprobacion del reglamento",			
		}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)

		self.fields['nombre'].required = True

class clienteForm(FormControl, forms.ModelForm):
	class Meta:
		model = Socio
		fields = [
			'nombre', 'apellido',
			'tipo_documento', 'numero_documento',
			'telefono', 'domicilio',
			'localidad', 'provincia'
			]

		labels = {
			'tipo': 'Tipo de Gasto',
			'tipo_documento': 'Tipo de documento',
			'numero_documento': 'Numero de documento'
		}
		widgets = {
			'numero_documento': TextInput(attrs={'type': 'number', 'min': '0', 'step':'1', 'required':True})
		}


	def __init__(self, consorcio=None, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.fields['tipo_documento'].required = True



class hiddenForm(forms.ModelForm):

	class Meta:
		model = Accesorio
		fields = ['finalizacion']

		widgets = {
			'finalizacion': HiddenInput(),
		}

# IMPORTACION_CHOICES = (
# 	(None, '-- Seleccionar Tipo de Importacion --'),
# 	('parcial', 'importacion parcial')
# )

# class Tipo_ImportacionForm(FormControl, forms.Form):
# 	tipo = forms.ChoiceField(choices=IMPORTACION_CHOICES)


class ImportacionForm(forms.Form):

	""" Importacion de un archivo """

	archivo = ExcelFileField()

class ConfirmacionForm(FormControl, forms.Form):

	""" Confirmacion del comprobante """

	confirmacion = forms.IntegerField(widget=forms.HiddenInput(), required=False)