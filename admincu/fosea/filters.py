from .models import *
import django_filters


class SolicitudFilter(django_filters.FilterSet):
    socio__apellido = django_filters.CharFilter(label="Identificacion del destinatario", lookup_expr="icontains")
    fecha = django_filters.DateRangeFilter(label="Fecha", lookup_expr="icontains")

    class Meta:
        model = Solicitud
        fields = []