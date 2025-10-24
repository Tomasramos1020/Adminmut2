from django.urls import path
from .views import Index, CrearOperacionView, obtener_sucursales, obtener_precio_producto, \
    CrearCompraView, CrearRemitoView, RegistroRemitos, remito_pdf, remito_anular, \
    NCProveeduriaCreateView, facturas_por_socio, CrearAjusteView, RegistroAjustes, \
    ajuste_pdf, ajuste_anular, Listado, Crear, Instancia, ModuloListView, ModuloCreateView, ModuloUpdateView

urlpatterns = [
	path('', Index.as_view(), name='proveeduria'),

	# --- MÓDULOS
	path('modulos/', ModuloListView.as_view(), name='modulos-index'),
	path('modulos/nuevo/', ModuloCreateView.as_view(), name='modulos-create'),
	path('modulos/<int:pk>/', ModuloUpdateView.as_view(), name='modulos-update'),
	
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

	path('proveeduria/nc/crear/', NCProveeduriaCreateView.as_view(), name='proveeduria-nc-crear'),
	path('ajax/facturas-por-socio/', facturas_por_socio, name='ajax-facturas-por-socio'),


	path('ajustes/nuevo/', CrearAjusteView.as_view(), name='ajuste-crear'),
	path('ajustes/', RegistroAjustes.as_view(), name='registro-ajustes'),
	path('ajustes/<int:pk>/pdf/', ajuste_pdf, name='ajuste-pdf'),
	path('ajustes/<int:pk>/anular/', ajuste_anular, name='ajuste-anular'),

	path('<str:modelo>/', Listado.as_view(), name='elemento'),
	path('<str:modelo>/nuevo', Crear.as_view(), name='crear_proveeduria'),
	path('<str:modelo>/<int:pk>/editar/', Instancia.as_view(), name='instancia_proveeduria'),



]
