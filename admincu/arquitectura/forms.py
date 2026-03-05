from django import forms
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.forms import Textarea, TextInput, NullBooleanSelect, Select, HiddenInput
from consorcios.models import *
from .models import *
from contabilidad.models import *
from django.db.models import Q
from django_afip.models import PointOfSales
from admincu.forms import FormControl

from django.db.models import Max

from admincu.forms import *
import os
import re
import subprocess
import tempfile


class ingresoForm(FormControl, forms.ModelForm):
	class Meta:
		model = Ingreso
		fields = [
			'nombre', 'prorrateo',
			'prioritario', 'cuenta_contable', 'es_cuenta_tercero', 'acreedor_tercero', 'es_cuota_social', "cuenta_activo"
		]
		labels = {
			'nombre': "Nombre del ingreso",
			'prioritario': "Tiene prioridad de cobro?",
			'prorrateo': "Prorratea por m2?",
			'es_cuenta_tercero': "¿Es por cuenta y obra de tercero?",
			'acreedor_tercero': "Proveedor / acreedor tercero",
			'es_cuota_social': "¿Se calcula para articulo 9?",
			"cuenta_activo": "Cuenta de activo (a cobrar)",
			"cuenta_contable": "Cuenta de resultado (haber)"
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

		cuentas = Plan.objects.get(consorcio=consorcio).cuentas.filter(
				nivel=4,
				).order_by('numero')
		self.fields['cuenta_contable'].queryset = cuentas
		self.fields['cuenta_activo'].queryset = cuentas
		self.fields['acreedor_tercero'].queryset = Acreedor.objects.filter(consorcio=consorcio).order_by('nombre')
		if self.instance and self.instance.es_cuenta_tercero and self.instance.acreedor_tercero:
			self.initial['cuenta_contable'] = self.instance.acreedor_tercero.cuenta_contable

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

		def clean(self):
			data = super().clean()
			es_cuenta_tercero = data.get('es_cuenta_tercero')
			acreedor_tercero = data.get('acreedor_tercero')
			cuenta_activo = data.get('cuenta_activo')

		if es_cuenta_tercero:
			if not acreedor_tercero:
				self.add_error('acreedor_tercero', "Debe seleccionar un proveedor para recursos por cuenta y obra de terceros.")
			if not cuenta_activo:
				self.add_error('cuenta_activo', "Debe seleccionar la cuenta a cobrar para recursos por cuenta y obra de terceros.")
			if acreedor_tercero:
				data['cuenta_contable'] = acreedor_tercero.cuenta_contable
		else:
			data['acreedor_tercero'] = None

		return data




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
		fields = ['nombre', 'entidad', 'saldo', 'fecha', 'cuenta_contable','convenio']

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

		if 'convenio' in self.fields:
			del self.fields['convenio']

		if (consorcio and consorcio.convenios) or (self.instance.pk and self.instance.convenio):
			self.fields['convenio'] = forms.BooleanField(
				required=False,
				label='Convenio'
		 )


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
			# ✅ Primero identificación
			'numero_documento',
			'tipo_persona',
			'condicionIVA',

			# ✅ Identidad
			'nombre',
			'apellido',

			# ✅ Datos asociativos
			'numero_asociado',
			'tipo_asociado',
			'fecha_alta',

			# ✅ Personales
			'fecha_nacimiento',
			'genero',
			'es_extranjero',

			# ✅ Domicilio
			'provincia',
			'localidad',
			'domicilio',
			'numero_calle',
			'piso',
			'departamento',
			'codigo_postal',

			# ✅ Contacto / actividades
			'telefono',
			'profesion',
			'mail',

			# ✅ Administración
			'notificaciones',
			'causa_baja',
			'medida_disciplinaria',
			'observacion',
			'directivo',
			'estado',

			# ✅ Federación
			'presidente',
			'gerente',
			'secretario',
			'tesorero',
			'cant_socios',
			'activos',
			'adherentes',
			'participantes',
			'honorarios',

			# ✅ Fiscal
			'convenio',
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
			'convenio':'Convenio',
			'condicionIVA':'Condicion frente al IVA',
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
		# ✅ Si el POST indica persona jurídica, apellido no es obligatorio
		if self.data.get('tipo_persona') == 'juridica':
			self.fields['apellido'].required = False

		self.fields['convenio'].queryset = Convenio.objects.filter(consorcio=consorcio, baja__isnull=True)

		if self.consorcio and not self.consorcio.convenios:
			self.fields['convenio'].widget = forms.HiddenInput()

		if self.consorcio and self.consorcio.es_federacion and self.consorcio.convenios:
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
			self.fields['convenio'].label = 'Servicios AE'

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
		
		if self.consorcio and self.consorcio.es_ri:

			self.fields['nombre'].label = 'Razón social / Nombre (obligatorio)'
			self.fields['numero_documento'].label = 'CUIT (obligatorio)'
			self.fields['condicionIVA'].label = 'Condicion frente al IVA (obligatorio)'
			self.fields['fecha_nacimiento'].widget = forms.HiddenInput()
			self.fields['genero'].widget = forms.HiddenInput()
			self.fields['notificaciones'].widget = forms.HiddenInput()
			self.fields['causa_baja'].widget = forms.HiddenInput()
			self.fields['medida_disciplinaria'].widget = forms.HiddenInput()
			self.fields['observacion'].widget = forms.HiddenInput()
			self.fields['estado'].widget = forms.HiddenInput()
			self.fields['directivo'].widget = forms.HiddenInput()
			self.fields['tipo_asociado'].widget = forms.HiddenInput()
			self.fields['tipo_asociado'].required = False
			self.fields['numero_asociado'].widget = forms.HiddenInput()
			self.fields['numero_asociado'].required = False
			self.fields['condicionIVA'].required = True
			self.fields['profesion'].label = 'Actividad'
			self.fields['fecha_alta'].required = False
			self.fields['fecha_alta'].widget = forms.HiddenInput()

			# ✅ SOLO definimos obligatorios
			obligatorios = [
				'nombre',
				'numero_documento',
				'domicilio',
				'localidad',
				'provincia',
				'codigo_postal',
			]

			for campo in obligatorios:
				if campo in self.fields:
					self.fields[campo].required = True




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

	def clean(self):
		cleaned = super().clean()
		if self.consorcio and self.consorcio.es_federacion == False:
			# Blindaje backend: persona jurídica no requiere apellido
			if cleaned.get("tipo_persona") == "juridica":
				cleaned["apellido"] = ""

		return cleaned


	def save(self, commit=True):

		socio = super().save(commit=False)

		if self.consorcio and self.consorcio.es_ri:
			socio.apellido = socio.apellido or ''
			socio.genero = None
			socio.fecha_nacimiento = None
			socio.tipo_asociado = None
			socio.directivo = None
			socio.estado = 'vigente'
			socio.notificaciones = False
			socio.fecha_alta = date.today()

		if not socio.numero_asociado:
			socio.numero_asociado = socio.cuit or socio.numero_documento or "SIN_NUMERO"

		socio.tipo_documento = DocumentType.objects.get(id=1)

		if commit:
			socio.save()

		return socio


class SocioAdjuntoForm(FormControl, forms.ModelForm):
	EXTENSIONES_PERMITIDAS = {'pdf', 'png', 'jpg', 'jpeg'}
	TAMANO_MAXIMO_FINAL = 400 * 1024  # 400KB
	TAMANO_MAXIMO_SUBIDA_PDF = 2 * 1024 * 1024  # 2MB

	class Meta:
		model = SocioAdjunto
		fields = ['nombre', 'archivo']
		labels = {
			'nombre': 'Descripcion (opcional)',
			'archivo': 'Archivo',
		}

	def __init__(self, socio=None, *args, **kwargs):
		self.socio = socio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = False
		self.fields['archivo'].required = True
		self.fields['archivo'].help_text = (
			"PDF/JPG/PNG. Tamaño final máximo por archivo: 400KB. "
			"Si el PDF supera ese peso, se intentará comprimir automáticamente."
		)

	def clean_archivo(self):
		archivo = self.cleaned_data.get('archivo')
		if not archivo:
			return archivo

		nombre = archivo.name or ''
		extension = nombre.rsplit('.', 1)[-1].lower() if '.' in nombre else ''
		if extension not in self.EXTENSIONES_PERMITIDAS:
			raise forms.ValidationError("Solo se permiten archivos PDF o imagen (JPG/PNG).")

		if extension == 'pdf':
			if archivo.size > self.TAMANO_MAXIMO_SUBIDA_PDF:
				raise forms.ValidationError(
					"El PDF supera 2MB. Subilo con menor peso para poder procesarlo."
				)
			if archivo.size > self.TAMANO_MAXIMO_FINAL:
				return self._comprimir_pdf_hasta_limite(archivo)
			return archivo

		if archivo.size > self.TAMANO_MAXIMO_FINAL:
			raise forms.ValidationError(
				"La imagen supera el tamaño máximo permitido de 400KB."
			)

		return archivo

	def _comprimir_pdf_hasta_limite(self, archivo):
		nombre_original = os.path.basename(archivo.name or "archivo.pdf")
		nombre_comprimido = self._nombre_pdf_comprimido(nombre_original)

		try:
			contenido_original = archivo.read()
			archivo.seek(0)
		except Exception:
			raise forms.ValidationError("No se pudo leer el PDF cargado.")

		if len(contenido_original) <= self.TAMANO_MAXIMO_FINAL:
			return ContentFile(contenido_original, name=nombre_original)

		estrategias = [
			('/ebook', 150),
			('/ebook', 120),
			('/screen', 96),
			('/screen', 72),
		]
		mejor_resultado = None

		try:
			with tempfile.TemporaryDirectory(prefix='socio_adj_pdf_') as tmpdir:
				entrada = os.path.join(tmpdir, "entrada.pdf")
				with open(entrada, "wb") as f:
					f.write(contenido_original)

				for i, (perfil, resolucion) in enumerate(estrategias):
					salida = os.path.join(tmpdir, "salida_{}.pdf".format(i))
					comando = [
						"gs",
						"-sDEVICE=pdfwrite",
						"-dCompatibilityLevel=1.4",
						"-dNOPAUSE",
						"-dQUIET",
						"-dBATCH",
						"-dSAFER",
						"-dDetectDuplicateImages=true",
						"-dCompressFonts=true",
						"-dSubsetFonts=true",
						"-dDownsampleColorImages=true",
						"-dDownsampleGrayImages=true",
						"-dDownsampleMonoImages=true",
						"-dColorImageResolution={}".format(resolucion),
						"-dGrayImageResolution={}".format(resolucion),
						"-dMonoImageResolution={}".format(max(150, resolucion)),
						"-dPDFSETTINGS={}".format(perfil),
						"-sOutputFile={}".format(salida),
						entrada,
					]
					try:
						resultado = subprocess.run(
							comando,
							check=False,
							stdout=subprocess.PIPE,
							stderr=subprocess.PIPE,
							timeout=45,
						)
					except FileNotFoundError:
						raise forms.ValidationError(
							"No hay motor de compresión PDF disponible en el servidor."
						)
					except subprocess.TimeoutExpired:
						continue

					if resultado.returncode != 0 or not os.path.exists(salida):
						continue

					with open(salida, "rb") as fs:
						contenido_salida = fs.read()

					if not contenido_salida:
						continue

					if not mejor_resultado or len(contenido_salida) < len(mejor_resultado):
						mejor_resultado = contenido_salida

					if len(contenido_salida) <= self.TAMANO_MAXIMO_FINAL:
						return ContentFile(contenido_salida, name=nombre_comprimido)
		except forms.ValidationError:
			raise
		except Exception:
			raise forms.ValidationError(
				"No se pudo procesar el PDF. Intentá nuevamente o subí una versión más liviana."
			)

		if mejor_resultado and len(mejor_resultado) < len(contenido_original):
			tam_kb = int(round(len(mejor_resultado) / 1024.0))
			raise forms.ValidationError(
				"No se pudo comprimir el PDF por debajo de 400KB (quedó en {}KB).".format(tam_kb)
			)

		raise forms.ValidationError(
			"No se pudo comprimir el PDF por debajo de 400KB. Probá con menor resolución de escaneo."
		)

	def _nombre_pdf_comprimido(self, nombre):
		base, _ = os.path.splitext(nombre)
		base = base or "archivo"
		return "{}_comprimido.pdf".format(base[:80])

	def clean(self):
		cleaned_data = super().clean()
		if not self.socio:
			raise forms.ValidationError("No se pudo identificar el socio para el adjunto.")

		cons = self.socio.consorcio
		if not cons.habilita_adjuntos_socios:
			raise forms.ValidationError("La carga de adjuntos no esta habilitada para esta mutual.")

		limite = cons.max_adjuntos_por_socio
		actuales = SocioAdjunto.objects.filter(socio=self.socio)
		if self.instance and self.instance.pk:
			actuales = actuales.exclude(pk=self.instance.pk)
		actuales = actuales.count()
		if actuales >= limite:
			raise forms.ValidationError(
				"Este socio ya alcanzo el limite de {} adjuntos.".format(limite)
			)

		return cleaned_data

	def save(self, commit=True):
		objeto = super().save(commit=False)
		objeto.socio = self.socio
		if commit:
			objeto.save()
		return objeto


	





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
			'fecha_reglamento': "Fecha de la aprobacion del reglamento",			
		}
		widgets = {
			'fecha_reglamento': forms.DateInput(attrs={'type':'date'}),
			'descripcion': forms.Textarea(attrs={'rows': 10}),
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

class ZonasPorCultivoForm(FormControl, forms.ModelForm):
	class Meta:
		model = ZonasPorCultivo
		fields = [
			'zona',
			'cultivo',
			'aporte_sin_siniestro',
			'aporte_con_siniestro',
			'franquicia',
			'subsidio_maximo'
			]
		labels = {'zona':"Zona",
			'cultivo':'Cultivo',
			'aporte_sin_siniestro':'% Aporte sin siniestro',
			'aporte_con_siniestro':'% Aporte con siniestro',
			'franquicia':'Franquicia',
			'subsidio_maximo':'Subsidio máximo'
		}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['zona'].queryset = Zona.objects.filter(consorcio=consorcio)
		self.fields['cultivo'].queryset = Cultivo.objects.filter(consorcio=consorcio)
		self.fields['zona'].required = True
		self.fields['cultivo'].required = True


class CotizacionForm(FormControl, forms.ModelForm):
	class Meta:
		model = Cotizacion
		fields = [
			'fecha',
			'producto',
			'cotizacion',
			'precio_flete',
			'comision'
		]
		labels = {
			'fecha':"Fecha",
			'producto':'Producto',
			'cotizacion':'Cotizacion',
			'precio_flete':'Precio del flete',
			'comision':'Comision'
			}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio

		super().__init__(*args, **kwargs)
		self.fields['fecha'].required = True
		self.fields['producto'].queryset = Cultivo.objects.filter(consorcio=consorcio)

class EstablecimientoForm(FormControl, forms.ModelForm):
	socio_1 = forms.ModelChoiceField(queryset=Socio.objects.none(), required=False, label="Dueño 1")
	socio_2 = forms.ModelChoiceField(queryset=Socio.objects.none(), required=False, label="Dueño 2")
	socio_3 = forms.ModelChoiceField(queryset=Socio.objects.none(), required=False, label="Dueño 3")
	socio_4 = forms.ModelChoiceField(queryset=Socio.objects.none(), required=False, label="Dueño 4")
	socio_5 = forms.ModelChoiceField(queryset=Socio.objects.none(), required=False, label="Dueño 5")

	class Meta:
		model = Establecimiento
		fields = [
			'nombre',
			'dpto',
			'gps',
			'zona'
			]
		labels = {
			'nombre':'Nombre',
			'dpto':'Departamento',
			'gps':'GPS',
			'zona':'Zona'
			}

	def __init__(self, consorcio=None, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.consorcio = consorcio
		if consorcio:
			if 'zona' in self.fields:
				self.fields['zona'].queryset = Zona.objects.filter(consorcio=consorcio)
			socios_qs = Socio.objects.filter(consorcio=consorcio)
			for i in range(1, 6):
				self.fields[f'socio_{i}'].queryset = socios_qs
		if self.instance and self.instance.pk:
			socios = list(self.instance.socio.all())
			for i in range(min(5, len(socios))):
				self.initial[f'socio_{i+1}'] = socios[i]
	def save(self, commit=True):
		instance = super().save(commit=False)
		if commit:
			instance.save()
		socios = []
		for i in range(1, 6):
			socio = self.cleaned_data.get(f'socio_{i}')
			if socio:
				socios.append(socio)
		if commit:
			instance.socio.set(socios)
		else:
			self._pending_socios = socios
		return instance
	def save_m2m(self):
		if hasattr(self, '_pending_socios'):
			self.instance.socio.set(self._pending_socios)


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
