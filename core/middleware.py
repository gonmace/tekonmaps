"""Middleware de zona horaria por usuario.

Activa la zona horaria del visitante (la del navegador, guardada en la cookie ``tz`` por
un script en ``base.html``) para que todas las fechas/horas se rendericen en su hora local
—típicamente America/Santiago (Chile) o America/La_Paz (Bolivia)—. Sin cookie válida, se
usa ``settings.TIME_ZONE`` como fallback.
"""
from zoneinfo import ZoneInfo, available_timezones

from django.utils import timezone

_VALID_TZS = available_timezones()


class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tzname = request.COOKIES.get("tz")
        if tzname and tzname in _VALID_TZS:
            timezone.activate(ZoneInfo(tzname))
        else:
            timezone.deactivate()  # usa settings.TIME_ZONE
        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()
