from django import forms
from admincu.forms import FormControl
from .models import *



class sucursalForm(FormControl, forms.ModelForm):
	class Meta:
		model = Sucursal
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True


class productoForm(FormControl, forms.ModelForm):
	class Meta:
		model = Producto
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True

class depositoForm(FormControl, forms.ModelForm):
	class Meta:
		model = Sucursal
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True

class stockForm(FormControl, forms.ModelForm):
	class Meta:
		model = Sucursal
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True

class transporteForm(FormControl, forms.ModelForm):
	class Meta:
		model = Sucursal
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True

class notas_pedidoForm(FormControl, forms.ModelForm):
	class Meta:
		model = Sucursal
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True

class comp_ventaForm(FormControl, forms.ModelForm):
	class Meta:
		model = Sucursal
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True

class consol_cargaForm(FormControl, forms.ModelForm):
	class Meta:
		model = Sucursal
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True

class guia_distriForm(FormControl, forms.ModelForm):
	class Meta:
		model = Sucursal
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True

class informeForm(FormControl, forms.ModelForm):
	class Meta:
		model = Sucursal
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True

class recibo_proveeForm(FormControl, forms.ModelForm):
	class Meta:
		model = Sucursal
		fields = ['nombre',]
		labels = {'nombre':"Nombre",}

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True
