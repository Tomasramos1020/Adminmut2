from django.urls import path
from .views import *

urlpatterns = [
	path('', Index.as_view(), name='proveeduria'),
	path('<str:modelo>/', Listado.as_view(), name='elemento'),
	path('<str:modelo>/nuevo', Crear.as_view(), name='crear_proveeduria'),
	path('<str:modelo>/<int:pk>/editar/', Instancia.as_view(), name='instancia_proveeduria'),



]
