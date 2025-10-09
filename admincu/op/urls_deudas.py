from django.urls import path
from .views_deud import *


urlpatterns = [
    path('', deud_index, name='deudas'),

    path('registro/', Registro.as_view(), name='registro de deudas'),

    path('nuevo/', deud_nuevo, name='deud_nuevo'),
    path('vinculaciones/', deud_vinculaciones, name='deud_vinculaciones'),
    path('confirm/<int:pk>/', deud_confirm, name='deud_confirm'),
    path('cancelar/<int:pk>/', deud_eliminar, name='deud_eliminar'),
    path('vincular-pago/<int:pk>/', deud_vincular_pago, name='deud_vincular_pago'),
    path('<int:pk>/', deud_ver, name='deud_ver'),
    path('eliminar_deuda/<int:pk>/', eliminar_deuda, name='eliminar_deuda'),

    # === NC a Proveedor ===
    path('nc-proveedor/', NCProveedorView.as_view(), name='nc-proveedor-crear'),
    path('ajax/deudas-por-acreedor/', deudas_por_acreedor, name='ajax-deudas-por-acreedor'),
    path('ajax/deuda-es-proveeduria/', deuda_es_proveeduria_ajax, name='ajax-deuda-es-proveeduria'),
    path('ajax/nc-disponible-producto/', disponible_producto_nc_ajax, name='ajax-nc-disponible-producto'),
    path('ajax/nc-lineas-deuda/', nc_lineas_deuda_ajax, name='ajax-nc-lineas-deuda'),

    path('registro_nc_proveedores/', RegistroNCProveedor.as_view(), name='registro-nc-proveedores'),
    path('registro_nc_proveedores_detalle/<int:pk>/', NCProveedorDetalleView.as_view(), name='nc-proveedor-detalle'),

]
