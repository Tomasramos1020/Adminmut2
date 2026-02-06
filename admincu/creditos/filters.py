from .models import *
import django_filters
from django_afip.models import PointOfSales
from django import forms
from django.db.models import Min, Q, F, Count
from admincu.funciones import consorcio
from arquitectura.models import PointOfSales, Convenio
from creditos.models import Factura
from django.db.models.functions import Coalesce

class LiquidacionFilter(django_filters.FilterSet):
    numero = django_filters.NumberFilter(label="Numero de liquidacion", lookup_expr="exact")
    fecha = django_filters.DateFromToRangeFilter(
        label="Fecha (desde / hasta)",
        field_name="fecha",
        widget=django_filters.widgets.RangeWidget(attrs={"type": "date", "class": "form-control"}),
    )
    convenio = django_filters.ChoiceFilter(
        label="Convenio",
        method='filter_convenio',
    )

    class Meta:
        model = Liquidacion
        fields = ['estado']

    def __init__(self, data=None, queryset=None, *, request=None, **kwargs):
        super().__init__(data=data, queryset=queryset, request=request, **kwargs)
        c = consorcio(request) if request else None
        if not c:
            self.filters.pop('convenio', None)
            return

        convenios = Convenio.objects.filter(consorcio=c, baja__isnull=True).order_by('nombre')
        choices = [('', '-- Seleccionar convenio --'), ('varios', 'Varios'), ('sin_convenio', 'Sin convenio')]
        choices += [(str(conv.pk), conv.nombre) for conv in convenios]
        self.filters['convenio'].extra['choices'] = choices
        self.filters['convenio'].field.choices = choices
        if getattr(c, 'es_federacion', False):
            self.filters['convenio'].label = 'Servicios AE'

    def filter_convenio(self, queryset, name, value):
        if not value:
            return queryset
        v = str(value).strip().lower()

        if v in ('varios', 'varias'):
            return (
                queryset
                .annotate(_cant_conv=Count('credito__socio__convenio', distinct=True))
                .filter(_cant_conv__gte=2)
            )

        if v in ('sin convenio', 'sin_convenio', 'ninguno', 'ninguna'):
            return (
                queryset
                .annotate(_cant_conv=Count('credito__socio__convenio', distinct=True))
                .filter(_cant_conv=0)
            )

        # id de convenio
        return queryset.filter(credito__socio__convenio_id=value).distinct()



class CreditoFilter(django_filters.FilterSet):
    liquidacion__numero = django_filters.NumberFilter(label="Numero de liquidacion", lookup_expr="exact")
    factura__receipt__receipt_number = django_filters.NumberFilter(label="Numero de factura", lookup_expr="icontains")
    fecha = django_filters.DateFromToRangeFilter(
        label="Fecha (desde / hasta)",
        field_name="fecha",
        widget=django_filters.widgets.RangeWidget(attrs={"type": "date", "class": "form-control"}),
    )
    periodo = django_filters.DateRangeFilter(label="Periodo", lookup_expr="icontains")
    ingreso__nombre = django_filters.CharFilter(label="Nombre del concepto", lookup_expr="icontains")
    socio__numero_asociado = django_filters.NumberFilter(label="Numero de asociado", lookup_expr="exact")
    socio__apellido = django_filters.CharFilter(label="Apellido del destinatario", lookup_expr="icontains")
    convenio = django_filters.ModelChoiceFilter(
        label="Convenio",
        field_name="socio__convenio",
        queryset=Convenio.objects.none(),
        empty_label="-- Seleccionar convenio --",
    )

    class Meta:
        model = Credito
        fields = []

    def __init__(self, data=None, queryset=None, *, request=None, **kwargs):
        super().__init__(data=data, queryset=queryset, request=request, **kwargs)
        c = consorcio(request) if request else None
        if not c:
            self.filters.pop('convenio', None)
            return

        self.filters['convenio'].queryset = (
            Convenio.objects.filter(consorcio=c, baja__isnull=True).order_by('nombre')
        )
        if getattr(c, 'es_federacion', False):
            self.filters['convenio'].label = 'Servicios AE'


class CreditoFilterSocio(django_filters.FilterSet):
    factura__receipt__receipt_number = django_filters.NumberFilter(label="Numero de factura", lookup_expr="icontains")
    periodo = django_filters.DateRangeFilter(label="Periodo", lookup_expr="icontains")
    ingreso__nombre = django_filters.CharFilter(label="Nombre del concepto", lookup_expr="icontains")

    class Meta:
        model = Credito
        fields = []


class FacturaFilter(django_filters.FilterSet):
    numero = django_filters.NumberFilter(
        field_name='receipt__receipt_number',
        lookup_expr='exact',
        label='N° de factura',
    )
    apellido = django_filters.CharFilter(
        field_name='socio__apellido', lookup_expr='icontains', label='Apellido',
    )
    punto = django_filters.ModelChoiceFilter(
        queryset=PointOfSales.objects.none(),
        label='Punto de venta',
        method='filter_punto',
    )
    fecha = django_filters.DateFromToRangeFilter(
        method='filter_fecha_factura',
        label='Fecha (desde / hasta)',
        widget=django_filters.widgets.RangeWidget(attrs={"type": "date", "class": "form-control"}),
    )
    convenio = django_filters.ModelChoiceFilter(
        label="Convenio",
        field_name="socio__convenio",
        queryset=Convenio.objects.none(),
        empty_label="-- Seleccionar convenio --",
    )

    class Meta:
        model = Factura
        fields = []

    def __init__(self, data=None, queryset=None, *, request=None, **kwargs):
        super().__init__(data=data, queryset=queryset, request=request, **kwargs)
        c = consorcio(request)  # siempre presente
        contrib = getattr(c, 'contribuyente', None)

        # Convenios (siempre que haya consorcio)
        if c:
            self.filters['convenio'].queryset = (
                Convenio.objects.filter(consorcio=c, baja__isnull=True).order_by('nombre')
            )
            if getattr(c, 'es_federacion', False):
                self.filters['convenio'].label = 'Servicios AE'
        else:
            self.filters.pop('convenio', None)

        # owner = contribuyente (clave para no ver POS de otros contribuyentes)
        if contrib:
            self.filters['punto'].queryset = PointOfSales.objects.filter(owner=contrib).order_by('number', 'id')
        else:
            self.filters['punto'].queryset = PointOfSales.objects.none()

        # label Apellido ↔ Matrícula (federación)
        es_fed = getattr(c, 'es_federacion', None)
        if es_fed is None:
            es_fed = getattr(c, 'federacion', False)
        if 'apellido' in self.form.fields:
            self.form.fields['apellido'].label = 'Matrícula' if es_fed else 'Apellido'

        # clases Bootstrap por defecto
        for _, f in self.form.fields.items():
            if not isinstance(f.widget, forms.CheckboxInput) and getattr(f.widget, 'input_type', '') != 'date':
                f.widget.attrs.setdefault('class', 'form-control')

    def filter_punto(self, qs, name, value):
        """
        Filtra por:
        - liquidacion__punto (FK en Factura)
        - receipt__point_of_sales (FK en Receipt)
        - compat: también por número (PointOfSales.number), si hiciera falta
        """
        if not value:
            return qs

        v_id = value.pk
        v_num = getattr(value, 'number', None)  # ✅ solo 'number'

        cond = Q(liquidacion__punto_id=v_id) | Q(receipt__point_of_sales_id=v_id)

        # Compat opcional: si alguna vez guardaron el número suelto (no recomendado)
        if v_num is not None:
            cond |= Q(receipt__point_of_sales__number=v_num)

        return qs.filter(cond)


    def filter_fecha_factura(self, qs, name, value):
        """
        Usa la misma definición de fecha que la vista:
        Min(fecha de créditos raíz) o fecha de liquidación.
        """
        qs = qs.annotate(
            fecha_factura=Coalesce(
                Min('credito__fecha', filter=Q(credito__padre__isnull=True)),
                F('liquidacion__fecha'),
            )
        )
        if not value:
            return qs
        if value.start and value.stop:
            return qs.filter(fecha_factura__range=(value.start, value.stop))
        if value.start:
            return qs.filter(fecha_factura__gte=value.start)
        if value.stop:
            return qs.filter(fecha_factura__lte=value.stop)
        return qs


