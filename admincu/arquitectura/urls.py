from django.urls import path
from .views import *

urlpatterns = [
	path('', Index.as_view(), name='parametros'),
	path('puntosdeventa/', arq_puntos, name='puntosdeventa'),

	path('codigo/<int:pk>/', PDFCodigo.as_view(), name='codigo-socio'),

	path("afip-datos/", consultar_padron_ajax, name="afip-datos"),

	path('test-a13/<int:cuit>/', consultar_padron_test, name='test-a13'),

	path('<str:modelo>/', Listado.as_view(), name='parametro'),
	path('<str:modelo>/nuevo/', Crear.as_view(), name='crear'),
	path('<str:modelo>/<int:pk>/editar/', Instancia.as_view(), name='instancia'),
	path('<str:modelo>/<int:pk>/finalizar/', Finalizar.as_view(), name='finalizar-parametro'),
	path('<str:modelo>/<int:pk>/reactivar/', Reactivar.as_view(), name='reactivar-parametro'),
	path('<str:modelo>/importacion/', SociosImportacionWizard.as_view(), name='importacion'),
	path('<str:modelo>/exportacion/', ExportacionInaes.as_view(), name='exportacion-inaes'),
	path('parametros/socios/exportar-txt/', exportar_socios_txt, name='exportar_socios_txt'),


]
