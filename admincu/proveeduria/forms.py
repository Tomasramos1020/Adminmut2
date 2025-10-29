from django import forms
from admincu.forms import FormControl
from .models import *
from django.forms import modelformset_factory
from admincu.funciones import consorcio
from django.forms.widgets import DateInput
from django_afip.models import PointOfSales
from arquitectura.models import Acreedor
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from django.forms import ModelForm
from django.forms import formset_factory
from creditos.models import Factura
from django.forms import inlineformset_factory
import json


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
	# margen virtual (% markup sobre costo)
	margen_pct = forms.DecimalField(
		label="Margen (%)", max_digits=6, decimal_places=2, required=False,
		help_text="Porcentaje sobre costo. Ej: 20 = 20%.",
		widget=forms.NumberInput(attrs={"step": "0.01"})
	)

	class Meta:
		model = Producto
		fields = [
			'nombre',
			'costo',                 # 👈 ahora es de modelo
			'precio_1','precio_2','precio_3','precio_4',
			'embalaje','retornable','calibre','vencimiento','otra_clasificacion',
			'activo','codigo_inter','descripcion',
			'proveedor','rubro','unidad_medida','stock_minimo','codigo_barra',
		]
		widgets = {
			'costo':    forms.NumberInput(attrs={"step": "0.01"}),
			'precio_1': forms.NumberInput(attrs={"step": "0.01"}),
			'precio_2': forms.NumberInput(attrs={"step": "0.01"}),
			'precio_3': forms.NumberInput(attrs={"step": "0.01"}),
			'precio_4': forms.NumberInput(attrs={"step": "0.01"}),
		}

	field_order = [
		'nombre',
		'costo', 'margen_pct',
		'precio_1','precio_2','precio_3','precio_4',
		'embalaje','retornable','calibre','vencimiento','otra_clasificacion',
		'activo','codigo_inter','descripcion',
		'proveedor','rubro','unidad_medida','stock_minimo','codigo_barra',
	]

	def __init__(self, consorcio=None, *args, **kwargs):
		self.consorcio = consorcio
		super().__init__(*args, **kwargs)
		self.fields['nombre'].required = True

		self.fields['proveedor'].required = False
		self.fields['proveedor'].widget = forms.HiddenInput()

		# Inicializar margen_pct desde costo y precio_1
		costo = self.instance.costo if (self.instance and self.instance.pk) else None
		p1 = self.instance.precio_1 if (self.instance and self.instance.pk) else None
		try:
			costD = Decimal(costo) if costo is not None else None
			p1D = Decimal(p1) if p1 is not None else None
		except (InvalidOperation, TypeError, ValueError):
			costD = p1D = None

		if costD is not None and p1D is not None:
			if costD > 0:
				margen = ((p1D / costD) - Decimal('1')) * Decimal('100')
				self.fields['margen_pct'].initial = margen.quantize(Decimal('0.01'))
			else:
				self.fields['margen_pct'].initial = Decimal('0.00')

		self.order_fields(self.field_order)

	def clean(self):
		cleaned = super().clean()

		def D(x):
			if x in (None, ""): return None
			try: return Decimal(x)
			except (InvalidOperation, TypeError, ValueError): return None

		costo = D(cleaned.get("costo"))
		precio_1 = D(cleaned.get("precio_1"))
		margen_pct = D(cleaned.get("margen_pct"))

		# Si no hay costo, forzamos 0.00
		if costo is None:
			costo = Decimal('0.00')
			cleaned['costo'] = costo

		changed = set(getattr(self, "changed_data", []))
		ch_precio = "precio_1" in changed
		ch_margen = "margen_pct" in changed
		ch_costo  = "costo" in changed

		# Reglas de sync (markup sobre costo): precio_1 = costo * (1 + m/100)
		def recompute_margen():
			if costo is not None and precio_1 is not None:
				if costo > 0:
					cleaned["margen_pct"] = ((precio_1 / costo) - Decimal('1')) * Decimal('100')
				else:
					cleaned["margen_pct"] = Decimal('0.00')
				cleaned["margen_pct"] = cleaned["margen_pct"].quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

		def recompute_precio():
			if costo is not None and margen_pct is not None:
				factor = (Decimal('1') + (margen_pct / Decimal('100')))
				cleaned["precio_1"] = (costo * factor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

		if ch_precio and not ch_margen:
			recompute_margen()
		elif ch_margen and not ch_precio:
			recompute_precio()
		elif ch_precio and ch_margen:
			# Priorizamos precio_1 y recalculamos margen
			recompute_margen()
		else:
			# Si cambió costo, derivamos precio desde margen si existe; si no, derivamos margen desde precio
			if ch_costo:
				if margen_pct is not None:
					recompute_precio()
				elif precio_1 is not None:
					recompute_margen()
			else:
				# Nada cambió explícito: completar el faltante
				if margen_pct is None and precio_1 is not None:
					recompute_margen()
				elif precio_1 is None and margen_pct is not None:
					recompute_precio()

		return cleaned




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
	sucursal = forms.ModelChoiceField(queryset=None, required=False)
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
		fields = ['producto', 'precio', 'cantidad', 'costo']
		widgets = {
			'producto': forms.Select(attrs={'class': 'form-control'}),
			'precio': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
			# cantidad es IntegerField en el modelo → step 1 para evitar decimales
			'cantidad': forms.NumberInput(attrs={'class': 'form-control', 'step': '1', 'min': '1'}),
			'costo': forms.NumberInput(attrs={
				'class': 'form-control', 'step': '0.01', 'readonly': 'readonly'
			}),
		}

VentaProductoFormSet = modelformset_factory(
	Venta_Producto,
	form=VentaProductoForm,
	extra=1,
	can_delete=True
)

# forms.py
LETRAS_CBTE = (('A','A'),('B','B'),('C','C'),('M','M'))

class CompraForm(forms.Form):
	letra = forms.ChoiceField(choices=LETRAS_CBTE, initial='A', label="Letra")
	punto_venta = forms.IntegerField(min_value=1, max_value=9999, label="Punto de venta")
	numero_cbte = forms.IntegerField(min_value=1, max_value=99999999, label="Número")

	acreedor = forms.ModelChoiceField(queryset=None, label="Acreedor")
	# número "legacy" que se guardará en Deuda.numero:
	numero = forms.CharField(required=False, widget=forms.HiddenInput())

	fecha = forms.DateField(widget=forms.DateInput(attrs={'type':'date'}))
	deposito = forms.ModelChoiceField(queryset=None, label="Depósito")
	observacion = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))

	def __init__(self, *args, **kwargs):
		request = kwargs.pop('request', None)
		super().__init__(*args, **kwargs)
		if request:
			c = consorcio(request)
			self.fields['acreedor'].queryset = Acreedor.objects.filter(
				consorcio=c, tipo__es_proveeduria=True
			).distinct()
			self.fields['deposito'].queryset = Deposito.objects.filter(consorcio=c)

	def clean(self):
		cleaned = super().clean()
		letra = cleaned.get('letra')
		pv = cleaned.get('punto_venta')
		num = cleaned.get('numero_cbte')
		# Componer en formato compacto sin guiones: L + PPPP + NNNNNNNN
		if letra and pv and num:
			cleaned['numero'] = f"{letra}-{pv:04d}-{num:08d}"
		return cleaned


class CompraProductoForm(forms.ModelForm):
	class Meta:
		model = Compra_Producto
		fields = ['producto', 'precio', 'cantidad']
		widgets = {
			'producto': forms.Select(attrs={'class': 'form-control'}),
			'precio': forms.NumberInput(attrs={'class': 'form-control'}),
			'cantidad': forms.NumberInput(attrs={'class': 'form-control'}),
		}

	def __init__(self, *args, **kwargs):
		request = kwargs.pop('request', None)
		super().__init__(*args, **kwargs)
		if request:
			try:
				c = consorcio(request)
				# Ajustá el filtro a tu modelo de productos
				# Ejemplos habituales: Producto.objects.filter(consorcio=c, baja__isnull=True)
				self.fields['producto'].queryset = (
					Producto.objects.filter(consorcio=c, es_modulo=False)  # + los filtros que uses (activos, sin baja, etc.)
					.order_by('nombre')
				)
			except Exception:
				# Si por algún motivo no se detecta el consorcio, al menos dejá la lista vacía
				self.fields['producto'].queryset = Producto.objects.none()


CompraProductoFormSet = modelformset_factory(
	Compra_Producto,
	form=CompraProductoForm,
	extra=1,
	can_delete=True
)

class RemitoForm(forms.Form):
	socio      = forms.ModelChoiceField(queryset=Socio.objects.none(), required=False)
	sucursal   = forms.ModelChoiceField(queryset=Sucursal.objects.none(), required=False)
	fecha      = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
	deposito   = forms.ModelChoiceField(queryset=Deposito.objects.none())
	transporte = forms.ModelChoiceField(queryset=Transporte.objects.none(), required=False)
	vendedor   = forms.ModelChoiceField(queryset=Vendendor.objects.none(), required=False)
	observacion = forms.CharField(widget=forms.Textarea(attrs={'rows':3}), required=False)

	def __init__(self, *args, **kwargs):
		request = kwargs.pop('request', None)
		super().__init__(*args, **kwargs)
		if request:
			cons = consorcio(request)
			self.fields['socio'].queryset      = Socio.objects.filter(consorcio=cons, baja__isnull=True)
			self.fields['deposito'].queryset   = Deposito.objects.filter(consorcio=cons)
			self.fields['transporte'].queryset = Transporte.objects.filter(consorcio=cons)
			self.fields['vendedor'].queryset   = Vendendor.objects.filter(consorcio=cons)
			# sucursal depende del socio (AJAX como ya usás)
			self.fields['sucursal'].queryset   = Sucursal.objects.none()
			if 'socio' in self.data:
				try:
					socio_id = int(self.data.get('socio'))
					self.fields['sucursal'].queryset = Sucursal.objects.filter(socio_id=socio_id)
				except (ValueError, TypeError):
					pass

class RemitoItemForm(ModelForm):
	# Campo informativo/editarle: NO está en el modelo
	precio = forms.DecimalField(
		required=False, min_value=0, decimal_places=2, max_digits=12,
		widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
	)

	class Meta:
		model = RemitoItem
		fields = ['producto', 'cantidad', 'detalle']  # el formset igual va a traer 'precio' porque está declarado arriba
		widgets = {
			'producto': forms.Select(attrs={'class': 'form-control producto-select'}),
			'cantidad': forms.NumberInput(attrs={'class': 'form-control cantidad-input', 'step': '0.01', 'min': '0.01'}),
			'detalle':  forms.TextInput(attrs={'class': 'form-control'}),
		}

	def clean_precio(self):
		# Opcional: si no viene precio, lo dejamos en None (lo rellenará el JS al elegir producto)
		p = self.cleaned_data.get('precio')
		return p


RemitoItemFormSet = modelformset_factory(
	RemitoItem,
	form=RemitoItemForm,
	extra=1,
	can_delete=True
)

class AjusteForm(forms.Form):
	fecha    = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
	deposito = forms.ModelChoiceField(queryset=Deposito.objects.none())
	motivo   = forms.CharField(widget=forms.Textarea(attrs={'rows':3}), required=False)

	def __init__(self, *args, **kwargs):
		request = kwargs.pop('request', None)
		super().__init__(*args, **kwargs)
		if request:
			cons = consorcio(request)
			self.fields['deposito'].queryset = Deposito.objects.filter(consorcio=cons)


class AjusteItemForm(ModelForm):
	class Meta:
		model = AjusteStockItem
		fields = ['producto', 'sentido', 'cantidad', 'detalle']
		widgets = {
			'producto': forms.Select(attrs={'class':'form-control'}),
			'sentido':  forms.Select(attrs={'class':'form-control'}),
			'cantidad': forms.NumberInput(attrs={'class':'form-control', 'step':'0.01', 'min':'0.01'}),
			'detalle':  forms.TextInput(attrs={'class':'form-control'}),
		}

AjusteItemFormSet = modelformset_factory(
	AjusteStockItem,
	form=AjusteItemForm,
	extra=1,
	can_delete=True
)

# forms_proveeduria_nc.py

class NCProveeduriaInicialForm(forms.Form):
	socio = forms.ModelChoiceField(queryset=Socio.objects.none(), empty_label="-- Seleccionar Socio --")
	factura = forms.ModelChoiceField(queryset=Factura.objects.none(), empty_label="-- Seleccionar Factura (Proveeduría) --")

	def __init__(self, *args, **kwargs):
		cons = kwargs.pop('consorcio')
		super().__init__(*args, **kwargs)

		self.fields['socio'].queryset = Socio.objects.filter(
			consorcio=cons, nombre_servicio_mutual__isnull=True
		)
		self.fields['factura'].queryset = Factura.objects.none()

		# detectar socio seleccionado (POST o initial)
		socio_id = None
		if self.data.get('socio'):
			socio_id = self.data.get('socio')
		elif self.initial.get('socio'):
			s = self.initial.get('socio')
			socio_id = s.id if hasattr(s, 'id') else s

		if socio_id:
			# ✅ Facturas del socio que tengan al menos un Crédito de Proveeduría
			qs = (Factura.objects
				  .filter(
					  consorcio=cons,
					  socio_id=socio_id,
					  credito__ingreso__es_proveeduria=True,   # <- criterio sólido
					  liquidacion__estado='confirmado',        # opcional: solo confirmadas
				  )
				  .select_related('receipt')
				  .order_by('-id')
				  .distinct()
				  )
			self.fields['factura'].queryset = qs

	def clean(self):
		cleaned = super().clean()
		socio = cleaned.get('socio')
		factura = cleaned.get('factura')
		if socio and factura:
			if factura.socio_id != socio.id:
				raise forms.ValidationError("La factura seleccionada no corresponde al socio elegido.")
			# doble chequeo de Proveeduría por si alguien fuerza el POST
			if not factura.credito_set.filter(ingreso__es_proveeduria=True).exists():
				raise forms.ValidationError("La factura seleccionada no pertenece a Proveeduría.")
		return cleaned


class DevolucionForm(forms.Form):
	vp_id = forms.IntegerField(widget=forms.HiddenInput())
	producto = forms.CharField(disabled=True, required=False)
	precio = forms.DecimalField(disabled=True, required=False, max_digits=9, decimal_places=2)
	cantidad_original = forms.DecimalField(disabled=True, required=False, max_digits=12, decimal_places=2)
	ya_devuelto = forms.DecimalField(disabled=True, required=False, max_digits=12, decimal_places=2)
	devolver = forms.DecimalField(required=False, max_digits=12, decimal_places=2, min_value=Decimal('0'))
	motivo = forms.CharField(required=False, max_length=200)

DevolucionFormSet = formset_factory(DevolucionForm, extra=0)


class ModuloForm(forms.ModelForm):

	precio = forms.DecimalField(label="Precio", max_digits=9, decimal_places=2, required=False)
	
	class Meta:
		model = Producto
		fields = [
			'nombre', 'descripcion', 'activo',
		]

	def __init__(self, *args, **kwargs):
		self.request = kwargs.pop('request', None)
		super().__init__(*args, **kwargs)

		if self.instance and self.instance.pk:
			self.fields['precio'].initial = self.instance.precio_1

	def clean(self):
		cd = super().clean()
		# Este form siempre crea/edita módulos
		# Si estás en update, el modelo ya tiene es_modulo=True.
		return cd


from django.core.exceptions import ValidationError

class ModuloComponenteForm(forms.ModelForm):
    class Meta:
        model = ModuloComponente
        fields = ['componente', 'cantidad']

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        qs = Producto.objects.none()
        if self.request:
            c = consorcio(self.request)
            qs = Producto.objects.filter(consorcio=c, activo=True)
            # no permitir módulos como componentes
            qs = qs.filter(es_modulo=False)

        # si estoy editando, que no se pueda elegir a sí mismo
        if self.instance and self.instance.producto_modulo_id:
            qs = qs.exclude(id=self.instance.producto_modulo_id)

        # set queryset final
        self.fields['componente'].queryset = qs

        # armamos el mapa id -> costo_unitario (str para que sea JSON safe)
        cost_map = {
            str(prod.id): str(prod.precio_compra)  # ejemplo "12.34"
            for prod in qs
        }

        # mostramos el costo al lado del nombre en el <option>
        opciones = []
        for prod in qs:
            costo_unitario = prod.precio_compra  # Decimal según tu modelo
            opciones.append((
                prod.id,
                f"{prod.nombre} (${costo_unitario})",
            ))
        self.fields['componente'].choices = opciones

        # agregamos attrs al <select> así quedan en el HTML
        self.fields['componente'].widget.attrs.update({
            'class': 'componente-select',
            'data-cost-map': json.dumps(cost_map),  # <= clave
        })

        # agregamos clase al input cantidad
        self.fields['cantidad'].widget.attrs.update({
            'class': 'cantidad-input',
            'step': '0.01',
            'min': '0',
        })

    def clean_cantidad(self):
        val = self.cleaned_data.get('cantidad')
        if val is None or Decimal(val) <= 0:
            raise ValidationError("La cantidad debe ser mayor a 0.")
        return val


ModuloComponenteFormSet = inlineformset_factory(
	parent_model=Producto,
	model=ModuloComponente,
	form=ModuloComponenteForm,
	fk_name='producto_modulo',
	extra=4,
	can_delete=True,
	min_num=1,
	validate_min=True,
)
