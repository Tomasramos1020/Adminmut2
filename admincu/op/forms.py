from django import forms
from django.forms import Textarea, TextInput, NullBooleanSelect, Select
from arquitectura.models import *
from .models import *
from django_afip.models import *
from django.utils.timezone import now
from django.forms import formset_factory, BaseFormSet
from proveeduria.models import Producto, Deposito
from admincu.funciones import consorcio




class encabezadoForm(forms.ModelForm):
	class Meta:
		model = OP
		fields = [
			'punto', 'acreedor', 'fecha_operacion'
		]
		labels = {
			'punto': 'Punto de gestion',
			'fecha_operacion': 'Fecha de la operacion',
		}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super(encabezadoForm, self).__init__(*args, **kwargs)
		clase = 'form-control'
		for field in iter(self.fields):
			if field == 'fecha_operacion':
				clase += ' datepicker'
			self.fields[field].widget.attrs.update({
						'class': clase,
				})
		self.fields['punto'].queryset = PointOfSales.objects.filter(owner=consorcio.contribuyente)
		self.fields['acreedor'].queryset = Acreedor.objects.filter(consorcio=consorcio)


class PagoParcialForm(forms.ModelForm):
	class Meta:
		model = OP
		fields = [
			'punto', 'total',
		]
		labels = {
			'punto': 'Punto de gestion',
		}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super(PagoParcialForm, self).__init__(*args, **kwargs)
		for field in iter(self.fields):
			self.fields[field].widget.attrs.update({
						'class': 'form-control',
				})
		self.fields['punto'].queryset = PointOfSales.objects.filter(owner=consorcio.contribuyente)


class cajaForm(forms.ModelForm):
	class Meta:
		model = CajaOP
		fields = ['caja','referencia','valor']

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super(cajaForm, self).__init__(*args, **kwargs)
		for field in iter(self.fields):
			self.fields[field].widget.attrs.update({
						'class': 'form-control',
				})
		self.fields['caja'].queryset = Caja.objects.filter(consorcio=self.consorcio)



class encabezadoDeudaForm(forms.ModelForm):
	class Meta:
		model = Deuda
		fields = [
			'acreedor', 'fecha', 'numero',
		]
		labels = {
			'fecha': 'Fecha del comprobante',
			'numero': 'Numero del comprobante',
		}
		widgets = {
			'fecha': TextInput(attrs={
					'id': 'datepicker-autoclose',
					'placeholder': 'AAAA-MM-DD',
					}),
		}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super(encabezadoDeudaForm, self).__init__(*args, **kwargs)
		for field in iter(self.fields):
			self.fields[field].widget.attrs.update({
						'class': 'form-control',
				})
		self.fields['acreedor'].queryset = Acreedor.objects.filter(consorcio=consorcio).order_by('nombre')

	def clean_numero(self):
		numero = self.cleaned_data['numero']
		if not numero:
			raise forms.ValidationError("Este campo es obligatorio.")
		return numero


class detallesDeudaForm(forms.ModelForm):
	class Meta:
		model = Deuda
		fields = [
			'observacion'
		]
		widgets = {
			'observacion': Textarea(attrs={'rows': 8}),
		}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super(detallesDeudaForm, self).__init__(*args, **kwargs)
		for field in iter(self.fields):
			self.fields[field].widget.attrs.update({
						'class': 'form-control',
				})


CSS_INPUT = {'class': 'form-control'}
CSS_SELECT = {'class': 'form-control select2'}
CSS_TEXTAREA = {'class': 'form-control', 'rows': 2}

class NCProveedorInicialForm(forms.Form):
	acreedor = forms.ModelChoiceField(
		queryset=Acreedor.objects.none(),
		label="Proveedor",
		widget=forms.Select(attrs={**CSS_SELECT, 'data-placeholder': 'Elegí un proveedor…'})
	)
	deuda = forms.ModelChoiceField(
		queryset=Deuda.objects.none(),
		required=True,
		label="Deuda a ajustar",
		widget=forms.Select(attrs={**CSS_SELECT, 'data-placeholder': 'Elegí una deuda…'})
	)
	fecha = forms.DateField(
		widget=forms.DateInput(attrs={**CSS_INPUT, 'type': 'date'}),
		label="Fecha"
	)

	observacion = forms.CharField(
		required=False,
		widget=forms.Textarea(attrs=CSS_TEXTAREA),
		label="Observación"
	)
	deposito = forms.ModelChoiceField(
		queryset=Deposito.objects.none(),
		required=False,
		label="Depósito (solo Proveeduría)",
		widget=forms.Select(attrs=CSS_SELECT)
	)
	importe_nc = forms.DecimalField(
		required=False,
		min_value=Decimal('0.01'),
		decimal_places=2,
		max_digits=12,
		label="Importe de la NC (no Proveeduría)",
		widget=forms.NumberInput(attrs={**CSS_INPUT, 'step': '0.01'})
	)

	def __init__(self, *args, **kwargs):
		self.request = kwargs.pop('request', None)
		super().__init__(*args, **kwargs)
		c = consorcio(self.request)

		self.fields['acreedor'].queryset = Acreedor.objects.filter(consorcio=c).order_by('nombre')
		self.fields['deposito'].queryset = Deposito.objects.filter(consorcio=c).order_by('nombre')

		acreedor_id = self.data.get(self.add_prefix('acreedor')) if self.is_bound else None
		if acreedor_id:
			self.fields['deuda'].queryset = (
				Deuda.objects
				.filter(consorcio=c, acreedor_id=acreedor_id, confirmado=True, pagado=False, anulado__isnull=True)
				.order_by('-fecha', '-id')
			)
		else:
			self.fields['deuda'].queryset = Deuda.objects.none()

	# opcional
	def acreedor_tiene_proveeduria(self):
		a: Acreedor = self.cleaned_data.get('acreedor')
		return bool(getattr(a, 'es_proveeduria', False))


class NCProductoForm(forms.Form):
	producto = forms.ModelChoiceField(
		queryset=Producto.objects.none(),
		widget=forms.Select(attrs=CSS_SELECT),
		label="Producto"
	)
	cantidad = forms.DecimalField(
		min_value=Decimal('0.01'),
		decimal_places=2, max_digits=12,
		widget=forms.NumberInput(attrs={**CSS_INPUT, 'step': '0.01', 'placeholder': 'Cantidad > 0'}),
		label="Cantidad"
	)
	precio = forms.DecimalField(
		min_value=Decimal('0.00'),
		decimal_places=2, max_digits=12,
		widget=forms.NumberInput(attrs={**CSS_INPUT, 'step': '0.01', 'placeholder': 'Precio >= 0'}),
		label="Precio"
	)

	def __init__(self, *args, **kwargs):
		req = kwargs.pop('request', None)
		deuda = kwargs.pop('deuda', None)      # <— NUEVO
		super().__init__(*args, **kwargs)
		c = consorcio(req)

		qs = Producto.objects.filter(consorcio=c).order_by('nombre')
		if deuda:
			from .views_deud import disponibles_por_producto_en_deuda
			mapa = disponibles_por_producto_en_deuda(deuda)
			ids_disponibles = [pid for pid, q in mapa.items() if q > 0]
			qs = qs.filter(pk__in=ids_disponibles)

		self.fields['producto'].queryset = qs


class BaseNCProductoFS(BaseFormSet):
	def clean(self):
		super().clean()
		filas_validas = 0
		total_nc = Decimal('0.00')
		for form in self.forms:
			cd = getattr(form, 'cleaned_data', None) or {}
			if cd and not cd.get('DELETE'):
				filas_validas += 1
				cantidad = cd.get('cantidad') or Decimal('0.00')
				precio = cd.get('precio') or Decimal('0.00')
				total_nc += (cantidad * precio)
		if filas_validas == 0:
			raise forms.ValidationError("Debés cargar al menos una línea de producto.")
		if total_nc <= 0:
			raise forms.ValidationError("El total de la NC por productos debe ser mayor a 0.")

NCProductoFS = formset_factory(NCProductoForm, formset=BaseNCProductoFS, extra=1, can_delete=True)

