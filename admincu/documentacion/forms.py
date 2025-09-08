# documentacion/forms.py
from django import forms
from admincu.forms import FormControl
from .models import *
from arquitectura.models import Socio

ISO_FMT = '%Y-%m-%d'

class FormBase(FormControl, forms.ModelForm):
    fecha = forms.DateField(
        required=False,
        widget=forms.DateInput(format=ISO_FMT, attrs={"type": "date"}),
        input_formats=[ISO_FMT],
    )
    contenido = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 16, "style": "font-family:monospace"})
    )

    class Meta:
        fields = []
        widgets = {
            # Estos widgets aplican si el campo está en fields del form concreto
            "firma": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "transcripcion": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "foja": forms.NumberInput(attrs={"min": 1, "step": 1}),
        }
        help_texts = {
            "firma": "Marcar si el documento/acta está firmado.",
            "transcripcion": "Marcar si el texto es una transcripción.",
            "foja": "Número de foja (sólo para actas).",
        }

    def __init__(self, consorcio=None, *args, **kwargs):
        self.consorcio = consorcio
        super().__init__(*args, **kwargs)

        if "integrantes" in self.fields:
            qs = (
                Socio.objects
                .filter(consorcio=consorcio, baja__isnull=True, estado="vigente")
                .exclude(directivo__isnull=True)
                .exclude(directivo="")
                .order_by("apellido", "nombre")
            )
            self.fields["integrantes"].queryset = qs
            # 🔑 Mostrar "Apellido, Nombre - Cargo"
            self.fields["integrantes"].label_from_instance = (
                lambda obj: f"{obj.apellido}, {obj.nombre} - {obj.get_directivo_display()}"
            )

        if "nombre" in self.fields:
            self.fields["nombre"].required = True

    # Validación suave de foja (si el form la incluye)
    def clean_foja(self):
        foja = self.cleaned_data.get("foja")
        if foja is not None and foja < 1:
            raise forms.ValidationError("La foja debe ser un entero mayor o igual a 1.")
        return foja


class EstatutoForm(FormBase):
    class Meta(FormBase.Meta):
        model = Estatuto
        fields = ["nombre", "fecha", "numero", "contenido", "descripcion", "firma", "transcripcion"]


class ActaConsejoForm(FormBase):
    class Meta(FormBase.Meta):
        model = ActaConsejo
        fields = ["nombre", "fecha", "numero", "integrantes", "foja", "contenido", "descripcion", "firma", "transcripcion"]


class ActaJuntaFiscalizadoraForm(FormBase):
    class Meta(FormBase.Meta):
        model = ActaJuntaFiscalizadora
        fields = ["nombre", "fecha", "numero", "integrantes", "foja", "contenido", "descripcion", "firma", "transcripcion"]


class ActaAsambleaForm(FormBase):
    class Meta(FormBase.Meta):
        model = ActaAsamblea
        fields = ["nombre", "fecha", "numero", "integrantes", "foja", "contenido", "descripcion", "firma", "transcripcion"]


class ConvenioDocForm(FormBase):
    class Meta(FormBase.Meta):
        model = ConvenioDoc
        fields = ["nombre", "fecha", "numero", "contenido", "descripcion", "firma", "transcripcion"]


