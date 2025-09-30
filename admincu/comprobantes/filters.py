# filters.py
import django_filters
from django_filters.widgets import RangeWidget
from django.db.models import Q
from .models import *

class ComprobanteFilter(django_filters.FilterSet):
    # Rango de fecha (desde/hasta) con método custom para abarcar varias fechas posibles
    fecha = django_filters.DateFromToRangeFilter(
        label='Fecha (desde / hasta)',
        widget=RangeWidget(attrs={'type': 'date', 'class': 'form-control'}),
        method='filtrar_fecha'
    )

    socio__apellido = django_filters.CharFilter(
        label="Identificación del destinatario",
        lookup_expr="icontains"
    )
    numero = django_filters.NumberFilter(
        label="Número de recibo",
        lookup_expr="exact"
    )
    nota_credito__receipt_number = django_filters.NumberFilter(
        label="Número de Nota de crédito C",
        lookup_expr="exact"
    )

    class Meta:
        model = Comprobante
        fields = ['fecha', 'socio__apellido', 'numero', 'nota_credito__receipt_number']

    def filtrar_fecha(self, qs, name, value):
        """
        Aplica el rango a:
        - Comprobante.fecha
        - receipt.issued_date (para filas que muestran la fecha del Receipt)
        - nota_credito.issued_date y nota_credito_anulado.issued_date (por si las querés contemplar)
        """
        if not value:
            return qs

        start = getattr(value, 'start', None)
        stop = getattr(value, 'stop', None)

        cond_start = Q()
        cond_stop = Q()

        if start:
            cond_start = (
                Q(fecha__gte=start) |
                Q(receipt__issued_date__gte=start) |
                Q(nota_credito__issued_date__gte=start) |
                Q(nota_credito_anulado__issued_date__gte=start)
            )

        if stop:
            cond_stop = (
                Q(fecha__lte=stop) |
                Q(receipt__issued_date__lte=stop) |
                Q(nota_credito__issued_date__lte=stop) |
                Q(nota_credito_anulado__issued_date__lte=stop)
            )

        # AND entre límites; cada límite es un OR entre campos de fecha
        if start and stop:
            return qs.filter(cond_start & cond_stop)
        elif start:
            return qs.filter(cond_start)
        elif stop:
            return qs.filter(cond_stop)
        return qs



class ComprobanteFilterSocio(django_filters.FilterSet):
    fecha = django_filters.DateRangeFilter(label="Fecha", lookup_expr="icontains")
    numero = django_filters.NumberFilter(label="Numero de recibo", lookup_expr="exact")
    nota_credito__receipt_number = django_filters.NumberFilter(label="Numero de Nota de credito C", lookup_expr="exact")

    class Meta:
        model = Comprobante
        fields = []