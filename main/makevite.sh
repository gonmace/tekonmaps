#!/bin/bash
# -*- ENCODING: UTF-8 -*-

# Obtener el nombre del directorio actual, que ahora será 'src'
app=$(basename "$PWD")

# Crear el directorio 'src' si no existe y navegar a él
mkdir -p src
cd src

# Iniciar un nuevo proyecto de Node.js y agregar Vite
npm init --y
npm i -D vite

# Modificar el archivo package.json usando jq para agregar los scripts necesarios
jq '.scripts |= .+ {
      "build": "vite build --watch",
      "build:admin": "vite build -c vite.config.admin.js --watch"
    }' package.json >temp.json && mv temp.json package.json

# Crear el archivo 'vite.config.js'
cat > vite.config.js <<EOF
const path = require('path');
const { defineConfig } = require('vite')

module.exports = defineConfig({
    build: {
        outDir: path.resolve(__dirname, '../../static/js'),
        minify: true,
        rollupOptions: {
            output: {
                entryFileNames: '${app}.js',
                format: 'iife'
              },
            input: './index-${app}.js',
        }
    }
});
EOF

cat > index-${app}.js <<EOF
document.addEventListener("DOMContentLoaded", function(){


});
EOF

# Instalar las dependencias de npm
npm install

# Ejecutar el script de construcción
npm run build