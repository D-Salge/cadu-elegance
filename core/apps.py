from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        # ADICIONE ESTA LINHA: Garante que o Django carrega os nossos sinais
        import core.signals