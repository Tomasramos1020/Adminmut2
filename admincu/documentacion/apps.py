from django.apps import AppConfig

class DocumentacionConfig(AppConfig):
    name = 'documentacion'

    def ready(self):
        from . import signals
