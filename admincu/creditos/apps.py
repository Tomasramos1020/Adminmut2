from __future__ import unicode_literals

from django.apps import AppConfig


class CreditosConfig(AppConfig):
    name = 'creditos'

    def ready(self):
        # Ejecuta el patch de AFIP al iniciar Django
        from . import afip_patch