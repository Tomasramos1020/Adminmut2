from django.urls import path
from .views import *

urlpatterns = [
    path('', IndexSolicitud.as_view(), name='fosea'),
    path('crear-solicitud/', CrearSolicitudView.as_view(), name='solicitudes'),
    path('obtener_establecimientos/', obtener_establecimientos, name='obtener_establecimientos'),
    path('ajax/datos_establecimiento/', datos_establecimiento, name='datos_establecimiento'),
    path('cotizacion_por_cultivo/', cotizacion_por_cultivo, name='cotizacion_por_cultivo'),
    path('ajax/aporte_por_zona_cultivo/', aporte_por_zona_cultivo, name='aporte_por_zona_cultivo'),
    path('ajax/obtener_subsidio_max/', obtener_subsidio_max, name='obtener_subsidio_max'),
    path('editar-solicitud/<int:pk>', EditarSolicitudView.as_view(), name='solicitud_editar'),
    path('solicitud/<int:pk>/pagare/', PagareSolicitudPDFView.as_view(), name='pagare_solicitud'),
    path('crear-cotizacion/', CrearCotizacionView.as_view(), name='crear_cotizacion'),
    path('parametros-zona-cultivo/', parametros_zona_cultivo, name='parametros_zona_cultivo'),
    path('establecimientos/nuevo/', establecimiento_modal, name='establecimiento_modal'),
    path('solicitud/<int:pk>/pdf/', solicitud_pdf, name='solicitud_pdf'),
    path('registro/', Registro.as_view(), name='registro-solicitudes'),    
    #Siniestros
    path('fosea/siniestros/nuevo/', CrearSiniestroView.as_view(), name='fosea-siniestros-nuevo'),
    path('fosea/ajax/franquicia/', franquicia_por_zona_cultivo, name='franquicia_por_zona_cultivo'),
    path('fosea/ajax/establecimientos_filtrados/', establecimientos_filtrados, name='establecimientos_filtrados'),
    path('fosea/siniestros/registro/', RegistroSiniestros.as_view(), name='registro_siniestros'),
    path('fosea/siniestros/<int:pk>/editar/', EditarSiniestroView.as_view(), name='siniestro_editar'),
    path('cobertura_por_cultivo/', cobertura_por_cultivo, name='cobertura_por_cultivo'),
    #Resumenes

]