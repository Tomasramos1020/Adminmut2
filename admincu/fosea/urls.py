from django.urls import path
from .views import IndexSolicitud, CrearSolicitudView, EditarSolicitudView, obtener_establecimientos, datos_establecimiento, cotizacion_por_cultivo, aporte_por_zona_cultivo, obtener_subsidio_max

urlpatterns = [
    path('', IndexSolicitud.as_view(), name='fosea'),
    path('crear-solicitud/', CrearSolicitudView.as_view(), name='solicitudes'),
    path('obtener_establecimientos/', obtener_establecimientos, name='obtener_establecimientos'),
    path('ajax/datos_establecimiento/', datos_establecimiento, name='datos_establecimiento'),
    path('cotizacion_por_cultivo/', cotizacion_por_cultivo, name='cotizacion_por_cultivo'),
    path('ajax/aporte_por_zona_cultivo/', aporte_por_zona_cultivo, name='aporte_por_zona_cultivo'),
    path('ajax/obtener_subsidio_max/', obtener_subsidio_max, name='obtener_subsidio_max'),
    path('editar-solicitud/<int:pk>', EditarSolicitudView.as_view(), name='solicitud_editar'),

]