#!/bin/bash
# nginx-deploy.sh — instala/actualiza la config de nginx
# Uso: bash nginx-deploy.sh   (o: make nginx)
# IMPORTANTE: ejecutar solo una vez (primer deploy) o cuando cambie nginx.conf.
#             NO ejecutar en cada deploy — certbot modifica el archivo para SSL
#             y sobreescribirlo eliminaría los certificados configurados.

set -e

if [ ! -f .env ]; then
    echo "Error: no se encontró el archivo .env. Ejecuta: bash setup.sh"
    exit 1
fi
set -a
source .env
set +a

PROJECT_NAME=${PROJECT_NAME:?La variable PROJECT_NAME no está definida en .env}
APP_PORT=${APP_PORT:-8000}
DOMAIN=${DOMAIN:?La variable DOMAIN no está definida en .env}
PROJECT_DIR=$(pwd)

NGINX_OUT="${PROJECT_NAME}.conf"
NGINX_AVAILABLE="/etc/nginx/sites-available/${PROJECT_NAME}.conf"
NGINX_ENABLED="/etc/nginx/sites-enabled/${PROJECT_NAME}.conf"

echo "▶ Generando ${NGINX_OUT}..."

# Sustituciones seguras con Python (evita problemas con caracteres especiales en sed)
python3 - << PYEOF
def substitute(content, replacements):
    for key, value in replacements.items():
        content = content.replace('{{' + key + '}}', value)
    return content

with open('nginx.conf') as f:
    output = substitute(f.read(), {
        'DOMAIN': '${DOMAIN}',
        'APP_PORT': '${APP_PORT}',
        'PROJECT_DIR': '${PROJECT_DIR}',
    })

with open('${NGINX_OUT}', 'w') as f:
    f.write(output)

print("  Config generada correctamente.")
PYEOF

echo "▶ Instalando config en nginx..."
sudo cp "${NGINX_OUT}" "${NGINX_AVAILABLE}"

if [ ! -L "${NGINX_ENABLED}" ]; then
    sudo ln -s "${NGINX_AVAILABLE}" "${NGINX_ENABLED}"
    echo "  Symlink creado: ${NGINX_ENABLED}"
fi

sudo nginx -t
sudo systemctl reload nginx
echo "✓ nginx actualizado y recargado."
echo ""
echo "Próximo paso: obtener certificado SSL con certbot:"
echo "  sudo certbot --nginx -d ${DOMAIN}"
