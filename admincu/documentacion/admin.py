from django.contrib import admin
from import_export import fields, resources
from import_export.admin import ImportExportModelAdmin
from import_export.widgets import ForeignKeyWidget

from arquitectura.models import Consorcio
from .models import ActaConsejo


class ActaConsejoResource(resources.ModelResource):
    consorcio = fields.Field(
        column_name="consorcio",
        attribute="consorcio",
        widget=ForeignKeyWidget(Consorcio, "id"),
    )

    class Meta:
        model = ActaConsejo
        fields = (
            "consorcio",
            "nombre",
            "fecha",
            "numero",
            "foja",
            "contenido",
            "descripcion",
            "firma",
            "transcripcion",
        )
        import_id_fields = ("consorcio", "nombre", "fecha", "numero", "foja")
        skip_unchanged = True
        report_skipped = True


@admin.register(ActaConsejo)
class ActaConsejoAdmin(ImportExportModelAdmin):
    resource_class = ActaConsejoResource
    list_display = ("nombre", "consorcio", "fecha", "numero", "foja", "firma", "transcripcion")
    list_filter = ("consorcio", "firma", "transcripcion")
    search_fields = ("nombre", "descripcion")
