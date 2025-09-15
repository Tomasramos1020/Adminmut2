from django import forms
from admincu.forms import FormControl
from .models import *
from django.forms import modelformset_factory
from admincu.funciones import consorcio
from django.forms.widgets import DateInput
from django_afip.models import PointOfSales
from arquitectura.models import Acreedor
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation


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

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if request:
            try:
                c = consorcio(request)
                # Ajustá el filtro a tu modelo de productos
                # Ejemplos habituales: Producto.objects.filter(consorcio=c, baja__isnull=True)
                self.fields['producto'].queryset = (
                    Producto.objects.filter(consorcio=c)  # + los filtros que uses (activos, sin baja, etc.)
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
