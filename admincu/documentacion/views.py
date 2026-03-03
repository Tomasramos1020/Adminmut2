# documentacion/views.py
from django.views import generic
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Q
from django.utils.dateparse import parse_date
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



def _es_federacion(request):
    try:
        return bool(getattr(consorcio(request), "es_federacion", False))
    except Exception:
        return False


def get_pivot(request):
    es_federacion = _es_federacion(request)
    acta_consejo_label = "Actas de Junta de Gobierno" if es_federacion else "Actas de Consejo"
    acta_jf_label = "Actas de Junta Ejecutiva" if es_federacion else "Actas de Junta Fiscalizadora"

    return {
        'Estatuto': ['Estatutos', EstatutoForm, Estatuto, ["nombre", "fecha", "numero", "contenido","firma","transcripcion"]],
        'ActaConsejo': [acta_consejo_label, ActaConsejoForm, ActaConsejo, ["nombre", "fecha", "numero", "foja","integrantes", "contenido","firma","transcripcion"]],
        'ActaJuntaFiscalizadora': [acta_jf_label, ActaJuntaFiscalizadoraForm, ActaJuntaFiscalizadora, ["nombre", "fecha", "numero","foja", "integrantes", "contenido","firma","transcripcion"]],
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

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["es_federacion"] = _es_federacion(self.request)
        return ctx

class Listado_doc(generic.ListView):
    template_name = 'elemento_doc.html'
    paginate_by = 50

    def _apply_ordering(self, queryset, model_cls):
        field_names = {
            field.name
            for field in model_cls._meta.get_fields()
            if getattr(field, "concrete", False)
        }
        if "numero" in field_names:
            return queryset.order_by("-numero", "-id")
        return queryset.order_by("-id")

    def _get_date_field_name(self, model_cls, list_fields):
        for field_name in list_fields:
            try:
                field = model_cls._meta.get_field(field_name)
            except Exception:
                continue
            if field.get_internal_type() == "DateField":
                return field_name
        return None

    def _apply_search(self, queryset, model_cls, list_fields):
        termino = (self.request.GET.get("q") or "").strip()
        if not termino:
            return queryset

        filtros = Q()
        termino_lower = termino.lower()
        es_numero = termino.isdigit()
        fecha = parse_date(termino)
        boolean_map = {
            "si": True,
            "sí": True,
            "true": True,
            "1": True,
            "no": False,
            "false": False,
            "0": False,
        }
        valor_booleano = boolean_map.get(termino_lower)

        for field_name in list_fields:
            try:
                field = model_cls._meta.get_field(field_name)
            except Exception:
                continue

            internal_type = field.get_internal_type()
            if internal_type in {"CharField", "TextField", "SlugField", "EmailField"}:
                filtros |= Q(**{f"{field_name}__icontains": termino})
            elif internal_type in {"IntegerField", "BigIntegerField", "SmallIntegerField", "PositiveIntegerField"} and es_numero:
                filtros |= Q(**{field_name: int(termino)})
            elif internal_type == "DateField" and fecha:
                filtros |= Q(**{field_name: fecha})
            elif internal_type == "BooleanField" and valor_booleano is not None:
                filtros |= Q(**{field_name: valor_booleano})
            elif field.many_to_many:
                # Para integrantes (Socio) buscamos por apellido, nombre, CUIT y cargo.
                filtros |= (
                    Q(**{f"{field_name}__apellido__icontains": termino}) |
                    Q(**{f"{field_name}__nombre__icontains": termino}) |
                    Q(**{f"{field_name}__cuit__icontains": termino}) |
                    Q(**{f"{field_name}__directivo__icontains": termino})
                )

        if not filtros.children:
            return queryset
        return queryset.filter(filtros).distinct()

    def _apply_date_range(self, queryset, model_cls, list_fields):
        fecha_desde_raw = (self.request.GET.get("fecha_desde") or "").strip()
        fecha_hasta_raw = (self.request.GET.get("fecha_hasta") or "").strip()
        if not fecha_desde_raw and not fecha_hasta_raw:
            return queryset

        date_field_name = self._get_date_field_name(model_cls, list_fields)
        if not date_field_name:
            return queryset

        fecha_desde = parse_date(fecha_desde_raw) if fecha_desde_raw else None
        fecha_hasta = parse_date(fecha_hasta_raw) if fecha_hasta_raw else None

        if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
            fecha_desde, fecha_hasta = fecha_hasta, fecha_desde

        if fecha_desde:
            queryset = queryset.filter(**{f"{date_field_name}__gte": fecha_desde})
        if fecha_hasta:
            queryset = queryset.filter(**{f"{date_field_name}__lte": fecha_hasta})

        return queryset

    def get_queryset(self):
        modelo = self.kwargs['modelo']
        _, _, ModelCls, list_fields, *_ = get_pivot(self.request)[modelo]
        queryset = ModelCls.objects.filter(consorcio=consorcio(self.request))
        queryset = self._apply_search(queryset, ModelCls, list_fields)
        queryset = self._apply_date_range(queryset, ModelCls, list_fields)
        return self._apply_ordering(queryset, ModelCls)

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        modelo = self.kwargs['modelo']
        pivot = get_pivot(self.request)
        label, FormCls, ModelCls, list_fields, *rest = pivot[modelo]
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
            "es_federacion": _es_federacion(self.request),
            "q": (self.request.GET.get("q") or "").strip(),
            "fecha_desde": (self.request.GET.get("fecha_desde") or "").strip(),
            "fecha_hasta": (self.request.GET.get("fecha_hasta") or "").strip(),
            "columns": columns,                 # [(field, label), ...]
            "long_field": long_fields[0] if long_fields else None,  # 1er campo largo
            "preview_trunc": PREVIEW_TRUNC,
        })
        return ctx




class Crear_doc(generic.CreateView):
    template_name = 'instancia_doc.html'

    def get_form_class(self):
        return get_pivot(self.request)[self.kwargs['modelo']][1]

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['consorcio'] = consorcio(self.request)
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        modelo = self.kwargs['modelo']
        pivot = get_pivot(self.request)
        ctx["elemento"] = modelo
        ctx["nombre_elemento"] = pivot[modelo][0]
        ctx["es_federacion"] = _es_federacion(self.request)
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
        ModelCls = get_pivot(self.request)[self.kwargs['modelo']][2]
        return ModelCls.objects.get(pk=self.kwargs['pk'], consorcio=consorcio(self.request))



# Create your views here.
