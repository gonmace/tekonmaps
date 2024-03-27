#!/bin/bash
# -*- ENCODING: UTF-8 -*-

read -p "Nombre de la App: " app
read -p "Dominio: " dominio
cat > ${app}.conf <<EOF
# /etc/nginx/sites-available/$app

upstream web_$app {
    server django:8000;
}
server {
    server_name $dominio www.${dominio};

    location = /favicon.ico { 
        access_log off; 
        log_not_found off; 
        }

    location /static/ {
        autoindex on;
        alias /app/staticfiles/;
        }
    
    location /media/ {
        autoindex on;
        alias /app/media/;
        }

    location / {
        proxy_pass http://web_app;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $host;
        proxy_redirect off;    
        }
}
EOF

sudo cp $app.conf ./nginx/

cat > ./nginx/Dockerfile <<EOF
# nginx/Dockerfile

# FROM nginx:stable-alpine
# RUN rm /etc/nginx/conf.d/default.conf
# COPY nginx.conf /etc/nginx/conf.d
# EXPOSE 80
sudo cp $app.conf /etc/nginx/sites-available/$app.conf
sudo ln -s /etc/nginx/sites-available/$app.conf /etc/nginx/sites-enabled/$app.conf
nginx -t
EOF

sudo docker-compose up -d --build

exit