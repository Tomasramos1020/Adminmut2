from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
	EstadoCuentaViewSet,
	SocioViewSet,
	SocioSolidariaViewSet
)

router = DefaultRouter()
router.register(r'estado_cuenta', EstadoCuentaViewSet, basename='estado-cuenta')
router.register(r'sociosOK', SocioViewSet, basename='socios-ok')
router.register(r'sociosSolidaria', SocioSolidariaViewSet, basename='socios-solidaria')
urlpatterns = [
	path('', include(router.urls))
]