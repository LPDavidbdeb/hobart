from django.apps import AppConfig

class AddressConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'address'

    def ready(self):
        import address.signals # This line imports and registers the signals
