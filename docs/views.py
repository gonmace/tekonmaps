from collections import Counter
from datetime import datetime
from urllib.parse import unquote
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from .models import DocEmpresa

WEBHOOK_URL = "https://n8npozos.magoreal.com/webhook/nc-tekon"
WEBHOOK_DEEP_URL = "https://n8npozos.magoreal.com/webhook/nc-tekon-deep"


def _get_empresa_or_default(nombre):
    """Obtiene DocEmpresa por nombre. Si no existe, retorna la primera o None."""
    try:
        return DocEmpresa.objects.get(nombre=nombre)
    except DocEmpresa.DoesNotExist:
        return DocEmpresa.objects.first()


def _root_path(empresa_nombre):
    """Path raíz para la empresa."""
    emp = _get_empresa_or_default(empresa_nombre)
    return emp.root_path() if emp else f"/{empresa_nombre}"


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


@login_required
def index(request):
    """Página de documentación. Las cards se cargan por AJAX."""
    empresas_list = list(DocEmpresa.objects.all())
    primera = empresas_list[0] if empresas_list else None
    empresa = request.GET.get("empresa", primera.nombre if primera else "")
    if not any(e.nombre == empresa for e in empresas_list):
        empresa = primera.nombre if primera else ""
    empresa_links = {e.nombre: (e.link_nextcloud or "").rstrip("/") for e in empresas_list}
    return render(request, "docs/index.html", {
        "empresa": empresa,
        "empresas": empresas_list,
        "empresa_links": empresa_links,
        "titulo_pagina": "Documentación",
    })


@login_required
def api_sitios(request):
    """GET: retorna lista de sitios (carpetas) para la empresa indicada."""
    empresa = request.GET.get("empresa", "")
    emp = _get_empresa_or_default(empresa)
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
    emp = _get_empresa_or_default(empresa_codigo)
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
    primera = DocEmpresa.objects.first()
    empresa = request.GET.get("empresa", primera.nombre if primera else "")
    structure_only = request.GET.get("structure_only") in ("1", "true", "yes")
    carpetas, error = _fetch_carpetas(empresa, structure_only=structure_only)
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
    emp = _get_empresa_or_default(empresa)
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
            # Para subcarpetas sin archivos, buscar un nivel más adentro
            subs_sin_archivos = [s for s in subfolders if not s.get("archivos")]
            if subs_sin_archivos:
                def enrich_sub(sub, rfp=root_folder_path):
                    sub_path = f"{rfp}/{sub['nombre']}"
                    archivos = _count_files_in_folder(sub_path)
                    return {**sub, "archivos": archivos} if archivos else sub
                with ThreadPoolExecutor(max_workers=6) as ex:
                    enriched = {s["nombre"]: s for s in ex.map(enrich_sub, subs_sin_archivos)}
                subfolders = [enriched.get(s["nombre"], s) for s in subfolders]
            resultado[nombre] = subfolders
            ts = _get_folder_lastmod(root_folder_path)
            if ts:
                ultima_actualizacion[nombre] = _format_lastmod(ts)
        return JsonResponse({**resultado, "ultima_actualizacion": ultima_actualizacion})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
