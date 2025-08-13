from django import forms
from django.forms import inlineformset_factory
from django.forms import formset_factory
from .models import Solicitud, SolicitudLinea
from arquitectura.models import Establecimiento, Socio, ZonasPorCultivo
from admincu.funciones import consorcio
from django.forms.widgets import DateInput
from django.forms import modelformset_factory, inlineformset_factory
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet

# forms.py
class SolicitudForm(forms.ModelForm):
    fecha = forms.DateField(
        widget=forms.DateInput(
            attrs={'type': 'date', 'class': 'form-control'},
            format='%Y-%m-%d',
        ),
        input_formats=['%Y-%m-%d', '%d/%m/%Y'],  # acepta ambos al recibir POST
    )
    class Meta:
        model = Solicitud
        fields = ['suscripcion', 'fecha', 'campaña', 'socio']
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if request:
            cons = consorcio(request)
            self.fields['socio'].queryset = (
                self.fields['socio'].queryset
                .filter(consorcio=cons, es_socio=True, baja__isnull=True)
                .exclude(nombre_servicio_mutual__isnull=False)
            )
    def clean(self):
        cleaned = super().clean()
        faltantes = []
        for campo in ('campaña', 'fecha', 'suscripcion', 'socio'):
            if not cleaned.get(campo):
                faltantes.append(campo)
        if faltantes:
            raise ValidationError('Completá todos los campos: campaña, fecha, suscripción y socio.')
        return cleaned

	

class SolicitudLineaForm(forms.ModelForm):
    # Campo extra (no se guarda), solo informativo
    franquicia = forms.DecimalField(required=False, disabled=True, max_digits=10, decimal_places=2)

    class Meta:
        model = SolicitudLinea
        fields = [
            'establecimiento',
            'participacion',
            'cultivo',
            'subsidio_max',
            'aporte_max',
            'aporte_total_qq',
            'hectarea',
        ]
        widgets = {
            'establecimiento': forms.Select(attrs={'class': 'form-control'}),
            'participacion': forms.NumberInput(attrs={'class': 'form-control'}),
            'cultivo': forms.Select(attrs={'class': 'form-control'}),
            'subsidio_max': forms.NumberInput(attrs={'class': 'form-control'}),
            'aporte_max': forms.NumberInput(attrs={'class': 'form-control'}),
            'aporte_total_qq': forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
            'hectarea': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned = super().clean()
        est = cleaned.get('establecimiento')
        cultivo = cleaned.get('cultivo')
        subsidio_max = cleaned.get('subsidio_max') or Decimal('0')
        aporte_max = cleaned.get('aporte_max') or Decimal('0')
        hectarea = cleaned.get('hectarea') or Decimal('0')

        # Validación contra subsidio máximo por zona/cultivo
        if est and est.zona_id and cultivo:
            try:
                zpc = ZonasPorCultivo.objects.get(zona=est.zona, cultivo=cultivo)
                if subsidio_max > zpc.subsidio_maximo:
                    self.add_error('subsidio_max', f'No puede superar {zpc.subsidio_maximo}.')
            except ZonasPorCultivo.DoesNotExist:
                pass

        # Recalcular en servidor (evita manipulaciones del cliente)
        aporte_total = cleaned.get('aporte_total_qq') or Decimal('0')
        cleaned['aporte_total_qq'] = aporte_total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if aporte_total <= 0:
            self.add_error('aporte_total_qq', 'El aporte total debe ser mayor a 0.')
        return cleaned


class LineasBaseFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        lineas_validas = 0

        for form in self.forms:
            # 1) Si el form ya tiene errores de campo, no hay cleaned_data
            if getattr(form, "cleaned_data", None) is None:
                continue

            cd = form.cleaned_data

            # 2) Si está marcado para borrar, saltealo
            if self.can_delete and cd.get("DELETE"):
                continue

            # 3) Si es una fila “vacía” permitida, salteala
            # (cuando todos los campos —salvo id/DELETE— están vacíos)
            if form.empty_permitted:
                hay_algo = any(
                    v not in (None, "", 0, Decimal("0"))
                    for k, v in cd.items()
                    if k not in ("id", "DELETE")
                )
                if not hay_algo:
                    continue

            # Llegamos a una línea “real”
            lineas_validas += 1

            # 4) Regla: aporte_total_qq > 0
            aporte_total = cd.get("aporte_total_qq")
            if aporte_total is None or aporte_total <= 0:
                form.add_error("aporte_total_qq", "Debe ser mayor a 0.")

        # 5) Al menos una línea válida
        if lineas_validas == 0:
            raise ValidationError("Debés cargar al menos una línea de solicitud.")




# Inline formset que ata las líneas a una Solicitud
SolicitudLineaFormSet = inlineformset_factory(
    parent_model=Solicitud,
    model=SolicitudLinea,
    form=SolicitudLineaForm,
    formset=LineasBaseFormSet,   # 👈 importante
    extra=0,
    can_delete=True
)

