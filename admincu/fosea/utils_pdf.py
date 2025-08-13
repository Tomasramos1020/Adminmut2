# tu_app/utils_pdf.py
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML

def _get_lineas(solicitud):
    rel = getattr(solicitud, 'lineas', None) or getattr(solicitud, 'solicitudlinea_set', None)
    if rel:
        try:
            return rel.select_related('establecimiento', 'cultivo').all()
        except Exception:
            return rel.all()
    return []

def solicitud_pdf_response(solicitud, request):
    lineas = _get_lineas(solicitud)  # <--- ahora sí se “accede” a la función

    hectareas_reales = sum((float(l.hectarea or 0)) * (float(l.participacion or 0)/100) for l in lineas)
    suma_aporte_total_qq = sum(float(l.aporte_total_qq or 0) for l in lineas)
    total_suscripcion = float(solicitud.suscripcion or 0) * hectareas_reales

    html = render_to_string('pdfs/solicitud.html', {
        'solicitud': solicitud,
        'lineas': lineas,
        'hectareas_reales': hectareas_reales,
        'suma_aporte_total_qq': suma_aporte_total_qq,
        'total_suscripcion': total_suscripcion,
    })
    pdf = HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf()
    resp = HttpResponse(pdf, content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="Solicitud_{solicitud.id}.pdf"'
    return resp
