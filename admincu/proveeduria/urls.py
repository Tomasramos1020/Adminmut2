from django.urls import path
from .views import *

urlpatterns = [
	path('', Index.as_view(), name='proveeduria'),

	#facturador
	path('crear-solicitud/', CrearOperacionView.as_view(), name='solicitudes_proveeduria'),
	path('obtener_sucursales/', obtener_sucursales, name='obtener_sucursales'),
	path('obtener-precio-producto/', obtener_precio_producto, name='obtener_precio_producto'),

	path('crear-compra/', CrearCompraView.as_view(), name='compras-proveeduria'),

	path('remitos/nuevo/', CrearRemitoView.as_view(), name='remitos-crear'),
	path('remitos/', RegistroRemitos.as_view(), name='remitos-registro'),
	path('remitos/<int:pk>/pdf/', remito_pdf, name='remito-pdf'),
	path('remitos/<int:pk>/anular/', remito_anular, name='remito-anular'),
	path('proveeduria/precio-producto/', obtener_precio_producto, name='obtener_precio_producto_remito'),

	path('ajustes/nuevo/', CrearAjusteView.as_view(), name='ajuste-crear'),
	path('ajustes/', RegistroAjustes.as_view(), name='registro-ajustes'),
	path('ajustes/<int:pk>/pdf/', ajuste_pdf, name='ajuste-pdf'),
	path('ajustes/<int:pk>/anular/', ajuste_anular, name='ajuste-anular'),

	path('<str:modelo>/', Listado.as_view(), name='elemento'),
	path('<str:modelo>/nuevo', Crear.as_view(), name='crear_proveeduria'),
	path('<str:modelo>/<int:pk>/editar/', Instancia.as_view(), name='instancia_proveeduria'),

]
