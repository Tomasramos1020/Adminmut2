from django import forms
from admincu.forms import FormControl
from .models import *
from django.forms import modelformset_factory
from admincu.funciones import consorcio
from django.forms.widgets import DateInput
from django_afip.models import PointOfSales
from arquitectura.models import Acreedor



class sucursalForm(FormControl, forms.ModelForm):
	class Meta:
		model = Sucursal
		fields = ['nombre', 'direccion', 'localidad', 'provincia', 'mail', 'socio', 'lista_precio']
		labels = {'nombre':"Nombre", 
		'direccion':'Direccion', 
		'localidad':'Localidad', 
		'provincia':'Provincia', 
		'mail':'Mail', 
		'socio':'Socio', 
		'lista_precio':'Lista de Precio'
		}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['direccion'].required = True
		self.fields['socio'].queryset = Socio.objects.filter(consorcio=consorcio, baja__isnull=True)
		self.fields['socio'].required = True


class productoForm(FormControl, forms.ModelForm):
	class Meta:
		model = Producto
		fields = [
			'nombre', 'precio_1','precio_2', 'precio_3', 'precio_4',
			'embalaje', 'retornable', 'calibre', 'vencimiento', 'otra_clasificacion',
			'activo', 'codigo_inter', 'descripcion',
			'proveedor', 'rubro', 'unidad_medida', 'stock_minimo', 'codigo_barra'
		]
		labels = {
			'nombre':"Nombre",
			'embalaje':'Embalaje',
			'retornable':'Retornable',
			'calibre':'Calibre',
			'vencimiento':'Vencimiento',
			'otra_clasificacion':'Otra Clasificacion',
			'precio_1':'Precio 1',
			'precio_2':'Precio 2',
			'precio_3':'Precio_3',
			'precio_4':'Precio_4',
			'activo':'Activo',
			'codigo_inter':'Codigo Interno',
			'descripcion':'Descripcion',
			'proveedor':'Proveedor',
			'rubro':'Rubro',
			'unidad_medida': 'Unidad de medida',
			'stock_minimo':'Stock Minimo',
			'codigo_barra':'Codigo Barra'
			}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True

		# Ocultar el campo proveedor y hacerlo no requerido
		self.fields['proveedor'].required = False
		self.fields['proveedor'].widget = forms.HiddenInput()

class depositoForm(FormControl, forms.ModelForm):
	class Meta:
		model = Deposito
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True

class stockForm(FormControl, forms.ModelForm):
	class Meta:
		model = Stock
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True

class transporteForm(FormControl, forms.ModelForm):
	class Meta:
		model = Transporte
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True

class proveedor_proveeduriaForm(FormControl, forms.ModelForm):
	class Meta:
		model = Proveedor_proveeduria
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True


class notas_pedidoForm(FormControl, forms.ModelForm):
	class Meta:
		model = Notas_Pedido
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True

class comp_ventaForm(FormControl, forms.ModelForm):
	class Meta:
		model = Comp_Venta
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True

class consol_cargaForm(FormControl, forms.ModelForm):
	class Meta:
		model = Consol_Carga
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True

class guia_distriForm(FormControl, forms.ModelForm):
	class Meta:
		model = Guia_Distri
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True

class informeForm(FormControl, forms.ModelForm):
	class Meta:
		model = Informe
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True

class recibo_proveeForm(FormControl, forms.ModelForm):
	class Meta:
		model = Recibo_Provee
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True


class rubroForm(FormControl, forms.ModelForm):
	class Meta:
		model = Rubro
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True

class vendedorForm(FormControl, forms.ModelForm):
	class Meta:
		model = Vendendor
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True


class OperacionForm(forms.Form):
	socio = forms.ModelChoiceField(queryset=None)
	sucursal = forms.ModelChoiceField(queryset=None)
	fecha = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
	transporte = forms.ModelChoiceField(queryset=None)
	deposito = forms.ModelChoiceField(queryset=None)
	vendedor = forms.ModelChoiceField(queryset=None)
	punto_venta = forms.ModelChoiceField(queryset=None)

	def __init__(self, *args, **kwargs):
		request = kwargs.pop('request', None)
		super().__init__(*args, **kwargs)
		if request:
			cons = consorcio(request)
			self.fields['socio'].queryset = Socio.objects.filter(consorcio=cons, baja__isnull=True)
			self.fields['sucursal'].queryset = Sucursal.objects.none()
			self.fields['transporte'].queryset = Transporte.objects.filter(consorcio=cons)
			self.fields['deposito'].queryset = Deposito.objects.filter(consorcio=cons)
			self.fields['vendedor'].queryset = Vendendor.objects.filter(consorcio=cons)
			self.fields['punto_venta'].queryset = PointOfSales.objects.filter(owner=cons.contribuyente)


			if 'socio' in self.data:
				try:
					socio_id = int(self.data.get('socio'))
					self.fields['sucursal'].queryset = Sucursal.objects.filter(socio_id=socio_id)
				except (ValueError, TypeError):
					pass

class VentaProductoForm(forms.ModelForm):
	class Meta:
		model = Venta_Producto
		fields = ['producto', 'precio', 'cantidad']
		widgets = {
			'producto': forms.Select(attrs={'class': 'form-control'}),
			'precio': forms.NumberInput(attrs={'class': 'form-control'}),
			'cantidad': forms.NumberInput(attrs={'class': 'form-control'}),
		}

VentaProductoFormSet = modelformset_factory(
	Venta_Producto,
	form=VentaProductoForm,
	extra=1,
	can_delete=True
)


class CompraForm(forms.Form):
    acreedor = forms.ModelChoiceField(queryset=None)
    numero = forms.CharField()
    fecha = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    deposito = forms.ModelChoiceField(queryset=None)
    observacion = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if request:
            cons = consorcio(request)
            self.fields['acreedor'].queryset = Acreedor.objects.filter(
				consorcio=cons,
				tipo__es_proveeduria=True
				).distinct()
            self.fields['deposito'].queryset = Deposito.objects.filter(consorcio=cons)

class CompraProductoForm(forms.ModelForm):
    class Meta:
        model = Compra_Producto
        fields = ['producto', 'precio', 'cantidad']
        widgets = {
            'producto': forms.Select(attrs={'class': 'form-control'}),
            'precio': forms.NumberInput(attrs={'class': 'form-control'}),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control'}),
        }

CompraProductoFormSet = modelformset_factory(
    Compra_Producto,
    form=CompraProductoForm,
    extra=1,
    can_delete=True
)
