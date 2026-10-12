"""Resumen por correo de pendientes vencidos y próximos de Seguimiento.

Pensado para un cron diario, p. ej.::

    0 7 * * * cd /ruta/proyecto && .venv/bin/python manage.py enviar_recordatorios

Cada destinatario recibe **un** correo con sus pendientes (los suyos como responsable; los
que no tienen usuario responsable van a los ITO asignados al sitio). Sin pendientes que
avisar no se envía nada.
"""
from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from proyectos import servicios
from proyectos.models import Pendiente


def _destinatarios(p):
    """Usuarios activos con correo a quienes corresponde avisar de ``p``."""
    if p.responsable_user_id:
        users = [p.responsable_user]
    else:
        proy = p.etapa.proyecto
        users = list(servicios.itos_asignados(proy.empresa, proy.sitio))
    return [u for u in users if u and u.is_active and (u.email or "").strip()]


class Command(BaseCommand):
    help = "Envía a cada responsable/ITO el resumen de pendientes vencidos y próximos."

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=2,
                            help="Avisar también los que vencen en los próximos N días (def. 2).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Muestra qué se enviaría, sin enviar correos.")

    def handle(self, *args, dias, dry_run, **opts):
        hoy = timezone.localdate()
        limite = hoy + timedelta(days=dias)
        qs = (Pendiente.objects
              .filter(eliminado_en__isnull=True, hecho=False, fecha__isnull=False,
                      fecha__lte=limite, etapa__proyecto__activo=True)
              .select_related("etapa__proyecto", "responsable_user")
              .order_by("fecha", "hora", "id"))
        por_usuario = defaultdict(list)
        for p in qs:
            for u in _destinatarios(p):
                por_usuario[u].append(p)

        enviados = 0
        for u, lista in sorted(por_usuario.items(), key=lambda kv: kv[0].email):
            vencidos = [p for p in lista if p.fecha < hoy]
            cuerpo = self._cuerpo(u, lista, vencidos, hoy)
            asunto = f"Seguimiento: {len(lista)} pendiente(s)" + (
                f", {len(vencidos)} vencido(s)" if vencidos else "")
            if dry_run:
                self.stdout.write(f"→ {u.email}: {asunto}")
            else:
                send_mail(asunto, cuerpo, None, [u.email], fail_silently=False)
            enviados += 1
        self.stdout.write(self.style.SUCCESS(
            f"{'Simulados' if dry_run else 'Enviados'}: {enviados} correo(s)."))

    def _cuerpo(self, u, lista, vencidos, hoy):
        def linea(p):
            hora = f" {p.hora.strftime('%H:%M')}" if p.hora else ""
            alta = " [ALTA]" if p.prioridad == "A" else ""
            return (f"  - {p.fecha.strftime('%d-%m-%Y')}{hora} · {p.titulo}{alta}\n"
                    f"      {p.etapa.proyecto.sitio} · {p.etapa.get_etapa_display()}")
        partes = [f"Hola {servicios.nombre_usuario(u)},", ""]
        if vencidos:
            partes += ["VENCIDOS"] + [linea(p) for p in vencidos] + [""]
        proximos = [p for p in lista if p.fecha >= hoy]
        if proximos:
            partes += ["PRÓXIMOS"] + [linea(p) for p in proximos] + [""]
        url = getattr(settings, "SITE_URL", "").rstrip("/")
        if url:
            partes += [f"Ver en Seguimiento: {url}/seguimiento/", ""]
        return "\n".join(partes)
