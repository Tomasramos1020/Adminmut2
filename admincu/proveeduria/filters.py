# remitos/filters.py
import django_filters
from .models import Remito

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
