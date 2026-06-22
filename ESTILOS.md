# Sistema de estilos — Guía reutilizable

Guía portable para replicar este sistema de diseño (botones, temas light/dark, componentes y
toasts) en **cualquier proyecto Django con Tailwind CSS v4 + DaisyUI v5**. Está basado en el
sistema usado por `pti.tekon-rl.cl` / `reg.tekon-rl.cl` / `wom`.

---

## 1. Stack y build

- **Tailwind CSS v4** + **DaisyUI v5** (sin `tailwind.config.js`; todo se configura en el CSS de entrada).
- **FontAwesome 6** (CDN) para iconos.
- **Fuente Nunito** (Google Fonts CDN).
- Integrado con **`django-tailwind`** (app `theme`) y compilado con **`@tailwindcss/cli`**.

### Estructura (este proyecto)

```
theme/static_src/
  src/styles.css       # entrada (temas + componentes)  ← editas aquí
  package.json
static/
  css/dist/styles.css  # salida compilada               ← se genera (gitignored)
  js/components/alert-component.js
templates/base.html    # carga el CSS con {% tailwind_css %}
```

### package.json (build con @tailwindcss/cli)

```json
{
  "scripts": {
    "start": "npx @tailwindcss/cli -i ./src/styles.css -o ../../static/css/dist/styles.css --watch",
    "build": "npx @tailwindcss/cli -i ./src/styles.css -o ../../static/css/dist/styles.css --minify"
  },
  "dependencies": {
    "@tailwindcss/cli": "^4.0.0",
    "daisyui": "^5.0.0",
    "tailwindcss": "^4.0.0"
  }
}
```

En `base.html`, cargar el CSS con la etiqueta de django-tailwind (resuelve
`TAILWIND_CSS_PATH = "css/dist/styles.css"`):

```django
{% load static tailwind_tags %}
{% tailwind_css %}
```

Comandos:

```bash
cd theme/static_src && npm install
npm run build        # producción (minificado)
npm run start        # watch en desarrollo   (o: python manage.py tailwind start / make tailwind)
```

> Los plugins `@tailwindcss/forms` y `@tailwindcss/typography` son **opcionales**. Si los quieres,
> instálalos (`npm i -D @tailwindcss/forms @tailwindcss/typography`) y añade en `input.css`:
> `@plugin "@tailwindcss/forms" { strategy: class; }` y `@plugin "@tailwindcss/typography";`.

---

## 2. Cabecera de `input.css`

```css
@import "tailwindcss";
@plugin "daisyui" {
  themes: light --default, dark;
  logs: false;
}

/* Escanea tus plantillas para detectar clases usadas */
@source "../templates/**/*.html";
@source "../<tu_app>/**/*.html";

/* Clases inyectadas por JS (el scanner no las ve en .html) → decláralas */
@source inline("toast toast-top toast-end z-[9999]");
@source inline("alert alert-success alert-error alert-warning alert-info");
@source inline("btn btn-sm btn-primary btn-success btn-error btn-warning btn-info btn-edit btn-delete btn-view btn-save btn-cancel");
@source inline("text-edit text-delete text-view");

/* Elementos nativos (select/input) en modo oscuro */
[data-theme="dark"] { color-scheme: dark; }
```

---

## 3. Temas light/dark (paleta completa)

Copia ambos bloques tal cual. Cambian la marca completa; el resto del sistema (botones, alerts)
deriva sus colores de estas variables, así que **light y dark salen gratis**.

```css
/* ─── LIGHT ─────────────────────────────────────────────── */
@plugin "daisyui/theme" {
  name: "light";
  default: true;
  prefersdark: false;
  color-scheme: light;
  --color-base-100: #ffffff;
  --color-base-200: #f2f2f7;
  --color-base-300: #e5e5ea;
  --color-base-content: #1c1c1e;
  --color-primary: #e60000;   --color-primary-content: #ffffff;
  --color-secondary: #4a4d4e; --color-secondary-content: #ffffff;
  --color-accent: #f59e0b;    --color-accent-content: #1c1c1e;
  --color-neutral: #3a3a3c;   --color-neutral-content: #ffffff;
  --color-info: #0284c7;      --color-info-content: #ffffff;
  --color-success: #16a34a;   --color-success-content: #ffffff;
  --color-warning: #eab308;   --color-warning-content: #1c1c1e;
  --color-error: #b91c1c;     --color-error-content: #ffffff;
  --color-edit:   #d97706;    --color-edit-content:   #fff;
  --color-delete: #cc0000;    --color-delete-content: #fff;
  --color-view:   #2563eb;    --color-view-content:   #fff;
  --radius-selector: 0.5rem; --radius-field: 0.625rem;
  --radius-box: 0.875rem;    --radius-badge: 0.375rem;
}

/* ─── DARK ──────────────────────────────────────────────── */
@plugin "daisyui/theme" {
  name: "dark";
  default: false;
  prefersdark: true;
  color-scheme: dark;
  --color-base-100: #1c1c1e;
  --color-base-200: #2c2c2e;
  --color-base-300: #3a3a3c;
  --color-base-content: #f2f2f7;
  --color-primary: #ff3b30;   --color-primary-content: #ffffff;
  --color-secondary: #8e8e93; --color-secondary-content: #ffffff;
  --color-accent: #fcd34d;    --color-accent-content: #1c1c1e;
  --color-neutral: #d1d1d6;   --color-neutral-content: #1c1c1e;
  --color-info: #38bdf8;      --color-info-content: #ffffff;
  --color-success: #34d399;   --color-success-content: #ffffff;
  --color-warning: #fde047;   --color-warning-content: #1c1c1e;
  --color-error: #f87171;     --color-error-content: #1c1c1e;
  --color-edit:   #fbbf24;    --color-edit-content:   #1c1c1e;
  --color-delete: #ff4040;    --color-delete-content: #fff;
  --color-view:   #60a5fa;    --color-view-content:   #fff;
  --radius-selector: 0.5rem; --radius-field: 0.625rem;
  --radius-box: 0.875rem;    --radius-badge: 0.375rem;
}
```

### Tabla de tokens

| Token       | Light     | Dark      | Uso                          |
|-------------|-----------|-----------|------------------------------|
| base-100    | `#ffffff` | `#1c1c1e` | Fondo de tarjetas/superficie |
| base-200    | `#f2f2f7` | `#2c2c2e` | Fondo secundario             |
| base-300    | `#e5e5ea` | `#3a3a3c` | Bordes / fondo de página     |
| base-content| `#1c1c1e` | `#f2f2f7` | Texto                        |
| primary     | `#e60000` | `#ff3b30` | Marca / acción principal     |
| secondary   | `#4a4d4e` | `#8e8e93` | Acción secundaria            |
| accent      | `#f59e0b` | `#fcd34d` | Énfasis                      |
| info        | `#0284c7` | `#38bdf8` | Informativo                  |
| success     | `#16a34a` | `#34d399` | Éxito / guardar              |
| warning     | `#eab308` | `#fde047` | Advertencia                  |
| error       | `#b91c1c` | `#f87171` | Error / cancelar             |
| **edit**    | `#d97706` | `#fbbf24` | Acción editar                |
| **delete**  | `#cc0000` | `#ff4040` | Acción eliminar              |
| **view**    | `#2563eb` | `#60a5fa` | Acción ver/abrir             |

Registrar `edit/delete/view` como utilidades Tailwind (`text-edit`, etc.):

```css
@theme {
  --color-edit:   #d97706;
  --color-delete: #cc0000;
  --color-view:   #2563eb;
}
```

---

## 4. Botones (el patrón clave)

**Estilo Cupertino/iOS:** sin borde, **forma de cápsula (pill)**, etiqueta **semibold**, con
feedback al pulsar (`:active`) y anillo de foco accesible (`:focus-visible`). El color sale de
las variables del tema. Todo se construye con **DaisyUI + Tailwind v4** (clases `.btn .btn-*`)
sobre los tokens del tema; las reglas viven en `theme/static_src/src/styles.css`.

### Base global (aplica a todos los `.btn`)

```css
.btn {
  border-width: 0 !important;          /* sin borde */
  border-radius: 9999px !important;    /* cápsula (pill) */
  font-weight: 600;                    /* etiqueta semibold */
  transition: transform 0.08s ease, background-color 0.15s ease, box-shadow 0.15s ease;
}
.btn-circle { border-radius: 9999px !important; }   /* conserva forma circular */
.btn:active { transform: scale(0.96); }             /* feedback táctil */
.btn:focus-visible {                                 /* foco con teclado (sin borde) */
  outline: 2px solid color-mix(in srgb, currentColor 55%, transparent);
  outline-offset: 2px;
}
```

### Color por variante (fondo translúcido + texto color completo)

Patrón translúcido: **fondo 18%** + **texto color completo** + sombra suave (el borde se anula
con la regla global de arriba). En hover sube a **28% / 22%**. Va **fuera de `@layer`** con
`!important` para ganarle a DaisyUI.

```css
.btn-primary {
  background-color: color-mix(in srgb, var(--color-primary) 18%, transparent) !important;
  color:            var(--color-primary) !important;
  box-shadow:       0 1px 6px color-mix(in srgb, var(--color-primary) 15%, transparent) !important;
}
.btn-primary:hover {
  background-color: color-mix(in srgb, var(--color-primary) 28%, transparent) !important;
  box-shadow:       0 2px 8px color-mix(in srgb, var(--color-primary) 22%, transparent) !important;
}
```

Repite el bloque cambiando la variable para cada variante:
`--color-secondary / success / error / warning / info / accent / neutral / edit / delete / view`.
(Ver `theme/static_src/src/styles.css` para el set completo, incluidos los alias
`btn-save` = success y `btn-cancel` = neutral usados por el componente de confirmación.)

### Variantes y tamaños

| Clase            | Color        | Uso              |
|------------------|--------------|------------------|
| `btn-primary`    | primary      | Acción principal |
| `btn-secondary`  | secondary    | Secundaria       |
| `btn-success`    | success      | Guardar/confirmar|
| `btn-error`      | error        | Cancelar/negativo|
| `btn-warning`    | warning      | Precaución       |
| `btn-info`       | info         | Informativa      |
| `btn-edit`       | edit         | Editar           |
| `btn-delete`     | delete       | Eliminar         |
| `btn-view`       | view         | Ver / abrir      |

Tamaños DaisyUI: `btn-xs`, `btn-sm`, (default), `btn-lg`. Otros: `btn-ghost`, `btn-circle`, `btn-outline`.

### Ejemplos HTML

```html
<button class="btn btn-primary">Guardar</button>
<button class="btn btn-success btn-sm h-9 min-h-0 px-5 text-xs font-semibold">Confirmar</button>
<button class="btn btn-ghost btn-sm">Cancelar</button>

<!-- Iconos de acción usando el color (sin fondo de botón) -->
<button class="inline-flex items-center justify-center w-7 h-7 text-edit hover:opacity-70 transition-opacity" title="Editar">
  <i class="fa-solid fa-pen"></i>
</button>
<button class="... text-delete ..." title="Eliminar"><i class="fa-solid fa-trash-can"></i></button>
<button class="... text-view ..."   title="Ver"><i class="fa-solid fa-eye"></i></button>
```

---

## 5. Otros componentes

**Card con elevación 3D** (añade sombra en capas a `.rounded-2xl.border-base-300`):

```css
.rounded-2xl.border-base-300 {
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,.60),
    0 1px 2px rgba(0,0,0,.04), 0 3px 8px rgba(0,0,0,.07), 0 8px 20px rgba(0,0,0,.05);
}
[data-theme="dark"] .rounded-2xl.border-base-300 {
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,.06),
    0 1px 2px rgba(0,0,0,.30), 0 3px 8px rgba(0,0,0,.35), 0 8px 20px rgba(0,0,0,.25);
}
```
```html
<div class="card bg-base-100 border border-base-300 shadow-xs"> ... </div>
```

**Tabla** (thead tintado, filas alternas, hover primario):

```css
@layer components {
  .table thead tr { background-color: var(--color-base-200); }
  .table thead th { padding-block:.75rem; border-bottom:2px solid var(--color-base-300); }
  .table tbody tr:nth-child(even){ background-color: color-mix(in oklab,var(--color-base-200) 50%,var(--color-base-100)); }
  .table tbody tr { border-bottom:1px solid color-mix(in oklab,var(--color-base-content) 6%,transparent); transition:background-color .12s ease; }
  .table tbody tr:last-child{ border-bottom:none; }
  .table tbody tr:hover{ background-color: color-mix(in oklab,var(--color-primary) 8%,transparent)!important; }
}
```

**Inputs / forms — estilo iOS (Cupertino):** fondo tenue (`base-200`), **sin borde**, esquinas
redondeadas y, al foco, un **anillo** del color `primary` (en vez de borde) + fondo `base-100`.
Aplica a los componentes DaisyUI (`.input/.textarea/.select/.file-input`) y a las variantes
`-bordered` (compat v4→v5).

```css
.input,.textarea,.select,.file-input,
.input-bordered,.textarea-bordered,.select-bordered,.file-input-bordered{
  border:none !important;
  background-color: var(--color-base-200);
  border-radius: 0.75rem;
  transition: box-shadow .15s ease, background-color .15s ease;
}
.input:focus,.input:focus-within,.textarea:focus,.select:focus,.file-input:focus,
.input-bordered:focus,.input-bordered:focus-within,.textarea-bordered:focus,.select-bordered:focus{
  outline:none;
  background-color: var(--color-base-100);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--color-primary) 45%, transparent);
}
```
```html
<input class="input input-bordered w-full" placeholder="Usuario">
<select class="select select-bordered select-sm"> ... </select>
```

**Badges** (genéricas DaisyUI + de marca por tipo de archivo):

```css
@layer utilities { .badge { gap: 0; } }   /* fix gap interno DaisyUI v5 */
.badge.badge-pdf   { background:#E60012!important; color:#fff!important; border:none!important; }
.badge.badge-word  { background:#2B579A!important; color:#fff!important; border:none!important; }
.badge.badge-excel { background:#217346!important; color:#fff!important; border:none!important; }
```
```html
<span class="badge badge-sm badge-success badge-outline">Activo</span>
```

**Navbar** (DaisyUI):

```html
<header class="navbar bg-base-100 border-b border-base-300">
  <div class="flex-1"><a class="btn btn-ghost text-xl text-primary font-bold">Mi App</a></div>
  <div class="flex-none gap-2">
    <a class="btn btn-ghost btn-sm">Sección</a>
  </div>
</header>
```

---

## 6. Fuente Nunito + FontAwesome (en `<head>`)

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6/css/all.min.css" rel="stylesheet">
```
```css
html {
  font-family: 'Nunito', -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
```

---

## 7. Toggle de tema (light/dark con persistencia)

`<html lang="es" data-theme="light" id="html-root">` + en el navbar un `swap`:

```html
<label class="swap swap-rotate btn btn-ghost btn-circle">
  <input type="checkbox" id="theme-toggle" />
  <svg class="swap-off size-5 fill-current">...sol...</svg>
  <svg class="swap-on  size-5 fill-current text-primary">...luna...</svg>
</label>
```
```html
<script>
  const root = document.getElementById('html-root');
  const saved = localStorage.getItem('theme');
  if (saved) root.setAttribute('data-theme', saved);
  const t = document.getElementById('theme-toggle');
  if (t) t.addEventListener('change', function () {
    const theme = this.checked ? 'dark' : 'light';
    root.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  });
  if (t && root.getAttribute('data-theme') === 'dark') t.checked = true;
</script>
```

---

## 8. Toasts / alerts (componente DaisyUI, sin librería externa)

Se usa `static/js/components/alert-component.js` (clase `Alert`, expuesta como `window.Alert`).
Crea un contenedor `toast toast-top toast-end z-[9999]` y mete cada aviso como `.alert .alert-*`
(ya tematizados en light/dark por las variantes `.alert-*`). Requiere FontAwesome para los iconos.

**API:**

```js
Alert.success('Guardado');
Alert.error('Algo falló', { autoHide: 5000 });
Alert.warning('Cuidado');
Alert.info('Info');
Alert.show('Mensaje', 'success', { autoHide: 4000, dismissible: true });
Alert.confirm('¿Eliminar?', () => borrar(), null,
              { confirmText: 'Eliminar', confirmClass: 'btn-delete', type: 'error' });
```

**Cargar + renderizar `django.contrib.messages` como toasts** (en `base.html`, antes de `</body>`):

```django
<script src="{% static 'js/components/alert-component.js' %}"></script>
{% if messages %}
<script>
  document.addEventListener('DOMContentLoaded', function () {
    {% for message in messages %}
    if (window.Alert) window.Alert.show('{{ message|escapejs }}', '{{ message.tags }}', { autoHide: 5000 });
    {% endfor %}
  });
</script>
{% endif %}
```

> Los tags de Django (`success/error/warning/info`) mapean directo a los tipos del toast.
> Si usas `Alert.confirm`, define los alias `.btn-save` (= success) y `.btn-cancel` (= neutral).

---

## 9. Checklist de integración

1. [ ] Crear `static_src/` con `input.css`, `package.json` y `postcss.config.mjs`.
2. [ ] Pegar la cabecera (§2) ajustando los `@source` a tus apps.
3. [ ] Pegar los temas light/dark (§3) y el `@theme` de edit/delete/view.
4. [ ] Pegar el set de botones (§4), alerts, card 3D, tabla e inputs (§5).
5. [ ] En `base.html`: `data-theme="light"`, fuentes Nunito + FontAwesome (§6), toggle (§7).
6. [ ] Copiar `alert-component.js` y enganchar `django.messages` (§8).
7. [ ] `cd static_src && npm install && npm run build`.
8. [ ] Cargar `<link href="{% static 'css/main.css' %}" rel="stylesheet">` en `base.html`.
9. [ ] Probar: marca roja + Nunito, botones translúcidos, toggle persistente, toasts.
