from django.apps import AppConfig


class ProveeduriaConfig(AppConfig):
    name = 'proveeduria'

    def ready(self):
        from . import signals