from collections import Counter
from datetime import datetime
from urllib.parse import unquote
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from . import company_loader
from .models import EstructuraCache, ProyectoFinalCache, SitioCache


WEBHOOK_URL = "https://n8npozos.magoreal.com/webhook/nc-tekon"
WEBHOOK_DEEP_URL = "https://n8npozos.magoreal.com/webhook/nc-tekon-deep"

FINAL_ROOT_PATH = "/20-PTI SP"


def _parse_name(path_encoded):
    decoded = unquote(path_encoded).rstrip("/")
    return decoded.split("/")[-1]


def _parse_item_date(item):
    """Extrae timestamp de un item. n8n Nextcloud devuelve lastModified (camelCase)."""
    if not item or not isinstance(item, dict):
        return None
    val = (
        item.get("lastModified")  # n8n Nextcloud node
        or item.get("mtime")
        or item.get("lastmodified")
        or item.get("getlastmodified")
    )
    if val is None and "propstat" in item:
        for ps in item.get("propstat", []) or []:
            props = ps.get("prop", {}) or {}
            val = props.get("getlastmodified")
            if val:
                break
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        s = val.replace("GMT", "").strip()
        fmts = [("%a, %d %b %Y %H:%M:%S", 25), ("%Y-%m-%dT%H:%M:%S", 19), ("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d", 10)]
        for fmt, maxlen in fmts:
            try:
                dt = datetime.strptime(s[:maxlen], fmt)
                return dt.timestamp()
            except (ValueError, TypeError):
                continue
    return None


def _get_folder_lastmod(path):
    """Obtiene la fecha de última modificación de una carpeta (max mtime de sus items)."""
    try:
        items = _fetch_items(path)
        timestamps = [_parse_item_date(i) for i in items if i]
        valid = [t for t in timestamps if t is not None]
        if not valid:
            return None
        return max(valid)
    except Exception:
        return None


_MESES_ES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def _format_lastmod(ts):
    """Formatea timestamp a string legible (ej: 25 feb 2025)."""
    if ts is None:
        return None
    try:
        dt = datetime.fromtimestamp(ts)
        return f"{dt.day:02d} {_MESES_ES[dt.month - 1]} {dt.year}"
    except (ValueError, TypeError, OSError, IndexError):
        return None


def _fetch_items(path):
    resp = requests.get(WEBHOOK_URL, params={"path": path}, timeout=15)
    resp.raise_for_status()
    try:
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _fetch_deep(root_folder_path):
    """Llama al endpoint deep que devuelve {subfolder: {ext: count}} en una sola petición."""
    resp = requests.get(WEBHOOK_DEEP_URL, params={"path": root_folder_path}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _parse_subfolders(deep):
    """Parsea la respuesta del endpoint deep a lista de {nombre, archivos}.
    Soporta formatos:
    - {"SubA": {"pdf": 2}, "SubB": {"dwg": 1}}  (dict plano)
    - {"subfolders": [{"nombre": "X", "archivos": {...}}]}
    - [{"nombre": "X", "archivos": {...}}]
    - ["SubA", "SubB"]  (lista de nombres)
    """
    if not deep:
        return []
    if isinstance(deep, list):
        result = []
        for item in deep:
            if isinstance(item, dict):
                result.append({
                    "nombre": str(item.get("nombre") or item.get("name") or ""),
                    "archivos": item.get("archivos") or item.get("files") or {},
                })
            elif isinstance(item, str):
                result.append({"nombre": item, "archivos": {}})
        return result
    if isinstance(deep, dict):
        if "subfolders" in deep:
            raw = deep["subfolders"]
            if isinstance(raw, list):
                return _parse_subfolders(raw)
        return [
            {"nombre": str(sub), "archivos": conteo if isinstance(conteo, dict) else {}}
            for sub, conteo in sorted(deep.items())
            if sub != "subfolders" and isinstance(conteo, dict)
        ]
    return []


def _build_tree(path, depth=0, max_depth=3, structure_only=False):
    """Árbol recursivo de carpetas. structure_only=True omite conteo de archivos."""
    if depth > max_depth:
        return []
    try:
        items = _fetch_items(path)
        subfolder_items = [i for i in items if i.get("type") == "folder"]
        if not subfolder_items:
            return []

        if not structure_only:
            try:
                deep = _fetch_deep(path)
                counts_map = {s["nombre"]: s["archivos"] for s in _parse_subfolders(deep)}
            except Exception:
                counts_map = {}
        else:
            counts_map = {}

        def process_folder(item):
            nombre = _parse_name(item["path"])
            child_path = f"{path}/{nombre}"
            if structure_only:
                archivos = {}
            else:
                archivos = counts_map.get(nombre) or _count_files_in_folder(child_path)
            children = _build_tree(child_path, depth + 1, max_depth, structure_only)
            return {"nombre": nombre, "archivos": archivos, "children": children}

        with ThreadPoolExecutor(max_workers=6) as ex:
            result = list(ex.map(process_folder, subfolder_items))
        return sorted(result, key=lambda c: c["nombre"])
    except Exception:
        return []


def _get_user_rol(user):
    """Devuelve el rol del usuario ('administrador' o 'visitante')."""
    try:
        return user.profile.rol
    except Exception:
        return "visitante"


@login_required
def index(request):
    """Página Docs. Contratista. Las cards se cargan por AJAX."""
    rol = _get_user_rol(request.user)
    empresas_list = company_loader.get_all()
    primera = empresas_list[0] if empresas_list else None
    empresa = request.GET.get("empresa", primera.nombre if primera else "")
    if not any(e.nombre == empresa for e in empresas_list):
        empresa = primera.nombre if primera else ""
    empresa_links = {e.nombre: e.link_para_rol(rol).rstrip("/") for e in empresas_list}
    return render(request, "docs/index.html", {
        "empresa": empresa,
        "empresas": empresas_list,
        "empresa_links": empresa_links,
        "titulo_pagina": "Docs. Contratista",
    })


@login_required
def final(request):
    """Página Docs. Finales — árbol de /20-PTI SP."""
    from django.conf import settings
    from .models import SiteConfig
    rol = _get_user_rol(request.user)
    try:
        config = SiteConfig.objects.get(clave="NEXTCLOUD_FINAL_BASE")
        nextcloud_base = config.link_para_rol(rol)
    except SiteConfig.DoesNotExist:
        nextcloud_base = getattr(settings, "NEXTCLOUD_FINAL_BASE", "")
    return render(request, "docs/final.html", {
        "titulo_pagina": "Docs. Finales",
        "nextcloud_base": nextcloud_base,
    })


@login_required
def api_sitios(request):
    """GET: retorna lista de sitios (carpetas) para la empresa indicada."""
    empresa = request.GET.get("empresa", "")
    emp = company_loader.get_by_nombre(empresa)
    if not emp:
        return JsonResponse({"sitios": []})
    root_path = emp.root_path()
    try:
        raiz_items = [i for i in _fetch_items(root_path) if i.get("type") == "folder"]
        sitios = sorted(_parse_name(item["path"]) for item in raiz_items)
        return JsonResponse({"sitios": sitios})
    except Exception:
        return JsonResponse({"sitios": []})


def _fetch_carpetas(empresa_codigo, structure_only=False):
    """Obtiene carpetas para una empresa desde el webhook.
    structure_only=True solo trae nombres de subcarpetas."""
    emp = company_loader.get_by_nombre(empresa_codigo)
    if not emp:
        return [], "Empresa no configurada."
    root_path = emp.root_path()
    carpetas = []
    error = None
    try:
        raiz_items = [i for i in _fetch_items(root_path) if i.get("type") == "folder"]
        items_config = [
            {"path": item["path"], "nombre_carpeta": _parse_name(item["path"])}
            for item in raiz_items
        ]

        def get_carpeta(item):
            nombre_carpeta = item["nombre_carpeta"]
            root_folder_path = f"{root_path}/{nombre_carpeta}"
            subfolders = []
            if structure_only:
                try:
                    items = _fetch_items(root_folder_path)
                    subfolders = [
                        {"nombre": _parse_name(i["path"]), "archivos": {}}
                        for i in items
                        if i.get("type") == "folder"
                    ]
                    subfolders.sort(key=lambda s: s["nombre"])
                except Exception:
                    pass
            else:
                try:
                    deep = _fetch_deep(root_folder_path)
                    subfolders = _parse_subfolders(deep)
                except Exception:
                    pass
                if not subfolders:
                    try:
                        items = _fetch_items(root_folder_path)
                        subfolders = [
                            {"nombre": _parse_name(i["path"]), "archivos": {}}
                            for i in items
                            if i.get("type") == "folder"
                        ]
                        subfolders.sort(key=lambda s: s["nombre"])
                    except Exception:
                        pass
            return {"nombre": nombre_carpeta, "subfolders": subfolders}

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(get_carpeta, item) for item in items_config]
            carpetas = [f.result() for f in as_completed(futures)]
        carpetas.sort(key=lambda c: c["nombre"])
    except requests.exceptions.ConnectionError:
        error = "No se pudo conectar al servidor."
    except requests.exceptions.Timeout:
        error = "La solicitud tardó demasiado. Intenta de nuevo."
    except requests.exceptions.HTTPError as e:
        error = f"Error del servidor: {e}"
    except Exception as e:
        error = str(e) or "Error inesperado."
    return carpetas, error


@login_required
def api_carpetas(request):
    """GET: retorna carpetas. structure_only=1 solo trae estructura (sin archivos)."""
    primera = company_loader.get_first()
    empresa = request.GET.get("empresa", primera.nombre if primera else "")
    structure_only = request.GET.get("structure_only") in ("1", "true", "yes")

    # Caché de estructura: comparar timestamp del root de la empresa
    if structure_only:
        emp = company_loader.get_by_nombre(empresa)
        ts = _get_folder_lastmod(emp.root_path()) if emp else None
        try:
            entry = EstructuraCache.objects.get(empresa=empresa)
            if ts is not None and entry.ultima_actualizacion_ts == ts:
                return JsonResponse({"carpetas": entry.datos})
        except EstructuraCache.DoesNotExist:
            pass

        carpetas, error = _fetch_carpetas(empresa, structure_only=True)
        if error:
            return JsonResponse({"error": error, "carpetas": []}, status=500)
        if carpetas:
            EstructuraCache.objects.update_or_create(
                empresa=empresa,
                defaults={"ultima_actualizacion_ts": ts, "datos": carpetas},
            )
        return JsonResponse({"carpetas": carpetas})

    carpetas, error = _fetch_carpetas(empresa, structure_only=False)
    if error:
        return JsonResponse({"error": error, "carpetas": []}, status=500)
    return JsonResponse({"carpetas": carpetas})


def _count_files_in_folder(path):
    """Cuenta archivos por extensión en una carpeta (recursivo y paralelo) usando el endpoint básico."""
    conteo = Counter()
    try:
        items = _fetch_items(path)
        sub_paths = []
        for item in items:
            if item.get("type") == "file":
                name = item.get("name") or item.get("basename") or _parse_name(item.get("path", ""))
                if name and "." in name:
                    ext = name.rsplit(".", 1)[-1].lower()
                    conteo[ext] += 1
            elif item.get("type") == "folder":
                sub_name = _parse_name(item.get("path", ""))
                if sub_name:
                    sub_paths.append(f"{path}/{sub_name}")
        if sub_paths:
            with ThreadPoolExecutor(max_workers=6) as ex:
                for sub_conteo in ex.map(_count_files_in_folder, sub_paths):
                    conteo.update(sub_conteo)
        return dict(conteo)
    except Exception:
        return {}


@login_required
def api_carpetas_archivos(request):
    """GET: retorna subfolders con archivos para los sitios indicados.
    Params: empresa, carpetas (nombres separados por coma).
    Respuesta: {"Site1": [{"nombre": "SubA", "archivos": {"pdf": 2}}, ...], "Site2": [...]}
    Si nc-tekon-deep falla, usa nc-tekon para contar archivos por subcarpeta.
    """
    empresa = request.GET.get("empresa", "")
    emp = company_loader.get_by_nombre(empresa)
    if not emp:
        return JsonResponse({"error": "Empresa no configurada."}, status=400)
    root_path = emp.root_path()
    carpetas_param = request.GET.get("carpetas", "")
    nombres_sitios = [s.strip() for s in carpetas_param.split(",") if s.strip()]
    resultado = {}
    ultima_actualizacion = {}
    try:
        for nombre in nombres_sitios:
            root_folder_path = f"{root_path}/{nombre}"

            # Comparar timestamp de Nextcloud con el cacheado
            ts = _get_folder_lastmod(root_folder_path)
            try:
                entry = SitioCache.objects.get(empresa=emp.nombre, sitio=nombre)
                if ts is not None and entry.ultima_actualizacion_ts == ts:
                    resultado[nombre] = entry.datos
                    if entry.ultima_actualizacion:
                        ultima_actualizacion[nombre] = entry.ultima_actualizacion
                    continue
            except SitioCache.DoesNotExist:
                pass

            # Caché ausente o desactualizado — re-fetchear
            subfolders = []
            try:
                deep = _fetch_deep(root_folder_path)
                subfolders = _parse_subfolders(deep)
            except Exception:
                pass
            if not subfolders:
                try:
                    items = _fetch_items(root_folder_path)
                    sub_items = [i for i in items if i.get("type") == "folder"]
                    if sub_items:

                        def get_sub_archivos(item):
                            sub_name = _parse_name(item["path"])
                            sub_path = f"{root_folder_path}/{sub_name}"
                            return {"nombre": sub_name, "archivos": _count_files_in_folder(sub_path)}

                        with ThreadPoolExecutor(max_workers=6) as ex:
                            subfolders = list(ex.map(get_sub_archivos, sub_items))
                        subfolders.sort(key=lambda s: s["nombre"])
                except Exception:
                    pass
            subs_sin_archivos = [s for s in subfolders if not s.get("archivos")]
            if subs_sin_archivos:
                def enrich_sub(sub, rfp=root_folder_path):
                    sub_path = f"{rfp}/{sub['nombre']}"
                    archivos = _count_files_in_folder(sub_path)
                    return {**sub, "archivos": archivos} if archivos else sub
                with ThreadPoolExecutor(max_workers=6) as ex:
                    enriched = {s["nombre"]: s for s in ex.map(enrich_sub, subs_sin_archivos)}
                subfolders = [enriched.get(s["nombre"], s) for s in subfolders]

            ultima_str = _format_lastmod(ts) if ts else ""
            if subfolders:  # solo cachear si hay datos reales
                SitioCache.objects.update_or_create(
                    empresa=emp.nombre,
                    sitio=nombre,
                    defaults={
                        "ultima_actualizacion_ts": ts,
                        "ultima_actualizacion": ultima_str,
                        "datos": subfolders,
                    }
                )
            resultado[nombre] = subfolders
            if ultima_str:
                ultima_actualizacion[nombre] = ultima_str
        return JsonResponse({**resultado, "ultima_actualizacion": ultima_actualizacion})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def api_final_tree(request):
    """GET: retorna árbol de proyectos en FINAL_ROOT_PATH.
    ?structure_only=1 → solo nombres de carpetas, sin conteo de archivos (rápido).
    """
    structure_only = request.GET.get("structure_only") in ("1", "true", "yes")
    try:
        children = _build_tree(FINAL_ROOT_PATH, structure_only=structure_only)
        return JsonResponse({"nombre": "20-PTI SP", "children": children})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def api_final_archivos(request):
    """GET: retorna árbol con conteo de archivos para los proyectos indicados.
    Params: proyectos (nombres separados por coma)
    Respuesta: {"Proyecto1": {"archivos": {...}, "children": [...]}, ...}
    """
    proyectos_param = request.GET.get("proyectos", "")
    nombres = [s.strip() for s in proyectos_param.split(",") if s.strip()]

    def get_proyecto(nombre):
        path = f"{FINAL_ROOT_PATH}/{nombre}"

        # Comparar timestamp de Nextcloud con el cacheado
        ts = _get_folder_lastmod(path)
        try:
            entry = ProyectoFinalCache.objects.get(nombre=nombre)
            if ts is not None and entry.ultima_actualizacion_ts == ts:
                return nombre, {**entry.datos, "ultima_actualizacion": entry.ultima_actualizacion}
        except ProyectoFinalCache.DoesNotExist:
            pass

        # Sin caché o timestamp distinto: re-fetchear
        children = _build_tree(path, max_depth=2)
        total: dict = {}
        for child in children:
            for ext, count in child.get("archivos", {}).items():
                total[ext] = total.get(ext, 0) + count
        ultima = _format_lastmod(ts) if ts else None
        data = {"archivos": total, "children": children}

        if children:  # solo cachear si hay datos reales
            ProyectoFinalCache.objects.update_or_create(
                nombre=nombre,
                defaults={
                    "ultima_actualizacion_ts": ts,
                    "ultima_actualizacion": ultima or "",
                    "datos": data,
                }
            )
        return nombre, {**data, "ultima_actualizacion": ultima}

    resultado = {}
    try:
        with ThreadPoolExecutor(max_workers=4) as ex:
            for nombre, data in ex.map(lambda n: get_proyecto(n), nombres):
                resultado[nombre] = data
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    return JsonResponse(resultado)
