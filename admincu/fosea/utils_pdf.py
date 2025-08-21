# tu_app/utils_pdf.py
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML
from collections import defaultdict
from decimal import Decimal, InvalidOperation

# 👇 ajustá este import según tu app
from arquitectura.models import Cotizacion

# utils_pdf.py
from collections import defaultdict
from decimal import Decimal

def calcular_total_garantia(solicitud):
    """Suma (aporte_total_qq * última cotización) por cultivo para la solicitud dada."""
    lineas = list(_get_lineas(solicitud))

    # Group por cultivo
    by_cultivo = defaultdict(lambda: {
        "aporte_total_qq": Decimal("0"),
        "cultivo_obj": None,
    })
    for l in lineas:
        cultivo_obj = getattr(l, "cultivo", None)
        key = str(cultivo_obj) if cultivo_obj else "—"
        d = by_cultivo[key]
        d["aporte_total_qq"] += _to_decimal(getattr(l, "aporte_total_qq", 0))
        if d["cultivo_obj"] is None:
            d["cultivo_obj"] = cultivo_obj

    # Traer última cotización por cultivo y acumular garantía
    total_garantia = Decimal("0")
    for data in by_cultivo.values():
        if data["cultivo_obj"] is None:
            continue
        valor_cereal = _latest_cotizacion(
            consorcio=solicitud.consorcio,
            cultivo_obj=data["cultivo_obj"],
            hasta_fecha=getattr(solicitud, "fecha", None)
        )
        if valor_cereal:  # si hay cotización
            total_garantia += data["aporte_total_qq"] * valor_cereal

    return total_garantia


def _to_decimal(x, default="0"):
    try:
        return Decimal(str(x or default))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")

def _get_lineas(solicitud):
    rel = getattr(solicitud, 'lineas', None) or getattr(solicitud, 'solicitudlinea_set', None)
    if rel:
        return (rel.select_related('establecimiento', 'cultivo')
                   .order_by('pk')      # orden estable
                   .distinct())         # por si hubo joins
    return []



def _latest_cotizacion(consorcio, cultivo_obj, hasta_fecha=None):
    qs = Cotizacion.objects.filter(consorcio=consorcio, producto=cultivo_obj)
    if hasta_fecha:
        qs = qs.filter(fecha__lte=hasta_fecha)
    c = qs.order_by('-fecha').first()
    return _to_decimal(c.cotizacion) if c else None

def _latest_cotizacion_for(consorcio, cultivo, hasta_fecha=None):
    """
    cultivo puede ser:
      - instancia de Cultivo
      - id (int) de Cultivo
      - nombre (str) del Cultivo -> usa producto__nombre__iexact
    """
    qs = Cotizacion.objects.filter(consorcio=consorcio)
    if hasattr(cultivo, "pk"):           # es instancia
        qs = qs.filter(producto=cultivo)
    elif isinstance(cultivo, int):       # es id
        qs = qs.filter(producto_id=cultivo)
    elif isinstance(cultivo, str):       # es nombre
        qs = qs.filter(producto__nombre__iexact=cultivo)  # <-- usa el campo 'nombre'
    else:
        return None

    if hasta_fecha:
        qs = qs.filter(fecha__lte=hasta_fecha)

    c = qs.order_by('-fecha').first()
    return _to_decimal(c.cotizacion) if c else None


def solicitud_pdf_response(solicitud, request):
    lineas = list(_get_lineas(solicitud))

    vistos = set()
    lineas_unicas = []
    for l in lineas:
        pk = getattr(l, "pk", None)
        if pk in vistos:
            continue
        vistos.add(pk)
        lineas_unicas.append(l)
    lineas = lineas_unicas

    # Totales básicos
    hectareas_reales = sum((_to_decimal(l.hectarea) * (_to_decimal(l.participacion) / Decimal("100"))) for l in lineas)
    suma_aporte_total_qq = sum(_to_decimal(l.aporte_total_qq) for l in lineas)
    valor_soja = _latest_cotizacion_for(
                consorcio=solicitud.consorcio,
                cultivo='Soja',
                hasta_fecha=getattr(solicitud, "fecha", None)
                )
    factor_kg_soja = (valor_soja / Decimal('100')) if valor_soja is not None else None
    valor_hec_real = (factor_kg_soja or Decimal('0')) * _to_decimal(solicitud.suscripcion)         
    total_suscripcion = valor_hec_real * hectareas_reales

    # Establecimientos (únicos)
    est_rows, seen = [], set()
    for l in lineas:
        est = getattr(l, "establecimiento", None)
        if not est:
            continue
        key = getattr(est, "id", None) or getattr(est, "pk", None) or getattr(est, "nombre", None)
        if key in seen:
            continue
        seen.add(key)
        est_rows.append({
            "nombre": getattr(est, "nombre", ""),
            "dpto": getattr(est, "dpto", "") or getattr(est, "departamento", ""),
            "zona": getattr(est, "zona", ""),
            "gps": getattr(est, "gps", ""),
        })

    # Group por cultivo con subtotales
    by_cultivo = defaultdict(lambda: {
        "lineas": [],
        "hectareas_total": Decimal("0"),
        "aporte_total_qq": Decimal("0"),
        "valor_cereal": None,     # se completa desde Cotizacion
        "cultivo_obj": None,      # guardo el obj real para buscar cotización
    })

    for l in lineas:
        cultivo_obj = getattr(l, "cultivo", None)
        cultivo_key = str(cultivo_obj) if cultivo_obj else "—"
        d = by_cultivo[cultivo_key]
        d["lineas"].append(l)
        d["hectareas_total"] += _to_decimal(l.hectarea)
        d["aporte_total_qq"] += _to_decimal(l.aporte_total_qq)
        if d["cultivo_obj"] is None:
            d["cultivo_obj"] = cultivo_obj

    # Completar valor_cereal desde Cotizacion (última para ese consorcio y cultivo)
    for data in by_cultivo.values():
        if data["valor_cereal"] is None and data["cultivo_obj"] is not None:
            vc = _latest_cotizacion(
                consorcio=solicitud.consorcio,
                cultivo_obj=data["cultivo_obj"],
                hasta_fecha=getattr(solicitud, "fecha", None)
            )
            if vc is not None:
                data["valor_cereal"] = vc

    # Resumen final por cultivo
    resumen, total_garantia = [], Decimal("0")
    for cultivo, data in by_cultivo.items():
        valor_cereal = data["valor_cereal"] or Decimal("0")
        garantia = (data["aporte_total_qq"] * valor_cereal) if valor_cereal else Decimal("0")
        total_garantia += garantia
        resumen.append({
            "cultivo": cultivo,
            "hectareas": data["hectareas_total"],
            "aporte_qq": data["aporte_total_qq"],
            "valor_cereal": valor_cereal if valor_cereal else None,
            "garantia": garantia if valor_cereal else None,
        })
    resumen.sort(key=lambda r: r["cultivo"])

    # Lista segura para el template
    cultivos_grouped_items = [(k, v) for k, v in by_cultivo.items()]
    total_hectareas_resumen = sum((r["hectareas"] for r in resumen), Decimal("0"))

    html = render_to_string('pdfs/solicitud.html', {
        'solicitud': solicitud,
        'lineas': lineas,
        'establecimientos': est_rows,
        'cultivos_grouped_items': cultivos_grouped_items,  # ← usar esto en el template
        'resumen': resumen,
        'hectareas_reales': hectareas_reales,
        'suma_aporte_total_qq': suma_aporte_total_qq,
        'total_suscripcion': total_suscripcion,
        'total_garantia': total_garantia,
        'total_hectareas_resumen': total_hectareas_resumen,
        'valor_soja': valor_soja,
        'factor_kg_soja': factor_kg_soja,
        'valor_hec_real': valor_hec_real,
    })
    pdf = HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf()
    resp = HttpResponse(pdf, content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="Solicitud_{solicitud.id}.pdf"'
    return resp


