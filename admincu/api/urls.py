from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
	EstadoCuentaViewSet,
	SocioViewSet,
)

router = DefaultRouter()
router.register(r'estado_cuenta', EstadoCuentaViewSet, basename='api')
router.register(r'sociosOK', SocioViewSet, basename='api')

urlpatterns = [
	path('', include(router.urls))
]