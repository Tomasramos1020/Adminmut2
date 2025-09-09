from .models import *
import django_filters
from django_afip.models import PointOfSales
from django import forms
from django.db.models import Min, Q

class LiquidacionFilter(django_filters.FilterSet):
    numero = django_filters.NumberFilter(label="Numero de liquidacion", lookup_expr="exact")
    fecha = django_filters.DateRangeFilter(label="Fecha de liquidacion", lookup_expr="icontains")

    class Meta:
        model = Liquidacion
        fields = ['estado']



class CreditoFilter(django_filters.FilterSet):
    liquidacion__numero = django_filters.NumberFilter(label="Numero de liquidacion", lookup_expr="exact")
    factura__receipt__receipt_number = django_filters.NumberFilter(label="Numero de factura", lookup_expr="icontains")
    periodo = django_filters.DateRangeFilter(label="Periodo", lookup_expr="icontains")
    ingreso__nombre = django_filters.CharFilter(label="Nombre del concepto", lookup_expr="icontains")
    socio__numero_asociado = django_filters.NumberFilter(label="Numero de asociado", lookup_expr="exact")
    socio__apellido = django_filters.CharFilter(label="Apellido del destinatario", lookup_expr="icontains")

    class Meta:
        model = Credito
        fields = []


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
        field_name='liquidacion__punto',
        queryset=PointOfSales.objects.none(),
        label='Punto de venta',
    )

    # 👉 ahora filtra por la fecha del primer crédito raíz (anotación fecha_factura)
    fecha = django_filters.DateFromToRangeFilter(
        method='filter_fecha_factura',
        label='Fecha (desde / hasta)',
        widget=django_filters.widgets.RangeWidget(attrs={"type": "date", "class": "form-control"})
    )

    class Meta:
        model = Factura
        fields = []

    def __init__(self, data=None, queryset=None, *, request=None, **kwargs):
        super().__init__(data=data, queryset=queryset, request=request, **kwargs)
        try:
            from admincu.funciones import consorcio
            c = consorcio(request)
            self.filters['punto'].queryset = (
                PointOfSales.objects.filter(liquidacion__factura__consorcio=c).distinct()
            )
            es_fed = getattr(c, 'es_federacion', None)
            if es_fed is None:
                es_fed = getattr(c, 'federacion', False)
            if 'apellido' in self.form.fields:
                self.form.fields['apellido'].label = 'Matrícula' if es_fed else 'Apellido'
        except Exception:
            self.filters['punto'].queryset = PointOfSales.objects.all()

        # estética
        for name, f in self.form.fields.items():
            if not isinstance(f.widget, forms.CheckboxInput) and getattr(f.widget, 'input_type', '') != 'date':
                f.widget.attrs.setdefault('class', 'form-control')

    def filter_fecha_factura(self, qs, name, value):
        """
        Filtra por la anotación fecha_factura (Min fecha de crédito raíz).
        value tiene .start y .stop (pueden venir None).
        """
        qs = qs.annotate(
            fecha_factura=Min('credito__fecha', filter=Q(credito__padre__isnull=True))
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



