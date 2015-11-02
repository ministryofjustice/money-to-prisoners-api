from django.conf import settings


def app_environment(request):
    return {
        'ENVIRONMENT': settings.ENVIRONMENT,
        'DEBUG': settings.DEBUG,
    }
