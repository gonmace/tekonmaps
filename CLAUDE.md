# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Django app ("Tk Redline" / `pti.tekon-rl.cl`) that presents Nextcloud document trees by user role
(`visitante` o una función ITO; ver Roles). Django habla **directamente** con Nextcloud vía WebDAV
(cliente `docs/nextcloud.py`), usando un usuario de servicio con app-password:

```
Browser → Django (AJAX) → docs/nextcloud.py (WebDAV PROPFIND/MKCOL) → Nextcloud → JSON
```

Credenciales en `.env`: `NEXTCLOUD_BASE_URL` (`…/remote.php/dav/files/<usuario>/`),
`NEXTCLOUD_USER`, `NEXTCLOUD_APP_PASSWORD`. Escrituras acotadas del cliente: `mkcol`/`ensure_tree`
(crear carpetas), `upload` (subidas del área ITO), `delete` (solo al aceptar una eliminación
pendiente) y `move` (renombrar sin sobrescribir). La integración previa vía n8n fue retirada.

The infrastructure (settings, Docker, deploy scripts, Makefile) follows the `Dj-Skeleton`
conventions: a single env-driven `core/settings.py` plus a `make`-based workflow.

## Commands

`.env` drives everything (read via `python-decouple`). Without a `.env`, `DEBUG` defaults to
False — local dev needs one (`make setup` generates it; a dev `.env` is already present).

```bash
make setup        # genera .env interactivo (dev/prod, SQLite/PostgreSQL, dominio…)
make install      # pip install -r requirements-dev.txt + tailwind install
make dev          # migrate + tailwind watch (bg) + runserver  → http://localhost:8000
make tailwind     # solo el watcher de Tailwind
make dev-up       # levanta PostgreSQL en Docker SOLO si POSTGRES_DB está en .env (SQLite: nada)

# Django (dev: directo | si DEBUG=False en .env: dentro del contenedor)
make migrate / migrations / superuser / shell / collect
python manage.py test          # tests; una app: python manage.py test docs

# Producción (VPS)
make nginx        # instala nginx.conf (SOLO la primera vez — certbot lo edita después)
make deploy       # git pull + check-ports + docker compose up -d --build
make logs / down
```

CSS: `cd theme/static_src && npm run build` (o `npm run start` para watch). Salida →
`static/css/dist/styles.css`. `db.sqlite3` se respalda/restaura con `./backup-db.sh` /
`./restore-db.sh` (ver `Readme.md`).

## Architecture

### Settings — único y guiado por entorno (`core/settings.py`)
- **Sin `POSTGRES_DB` → SQLite** (default, `db.sqlite3`); **con `POSTGRES_DB` → PostgreSQL**.
- **Sin `EMAIL_HOST` → backend de consola**; con él → SMTP.
- `DEBUG=True` añade `django_browser_reload`, modo Tailwind y CSP relajado para WebSockets.
- `DEBUG=False` activa HSTS, cookies seguras, `SECURE_SSL_REDIRECT` (override con env).
- **Caché:** filesystem (`.cache/django`, TTL 1h). **Sesiones:** base de datos. No usa Redis.
- **django-axes** (brute-force) con `AxesDatabaseHandler` (sin Redis) + `AUTHENTICATION_BACKENDS`.
- **django-csp** permisivo: permite los CDNs (FontAwesome, Google Fonts) y `'unsafe-inline'`
  porque las plantillas usan scripts/estilos inline (toggle de tema, toasts). Endurecer con
  nonces si se requiere.
- `ADMIN_URL` configurable (default `admin/`); usado en `core/urls.py` y `robots.txt`.

### Apps
- **`core/`** — config, `urls.py` (admin, sitemap, robots, raíz), `views.home`, `sitemaps.py`.
- **`accounts/`** — login **por correo** + logout. Sin modelos. `username == email`. Flujo en dos
  pasos (`login_view`/`crear_password_view`): el usuario escribe su correo; si la cuenta aún no
  tiene contraseña usable (recién creada por el superusuario), se le deriva a **crear contraseña**
  (1er ingreso); si ya la tiene, autentica correo+contraseña en la misma pantalla. **No hay
  auto-registro:** un correo desconocido da error. `redirect` de `next` validado contra
  open-redirect. Sigue protegido por django-axes.
- **`panel/`** — panel de gestión **solo para superusuarios** (alternativa al admin de Django), en
  `/panel/`. Sin modelos propios; gestiona los de `docs`/`auth`. Gate:
  `superuser_required = user_passes_test(lambda u: u.is_superuser, login_url='accounts:login')`
  en cada vista. Secciones: **Empresas** (`EmpresaLink` CRUD), **Docs. Finales** (`SiteConfig`
  CRUD), **Docs. ITO** (`DocumentoEsperado` CRUD), **Usuarios** (alta solo con **nombre+correo+rol**
  → `set_unusable_password`; editar nombre/correo/rol/activo, opción de reset o "requerir nueva
  contraseña"; **toggles** en la lista de activo y de **acceso por sección** —Contratista/
  Finales/Seguimiento, `UserProfile.acceso_*`—; borrar — protege al propio usuario y a
  superusuarios), **Accesos** (asignar a cada usuario los **sitios** que puede ver, modelo
  `AccesoSitio`; solo se ofrecen los sitios **ya generados** —con carpeta en el área ITO,
  vía `api_sitios?generados=1` → `seguimiento.sitios_generados()`—, no se crean),
  **Cachés** (ver y limpiar `EstructuraCache`/`SitioCache`/`ProyectoFinalCache`/`SeguimientoCache`
  + `cache.clear()`). El navbar
  (`header.html`) muestra el enlace **Panel** solo si `user.is_superuser`. El admin de Django
  sigue registrado (`docs/admin.py`) como respaldo en `ADMIN_URL`, pero ya no se enlaza en la UI.
- **`docs/`** — la app principal. Todas las vistas son `@login_required` y resuelven el rol con
  `_get_user_rol` (`user.profile.rol`, default `"visitante"`).
- **Roles (un solo campo `UserProfile.rol`):** `visitante` (solo lectura) o una **función ITO**
  (`rol_buscador`/`rol_tk_redline`/`rol_constructor`/`rol_ito`/`rol_ito_hse`/`rol_esp_electrico`/
  `rol_coordinador`). `_es_admin` = `is_superuser or rol != "visitante"` (cualquier función edita/
  sube/confirma y **auto-confirma su rol** en el documento, porque `rol` == el campo `rol_*`).
  `_es_coordinador` = `is_superuser or rol == "rol_coordinador"` (acepta borrados). `link_para_rol`
  da el link de edición a todo lo que no sea visitante. (Antes había `rol` + `rol_ito`; se
  consolidaron en mig. `0037`.)
- **Acceso por sección (`UserProfile.acceso_contratista`/`acceso_finales`/`acceso_seguimiento`):**
  controla la visibilidad de las 3 secciones del navbar. **Restrictivo** (default `False`); el
  superusuario ve todo. Las vistas `index`/`final`/`seguimiento_view` y sus APIs de lectura
  (`api_sitios`/`api_carpetas*`/`api_final_*`/`api_seguimiento`) lo exigen vía
  `_exigir_seccion`/`_gate_api` (403 si no). El navbar (`header.html`) oculta el enlace; tras el
  login, `accounts._landing` aterriza en la primera sección permitida (o `home`).
- **Acceso por sitio (`AccesoSitio`):** ortogonal al rol. El **superusuario ve todo**; cualquier
  otro usuario solo ve los `(empresa, sitio)` que tenga asignados en el Panel (**Accesos**). Sin
  asignaciones **no ve ningún sitio** (restrictivo). Helpers `_sitios_permitidos(user, empresa)` /
  `_empresas_permitidas(user)` (`None` = sin restricción) filtran `api_sitios`, `api_seguimiento`
  (403 si el sitio no está permitido), `index` y `seguimiento_view`.
- **Revisión con observaciones:** las acciones REVISAR/FIRMAR se confirman a mano (modal). El
  revisor puede marcar **"No conforme"** con una nota (`ObservacionDocumento`, vista `observar`) →
  el documento muestra ⚠. Conforme y observación son excluyentes por (doc, rol); subir un archivo
  corregido limpia confirmaciones **y** observaciones.
- **Renombrar según plantilla:** en la lista de archivos de un documento (botón "ver" de la
  columna central), la varita —solo en documentos **con `codigo`**— abre un modal con el
  nombre que dicta la plantilla
  (`DocumentoEsperado.codigo` con el código de sitio real y, si trae `(XX00)`, correlativo+fecha
  — misma sugerencia que el modal de subida), editable. Vista `renombrar_archivo` →
  `seguimiento.renombrar_archivo` → `nextcloud.move` (MOVE sin sobrescribir, mismo directorio);
  los registros por path (`AsignacionArchivo`/`EliminacionPendiente`/`ArchivoOculto`) siguen al
  archivo. No toca confirmaciones/observaciones (el contenido no cambió).
- **Borrado en dos pasos:** el botón eliminar **marca** el archivo (`EliminacionPendiente`, X
  tachada) vía `eliminar_archivo`; solo Coordinador/superusuario **aceptan** (`aceptar_eliminacion`
  → borra de Nextcloud) o **rechazan** (`rechazar_eliminacion`).

### docs — flujo de datos
- **Empresas:** `companies.json` → `docs/company_loader.py` (`Company` dataclasses). Los links
  de Nextcloud por empresa se superponen desde el modelo `EmpresaLink` (`link_admin`/
  `link_visitante`), elegidos por rol con `link_para_rol(rol)`. `SiteConfig` guarda los links de
  "Docs. Finales".
- **Acceso a Nextcloud** (`docs/nextcloud.py`, WebDAV): `list_folder` (lista items, reemplaza al
  antiguo `_fetch_items`), `tree` (recorrido recursivo Depth:1 paralelo), `mkcol`/`ensure_tree`
  (crear carpetas). `docs/views.py` mantiene los helpers `_fetch_items`/`_fetch_deep` como adaptadores
  sobre el cliente, conservando el formato y la caché.
- **Caché por timestamp** (clave de rendimiento): `EstructuraCache`, `SitioCache`,
  `ProyectoFinalCache` guardan el JSON traído + el `lastModified` de Nextcloud
  (`ultima_actualizacion_ts`). Cada request obtiene el max-mtime actual (`_get_folder_lastmod`) y
  solo re-fetchea si difiere. Solo se cachea si hay datos reales.

### Seguimiento ITO (completitud de documentos)
- **Lista maestra:** modelo `DocumentoEsperado` (etapa/actividad/nombre/orden), sembrado con
  `python manage.py seed_documentos` desde `docs/fixtures/documentos_ito.json` (exportado de
  `ESTRUCTURA DOCUMENTOS.xlsx`, filas donde el ITO es responsable). CRUD en el Panel (**Docs. ITO**).
- **Sin pre-generación de estructura** (criterio "mostrar por referencia, no copiar", estilo `ln`):
  el área `/20-ITO_SEGUIMIENTO/<sitio>/` **no se pre-crea**. Sus carpetas nacen **bajo demanda** al
  subir (`subir_documento`/`subir_multimedia` → `ensure_tree`). Los archivos de constructora viven en
  sus carpetas `/20*` originales y se **muestran por referencia** (su `path` original); nunca se
  copian ni se mueven. Asignar un archivo a un documento es solo un registro en BD
  (`AsignacionArchivo`), no toca Nextcloud.
- **Dónde caen las subidas:** un documento subido cae en `/20-ITO_SEGUIMIENTO/<sitio>/<ETAPA>/[CARPETA]`
  (`DocumentoEsperado.carpeta_contenedora()`, sueltos en la etapa, sin subcarpeta por documento); la
  multimedia en `/20-ITO_SEGUIMIENTO/<sitio>/05_SEGUIMIENTO/<Imágenes|Videos>` (`media_base`).
- **Completitud:** `estado_sitio(empresa, sitio)` escanea (PROPFIND, paralelo) todas las carpetas
  `/20*` de constructora (por código de sitio) **más** el área ITO, asigna cada archivo a un documento
  (por `AsignacionArchivo` o `score_match`) y lo marca *presente* si tiene ≥1 archivo del tipo
  esperado. Tablero en `/docs/seguimiento/` (enlace **Seguimiento ITO** del navbar). Caché
  `SeguimientoCache` (invalidación por timestamp).
- **Fast-path (carga rápida):** `estado_sitio` guarda la *fecha* (mtime, `folder_lastmod`) de **la
  carpeta del sitio dentro de cada root `/20*` + el área ITO**, junto con la lista `archivos`
  escaneada (clave `seg:fp:*`, TTL 6 h vía `_set_fp`). En la siguiente carga consulta solo esas
  fechas (1-2 PROPFINDs chicos); si no cambiaron, **reconstruye `datos`** (`_ensamblar_datos`) desde
  los `archivos` cacheados + el estado **actual** de la BD — sin escaneo profundo (~1.5 s vs ~57 s del
  escaneo frío). El fp **se renueva en cada uso** (un sitio activo no expira) y **se guarda aunque
  falle alguna fuente** (un root `/20*` flaky no bloquea el cacheo). Cambios que **no tocan Nextcloud**
  (editar/confirmar/necesario/asignar) se reflejan al instante. `?refresh=1` y **Refrescar carpeta**
  saltan el fast-path. (Ojo: correr el suite de tests hace `cache.clear()` sobre la misma caché de
  filesystem → la siguiente carga real será fría una vez.)
- **Dos invalidaciones:** `invalidar_cache` (cambió Nextcloud: subir/eliminar archivo) borra `datos`
  **y** la firma/archivos del fast-path → re-escanea. `invalidar_datos` (cambió solo la BD:
  confirmar/necesario/asignar) borra solo `datos` y **conserva** el fast-path → reconstruye sin
  escanear. La edición de `DocumentoEsperado` en el Panel (`panel._invalidar_seguimiento`) también
  conserva el fast-path.

### API endpoints (bajo `/docs/`, `@login_required`, JSON)
| Endpoint | Para qué |
|---|---|
| `api/sitios/` | Carpetas raíz (sitios) de una empresa |
| `api/carpetas/` | Carpetas; `?structure_only=1` = solo nombres (cache `EstructuraCache`) |
| `api/carpetas/archivos/` | Subcarpetas + conteo por sitio (cache `SitioCache`) |
| `api/final/tree/` | Árbol bajo `/20-PTI SP` (`FINAL_ROOT_PATH`) |
| `api/final/archivos/` | Árbol + conteo por proyecto (cache `ProyectoFinalCache`) |
| `api/seguimiento/` | Completitud de documentos del ITO por sitio (cache `SeguimientoCache`) |

## Frontend / CSS
- **Tailwind v4 + DaisyUI v5** vía `django-tailwind` (app `theme`). Editas
  `theme/static_src/src/styles.css`; compila a `static/css/dist/styles.css`. `base.html` lo
  carga con `{% tailwind_css %}` (`{% load tailwind_tags %}`).
- Design system (botones, inputs, temas light/dark, toasts) documentado en `ESTILOS.md`.
- **Estilo de controles (Cupertino/iOS), todo con DaisyUI + tokens del tema** en `styles.css`:
  - **Botones** (`.btn`): sin borde, **cápsula** (`border-radius: 9999px`), etiqueta **semibold**,
    `:active` → `scale(0.96)`, `:focus-visible` → anillo del color del botón. El color por
    variante (`.btn-info`, etc.) usa fondo translúcido + texto a color completo. `.btn-circle`
    conserva su forma.
  - **Inputs** (`.input/.textarea/.select/.file-input` y variantes `-bordered`): fondo tenue
    (`base-200`), sin borde, `border-radius: 0.75rem`; al foco, anillo `primary` + fondo `base-100`.
- **Logo por tema:** `logo-tk-rl.png` (rojo+negro, light) y `logo-tk-rl-dark.png` (rojo+blanco,
  generado con Pillow). Se incluyen ambos `<img>` (`.logo-light` / `.logo-dark`) y se conmutan
  por `[data-theme]` en `styles.css`.
- **Al agregar apps Django:** añadir a `INSTALLED_APPS` y un `@source "../../../<app>"` en
  `theme/static_src/src/styles.css` para que Tailwind escanee sus templates.

## Convenciones
- Código, comentarios y UI en español.
- `db.sqlite3` **no** se versiona (está en `.gitignore`); cada entorno tiene el suyo. Respaldo/
  restauración con `./backup-db.sh` / `./restore-db.sh`.
- `Readme.md` aún describe el flujo previo (split settings, `requirements/`); la fuente de verdad
  para comandos es este archivo y el `Makefile`.
