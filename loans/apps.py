from django.apps import AppConfig


class LoansConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "loans"

    def ready(self):
        from . import checks, security  # noqa: F401  (registers launch checks and the failed-login counter)
