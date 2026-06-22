# Pendientes de producción (no aplicados en código)

Auditoría pre-producción (2026-06-22). Estos puntos **no se tocaron en código** —por riesgo de
romper el deploy o por estar fuera del alcance acordado (P2)— y se aplican manualmente.

## Acción manual obligatoria (P0) — rotar credenciales filtradas

`.env.example` tenía credenciales **reales** en la historia de git (commit `3cf7841`). Ya se
reemplazó por placeholders, pero las viejas siguen en commits pasados → **deben rotarse**:

1. **Nextcloud**: revocar el app-password de `svc-seguimiento` y generar uno nuevo → `.env` del VPS.
2. **PostgreSQL**: cambiar `DATABASE_PASSWORD`/`POSTGRES_PASSWORD` → `.env` del VPS y la BD.
3. **Django**: nuevo `SECRET_KEY`
   (`python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'`).
4. `chmod 600 .env` en el VPS (estaba en `644`).
5. (Opcional pero recomendado) purgar los secretos de la historia con `git filter-repo` **después**
   de rotar.

Verificar `.env` de producción: `DEBUG=False`, `ALLOWED_HOSTS=pti.tekon-rl.cl`, `POSTGRES_DB`
definido (no SQLite en prod), HTTPS activo.

## nginx — NO modificar `nginx.conf` ni `nginx-deploy.sh`

Por preferencia explícita, la config de nginx no se edita automáticamente (la gestiona certbot y
ajustes manuales). Pendientes a aplicar a mano:

- **TLS/certbot**: confirmar `sudo certbot --nginx -d pti.tekon-rl.cl` y la redirección 80→443.
- **Rate limiting**: `limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;` para
  `/accounts/login` y una zona para los `api_*` (complementa django-axes).
- **Headers defensivos**: `add_header X-Content-Type-Options nosniff;`,
  `add_header X-Frame-Options DENY;`, `add_header Referrer-Policy strict-origin-when-cross-origin;`.
- **`client_max_body_size`**: hoy `20M`. La app ahora limita subidas a 100 MB
  (`MAX_UPLOAD_BYTES` en `docs/views.py`); alinear ambos valores si se quieren archivos grandes.

## Contenedor no-root (P1, diferido por riesgo)

El contenedor Django corre como **root**. Migrar a usuario no-root es deseable, pero los bind-mounts
del host (`./staticfiles`, `./media`, `./db.sqlite3` en `docker-compose.yml`) son propiedad de root,
así que un `USER app` directo rompería `collectstatic`, las subidas y la caché de filesystem.

Forma segura (pendiente): entrypoint que arranque como root, haga `chown` de los volúmenes y baje a
un usuario sin privilegios con `gosu`/`su-exec` antes de `exec gunicorn`. Requiere instalar `gosu`
en la imagen y probar en staging para no romper permisos del deploy en vivo.

Ya aplicado y seguro: `HEALTHCHECK` en el `Dockerfile` y `--timeout/--max-requests` en gunicorn.

## P2 — Endurecimientos recomendados (follow-up, no bloquean)

- **Cookies** (`core/settings.py`, junto a `*_COOKIE_SECURE`): añadir
  `SESSION_COOKIE_HTTPONLY=True`, `CSRF_COOKIE_HTTPONLY=True`,
  `SESSION_COOKIE_SAMESITE='Lax'`, `CSRF_COOKIE_SAMESITE='Strict'`.
- **CSP** (`settings.py`): hoy `'unsafe-inline'` en script/style; migrar a **nonces** para endurecer.
- **ADMINS** (`settings.py`): reemplazar `admin@example.com` por un correo real y configurar
  `EMAIL_HOST` para recibir errores 500 en producción.
- **`Content-Disposition`** (`docs/views.py`): el `filename` viene de la ruta; sanear CR/LF o usar
  `FileResponse` (defensa en profundidad).
- **requirements.txt**: añadir cotas superiores a paquetes críticos y correr `pip-audit` en CI.
