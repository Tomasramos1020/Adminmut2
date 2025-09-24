# remitos/filters.py
import django_filters
from django_filters.widgets import RangeWidget
from .models import Remito, AjusteStock, Deposito

class RemitoFilter(django_filters.FilterSet):
    socio__apellido = django_filters.CharFilter(
        label="Identificación del destinatario",
        field_name="socio__apellido", lookup_expr="icontains"
    )
    fecha = django_filters.DateRangeFilter(label="Fecha")
    numero = django_filters.NumberFilter(label="Número de remito", lookup_expr="exact")
    deposito__nombre = django_filters.CharFilter(label="Depósito", lookup_expr="icontains")

    class Meta:
        model = Remito
        fields = []


class AjusteFilter(django_filters.FilterSet):
    # rango de fechas
    fecha = django_filters.DateFromToRangeFilter(
        label="Fecha (desde/hasta)",
        widget=RangeWidget(attrs={'type': 'date'})
    )
    motivo = django_filters.CharFilter(label="Motivo contiene", lookup_expr='icontains')
    anulado = django_filters.BooleanFilter(label="Anulado")

    # opcional: filtrar por depósito
    deposito = django_filters.ModelChoiceFilter(
        label="Depósito",
        queryset=Deposito.objects.none()
    )

    def __init__(self, *args, **kwargs):
        # paso el request para limitar depósitos por consorcio
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request:
            from admincu.funciones import consorcio
            cons = consorcio(self.request)
            self.filters['deposito'].queryset = Deposito.objects.filter(consorcio=cons)

    class Meta:
        model = AjusteStock
        fields = ['fecha', 'deposito', 'anulado', 'motivo']
