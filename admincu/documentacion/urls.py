from django.urls import path
from .views import Index_doc, Listado_doc, Crear_doc, Instancia_doc

urlpatterns = [
    path('', Index_doc.as_view(), name='documentacion'),
    path('<str:modelo>/', Listado_doc.as_view(), name='doc_listado'),
    path('<str:modelo>/nuevo', Crear_doc.as_view(), name='doc_crear'),
    path('<str:modelo>/<int:pk>/editar/', Instancia_doc.as_view(), name='doc_instancia'),
]


