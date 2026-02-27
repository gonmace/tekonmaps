#!/usr/bin/env python
"""
Filtra un fixture JSON para eliminar modelos obsoletos y referencias.
Útil cuando se restaura un dump antiguo en un esquema con modelos eliminados.
"""
import json
import sys

# Modelos eliminados (app.model) - no cargar
EXCLUDED_MODELS = {"docs.doccarpeta"}

# ContentTypes a excluir (app_label, model)
EXCLUDED_CONTENT_TYPES = {("docs", "doccarpeta")}


def should_exclude(obj):
    model = obj.get("model", "")
    if model in EXCLUDED_MODELS:
        return True
    # admin.logentry y otros con content_type FK
    if model == "admin.logentry":
        fields = obj.get("fields", {})
        ct = fields.get("content_type")
        if isinstance(ct, list) and tuple(ct) in EXCLUDED_CONTENT_TYPES:
            return True
    if model == "contenttypes.contenttype":
        fields = obj.get("fields", {})
        if (fields.get("app_label"), fields.get("model")) in EXCLUDED_CONTENT_TYPES:
            return True
    return False


def main():
    data = json.load(sys.stdin)
    filtered = [o for o in data if not should_exclude(o)]
    json.dump(filtered, sys.stdout, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
