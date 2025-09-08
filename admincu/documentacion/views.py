# documentacion/views.py
from django.views import generic
from django.urls import reverse_lazy
from django.contrib import messages
from admincu.funciones import consorcio
from .models import *
from .forms import *
from arquitectura.models import Servicio_mutual
try:
    from arquitectura.forms import servicioForm  # opcional
except Exception:
    ServicioForm = None

# Campos considerados "largos" en cualquier modelo
LONG_FIELD_NAMES = {"contenido", "descripcion", "texto", "cuerpo", "reglamento"}

# Modo: True = mostrar una columna "Resumen"; False = ocultar por completo esos campos
SHOW_PREVIEW = True
PREVIEW_LABEL = "Contenido"
PREVIEW_TRUNC = 300  # caracteres para truncate



PIVOT = {
    'Estatuto': ['Estatutos', EstatutoForm, Estatuto, ["nombre", "fecha", "numero", "contenido","firma","transcripcion"]],
    'ActaConsejo': ['Actas de Consejo', ActaConsejoForm, ActaConsejo, ["nombre", "fecha", "numero", "foja","integrantes", "contenido","firma","transcripcion"]],
    'ActaJuntaFiscalizadora': ['Actas de Junta Fiscalizadora', ActaJuntaFiscalizadoraForm, ActaJuntaFiscalizadora, ["nombre", "fecha", "numero","foja", "integrantes", "contenido","firma","transcripcion"]],
    'ActaAsamblea': ['Actas de Asamblea', ActaAsambleaForm, ActaAsamblea, ["nombre", "fecha", "numero", "foja","integrantes", "contenido","firma","transcripcion"]],
    'ConvenioDoc': ['Convenios', ConvenioDocForm, ConvenioDoc, ["nombre", "fecha", "numero", "contenido","firma","transcripcion"]],
    'Servicio_mutual': [
        'Reglamentos',
        servicioForm,
        Servicio_mutual,
        ["nombre", "fecha_reglamento", "descripcion", "nombre_reglamento"],
        {
            "nombre": "Nombre del servicio",
            "descripcion": "Reglamento",
            "nombre_reglamento": "Nombre del Reglamento",
            "fecha_reglamento": "Fecha del Reglamento",
        },
    ],
}


class Index_doc(generic.TemplateView):
    template_name = 'index_doc.html'

class Listado_doc(generic.ListView):
    template_name = 'elemento_doc.html'
    paginate_by = 50

    def get_queryset(self):
        modelo = self.kwargs['modelo']
        ModelCls = PIVOT[modelo][2]
        return ModelCls.objects.filter(consorcio=consorcio(self.request))

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        modelo = self.kwargs['modelo']
        label, FormCls, ModelCls, list_fields, *rest = PIVOT[modelo]
        overrides = rest[0] if rest else {}

        # Labels del ModelForm (si existen)
        form_labels = {}
        Meta = getattr(FormCls, 'Meta', None)
        if Meta:
            form_labels = getattr(Meta, 'labels', {}) or {}

        # Separar campos largos / visibles
        long_fields = [f for f in list_fields if f in LONG_FIELD_NAMES]
        visible_fields = [f for f in list_fields if f not in LONG_FIELD_NAMES]

        # ¿Agregamos columna de preview?
        use_preview = SHOW_PREVIEW and bool(long_fields)
        if use_preview:
            visible_fields.append("preview")  # columna sintética

        # Construir labels “lindos” solo para los visibles (+ preview)
        special = {"preview": PREVIEW_LABEL, "integrantes": "Integrantes"}
        pretty = {}
        for f in visible_fields:
            if f in special:
                lbl = special[f]
            elif f in overrides:
                lbl = overrides[f]
            elif f in form_labels:
                lbl = form_labels[f]
            else:
                try:
                    lbl = ModelCls._meta.get_field(f).verbose_name
                except Exception:
                    lbl = f.replace("_", " ")
            pretty[f] = str(lbl[:1]).upper() + str(lbl)[1:]

        # Pares (campo, etiqueta) para iterar fácil en el template
        columns = [(f, pretty[f]) for f in visible_fields]

        ctx.update({
            "elemento": modelo,
            "nombre_elemento": label,
            "columns": columns,                 # [(field, label), ...]
            "long_field": long_fields[0] if long_fields else None,  # 1er campo largo
            "preview_trunc": PREVIEW_TRUNC,
        })
        return ctx




class Crear_doc(generic.CreateView):
    template_name = 'instancia_doc.html'

    def get_form_class(self):
        return PIVOT[self.kwargs['modelo']][1]

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['consorcio'] = consorcio(self.request)
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        modelo = self.kwargs['modelo']
        ctx["elemento"] = modelo
        ctx["nombre_elemento"] = PIVOT[modelo][0]
        # si querés, podés pasar columnas también:
        # ctx["list_fields"] = PIVOT[modelo][3]
        return ctx

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.consorcio = consorcio(self.request)
        obj.save()
        form.save_m2m()
        messages.success(self.request, "Documento guardado con éxito.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('doc_listado', args=(self.kwargs['modelo'],))

class Instancia_doc(Crear_doc, generic.UpdateView):
    def get_object(self, queryset=None):
        ModelCls = PIVOT[self.kwargs['modelo']][2]
        return ModelCls.objects.get(pk=self.kwargs['pk'], consorcio=consorcio(self.request))



# Create your views here.
