import 'leaflet/dist/leaflet.css';
import 'leaflet.markercluster/dist/MarkerCluster.css'
import 'leaflet.markercluster/dist/MarkerCluster.Default.css'
import "leaflet";
import "leaflet.markercluster";
import 'leaflet.markercluster.layersupport';

document.addEventListener('DOMContentLoaded', function () {


var yellowIcon = L.icon({
  iconUrl: static_url+'leaflet/images/marker-icon-yellow.png', 
  shadowUrl: static_url+'leaflet/images/marker-shadow.png',
  iconSize: [25, 41], // Tamaño del icono, ajusta según sea necesario
  iconAnchor: [12, 41], // Punto del icono que corresponderá a la ubicación del marcador
  popupAnchor: [1, -34] // Punto donde se mostrará el popup en relación al icono
});

var redIcon = L.icon({
  iconUrl: static_url+'leaflet/images/marker-icon-red.png', 
  shadowUrl: static_url+'leaflet/images/marker-shadow.png',
  iconSize: [25, 41], 
  iconAnchor: [12, 41], 
  popupAnchor: [1, -34] 
});

var greenIcon = L.icon({
  iconUrl: static_url+'leaflet/images/marker-icon-green.png', 
  shadowUrl: static_url+'leaflet/images/marker-shadow.png',
  iconSize: [25, 41], 
  iconAnchor: [12, 41], 
  popupAnchor: [1, -34] 
});

var blueIcon = L.icon({
  iconUrl: static_url+'leaflet/images/marker-icon-blue.png', 
  shadowUrl: static_url+'leaflet/images/marker-shadow.png',
  iconSize: [25, 41], 
  iconAnchor: [12, 41], 
  popupAnchor: [1, -34] 
});

var grayIcon = L.icon({
  iconUrl: static_url+'leaflet/images/marker-icon-gris.png', 
  shadowUrl: static_url+'leaflet/images/marker-shadow.png',
  iconSize: [25, 41], 
  iconAnchor: [12, 41], 
  popupAnchor: [1, -34] 
});

    var opacidad = 1;

    // Definición de capas de tiles
    var OpenStreetMap_Mapnik = L.tileLayer('https://{s}.tile.osm.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="http://osm.org/copyright">OpenStreetMap</a> contributors',
      opacity: opacidad
    });
    
    var Esri_WorldImagery = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 19,
      attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
      opacity: opacidad
    });
    
    var OpenStreetMap_Dark = L.tileLayer('http://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="http://osm.org/copyright">OpenStreetMap</a> contributors',
      opacity: opacidad
    });
  
    // Suponiendo que tienes una lista de todos tus marcadores
    var allMarkers = [];
    var mapZoomLevel = localStorage.theZoom;
    var mapCenter = [localStorage.lat, localStorage.lon];
    if (isNaN(mapZoomLevel)) {
      mapZoomLevel = 8;
    }
    if (isNaN(localStorage.lat)) {
      mapCenter = [-33.68075,-70.93344444];
    }

        // Creación y configuración del mapa
    var map = L.map('map', {
      center: mapCenter,
      zoom: mapZoomLevel,
      layers: [OpenStreetMap_Mapnik] // Incluye ajgroup y mergroup por defecto
    });




// Grupos de capas para AJ y MER
var ajgroup = L.layerGroup(),
    mergroup = L.layerGroup();

var mcgLayerSupportGroup = L.markerClusterGroup.layerSupport({
    spiderfyDistanceMultiplier: 10,
    showCoverageOnHover: true,
    zoomToBoundsOnClick: true,
    maxClusterRadius: 20
});

    
    // Control de capas
    var control = L.control.layers({
      'OpenStreetMap': OpenStreetMap_Mapnik,
      // 'OpenStreetMap_Dark': OpenStreetMap_Dark,
      'Esri_WorldImagery': Esri_WorldImagery
    }, {
      'AJ': ajgroup,
      'MER': mergroup
    }, {
      collapsed: false,
      groupCheckboxes: true,
      position: 'topleft',
    });
    
    // Añadir marcadores a ajgroup y mergroup
    sitios.forEach(e => {

      let selectedIcon;
      if (e['avance__estado'] === 'ASG') {
        selectedIcon = yellowIcon;
      } else if (e['avance__estado'] === 'EJE') {
        selectedIcon = greenIcon;
      } else if (e['avance__estado'] === 'PTG') {
        selectedIcon = grayIcon;
      } else if (e['avance__estado'] === 'CAN') {
        selectedIcon = redIcon;
      } else {
        selectedIcon = blueIcon;
      }

      var marker = L.marker([e['lat'], e['lon']], {
        icon: selectedIcon, // Asegúrate de que selectedIcon esté definido
        title: e['sitio'] + '_' + e['entel_id'],
        contratista: e.contratista // Asegúrate de tener esta propiedad en tus datos
      });

      marker.bindTooltip(e['nombre'], {permanent: false});
// Ahcer que el tolltip solo se vea en el zoom 9 o mas
      function updateTooltipsBasedOnZoom() {
        var currentZoom = map.getZoom();
        allMarkers.forEach(function(marker) {
            if (currentZoom > 9) {
                marker.openTooltip();
            } else {
                marker.closeTooltip();
            }
        });
    }
    
    // Inicialmente actualiza los tooltips basándose en el zoom actual
    updateTooltipsBasedOnZoom();
    
    // Añade un listener para actualizar los tooltips cada vez que el zoom cambia
    map.on('zoomend', function() {
        updateTooltipsBasedOnZoom();
    });
    

    // Definiendo las rutas a los íconos
    var checkIconPath = static_url+'img/check.png';
    var crossIconPath = static_url+'img/cross.png';

    var excavado = e['avance__excavacion'] === '' ? false : true;
    if (e['avance__excavacion']) {
      var partesDeFecha = e['avance__excavacion'].split('-'); // Separar YYYY, MM, DD
      e['avance__excavacion'] = partesDeFecha[2] + '-' + partesDeFecha[1] + '-' + partesDeFecha[0]; // Reorganizar a D-M-YYYY
    }

    var hormigonado = e['avance__hormigonado'] === '' ? false : true;
    if (e['avance__hormigonado']) {
      var partesDeFecha = e['avance__hormigonado'].split('-'); // Separar YYYY, MM, DD
      e['avance__hormigonado'] = partesDeFecha[2] + '-' + partesDeFecha[1] + '-' + partesDeFecha[0]; // Reorganizar a D-M-YYYY
    }

    var montado = e['avance__montado'] === '' ? false : true;
    if (e['avance__montado']) {
      var partesDeFecha = e['avance__montado'].split('-'); // Separar YYYY, MM, DD
      e['avance__montado'] = partesDeFecha[2] + '-' + partesDeFecha[1] + '-' + partesDeFecha[0]; // Reorganizar a D-M-YYYY
    }

    if (e['avance__fechaFin']) {
      var partesDeFecha = e['avance__fechaFin'].split('-'); // Separar YYYY, MM, DD
      e['avance__fechaFin'] = partesDeFecha[2] + '-' + partesDeFecha[1] + '-' + partesDeFecha[0]; // Reorganizar a D-M-YYYY
    }

    var progressValue = Math.round(e['avance__porcentaje']*100); // Este es el valor de progreso. Reemplázalo con tu valor dinámico

    var popupContent = `
    <div class="max-w-60">
      <div class="flex justify-around">
        <a class="mr-0.5" href="https://www.google.com/maps/search/?api=1&query=${e['lat']},${e['lon']}" target="_blank" ">
          <img src="${static_url}img/logoGoogleMaps.svg" alt="Google Maps" class="w-8 mr-1">
        </a>
        <div>
          <strong> ${e['sitio']} ${e['nombre']} - ${e['contratista']} </strong>
        </div>
      </div>
      <div>
        <div id="imagenes-${e['sitio'].toLowerCase()}" class="thumbnails">Cargando imágenes...</div>
      </div>
      <p>${e['avance__comentario']}</p>
      <div class="flex items-center mb-1">
        <img src="${excavado ? checkIconPath : crossIconPath}" alt="Cross" class="w-3 h-3 mr-1"> Excavación ${e['avance__excavacion']}
      </div>  
      <div class="flex items-center mb-1">
          <img src="${hormigonado ? checkIconPath : crossIconPath}" alt="Cross" class="w-3 h-3 mr-1"> Hormigonado ${e['avance__hormigonado']}
      </div>
      <div class="flex items-center mb-1">
          <img src="${montado ? checkIconPath : crossIconPath}" alt="Check" class="w-3 h-3 mr-1"> Montado ${e['avance__montado']}
      </div>
      <div class="flex items-center mb-1">
        <img src="${e['empalmeE'] ? checkIconPath : crossIconPath}" alt="Check" class="w-3 h-3 mr-1"> Empalme Electrico
      </div>
      <div class="flex items-center mb-1">
        Fecha Entrega: <b>${e['avance__fechaFin']} </b>
      </div>
      <div class="flex items-center">
          <div class="w-full h-4 bg-gray-200 rounded-full overflow-hidden relative mr-2">
              <div class="h-full bg-green-400 rounded-full" style="width: ${progressValue}%;"></div>
          </div>
          <span>${progressValue}%</span>
      </div>
  </div>
  `;
    // <iframe src="/media/pdfs/${e['cod']}.pdf" width="600" height="400"></iframe>
  // <a href="#" class="text-blue-500 hover:text-blue-700" onclick="openPdfModal('static/reportes/${e['cod']}.pdf')">Ver Reporte</a>
  marker.bindPopup(popupContent).on('popupopen', function() {
    fetch(`imgs/api/${e['sitio'].toLowerCase()}/`)
        .then(response => response.json())
        .then(data => {
            const container = document.getElementById(`imagenes-${data['slug']}`);
            container.innerHTML = ''; // Limpiar el mensaje de carga
            let firstImage = true;
            data['imagenes'].forEach((img, index) => {
                const imgElement = document.createElement('img');
                imgElement.src = img.imagen;    
                imgElement.alt = img.descripcion;
                imgElement.className = 'thumbnail' + (firstImage ? ' active' : '');
                firstImage = false; // Solo la primera imagen es activa inicialmente
                imgElement.addEventListener('click', () => {
                  // Redirige al usuario a la página de detalles de la galería
                  // Supongamos que la URL de detalles puede construirse así:
                  // "galeria/detail?id=ID_IMAGEN", donde ID_IMAGEN es un identificador único para cada imagen.
                  window.location.href = `imgs/${e['sitio'].toLowerCase()}`; // Asegúrate de que `img.id` sea el dato correcto para construir la URL
              });
                container.appendChild(imgElement);
            });
            startCarousel(`imagenes-${data['slug']}`);
        });
});

function startCarousel(containerId) {
    const container = document.getElementById(containerId);
    const images = container.getElementsByClassName('thumbnail');
    let currentIndex = 0;

    setInterval(() => {
        images[currentIndex].classList.remove('active');
        currentIndex = (currentIndex + 1) % images.length; // Vuelve al inicio si se supera la cantidad de imágenes
        images[currentIndex].classList.add('active');
    }, 2000); // Cambia cada 2 segundos
}
 

  if (e.contratista == 'AJ') {
    ajgroup.addLayer(marker);
  } else {
    mergroup.addLayer(marker);
  }
  allMarkers.push(marker);
});
    
// Función para regenerar marcadores al actualizar cluster
function reAddMarkers() {
  allMarkers.forEach(marker => {
      if (marker.options.contratista === 'AJ') {
          ajgroup.addLayer(marker);
      } else {
          mergroup.addLayer(marker);
      }
  });
}

// Función para actualizar el radio máximo del cluster
function updateMaxClusterRadius(newRadius) {
  // Guardar la vista actual del mapa
  var currentZoom = map.getZoom();
  var currentCenter = map.getCenter();

  mcgLayerSupportGroup.options.maxClusterRadius = newRadius;
  mcgLayerSupportGroup.clearLayers();

  reAddMarkers();

  mcgLayerSupportGroup.checkIn([ajgroup, mergroup]);

  // Restaurar la vista del mapa
  map.setView(currentCenter, currentZoom);
}
    // Añadir grupos al mcgLayerSupportGroup y luego al mapa
    mcgLayerSupportGroup.checkIn([ajgroup, mergroup]);
    mcgLayerSupportGroup.addTo(map);
    
    // Iniciar por defecto checked
    ajgroup.addTo(map);
    mergroup.addTo(map);
    // Añadir el control de capas al mapa

    control.addTo(map);

// Crear un control de UI para el radio del cluster con un slider
var radiusControl = L.control({ position: 'bottomleft' });
radiusControl.onAdd = function (map) {
    var div = L.DomUtil.create('div', 'leaflet-control leaflet-bar radius-control');
    div.innerHTML = `
        <div class="leaflet-control-container p-1" >
            <label for="radiusSlider">Radio del Cluster:</label>
            <input type="range" id="radiusSlider" min="0" max="500" value="150" />
            <span id="radiusValue">20</span>
        </div>
    `;
    // Detiene la propagación de eventos del mouse al mapa
    L.DomEvent.disableClickPropagation(div);
    return div;
};
radiusControl.addTo(map);

function updateRadiusValue(value) {
    document.getElementById('radiusValue').innerText = value;
}

// Evento para manejar el cambio en el control del slider
L.DomEvent.addListener(L.DomUtil.get('radiusSlider'), 'input', function (e) {
    var newRadius = e.target.value;
    updateMaxClusterRadius(newRadius);
    updateRadiusValue(newRadius);
});


// Crear un control personalizado para mostrar la leyenda de los iconos
var legendControl = L.control({ position: 'bottomright' });
legendControl.onAdd = function (map) {
  var div = L.DomUtil.create('div', 'info legend');
  div.style.backgroundColor = 'white';
  div.style.opacity = '0.7';
  div.style.padding = '10px';
  div.style.borderRadius = '5px';
  div.style.display = 'flex';
  div.style.flexDirection = 'column';

  var leyendas = [
      { icon: 'marker-icon-yellow.png', text: 'Asignado' },
      { icon: 'marker-icon-green.png', text: 'En ejecución' },
      { icon: 'marker-icon-blue.png', text: 'Conlcuido' },
      { icon: 'marker-icon-gris.png', text: 'Suspendido' },
      { icon: 'marker-icon-red.png', text: 'Cancelado' },
  ];

  // div.innerHTML += '<h4>LEYENDA</h4>';
  leyendas.forEach(function(leyenda) {
      var item = L.DomUtil.create('div', '', div);
      item.style.display = 'flex';
      item.style.alignItems = 'center';
      item.style.marginBottom = '5px';
      item.innerHTML = '<img src="' + static_url + 'leaflet/images/' + leyenda.icon + '" alt="' + leyenda.text + '" width: 15px; height: 24px; margin-right: 5px;">' + leyenda.text;
  });

  return div;
};

// Añadir el control de leyenda al mapa
legendControl.addTo(map);


map.on('moveend', () => {
  localStorage.theZoom = map.getZoom();
  var centro = map.getCenter();
  localStorage.lat = centro.lat;
  localStorage.lon = centro.lng;
});


var asignadoAJ=0, asignadoMER=0, 
ejecucionAJ=0, ejecucionMER=0, 
terminadoAJ=0, terminadoMER=0, 
postergadoAJ=0, postergadoMER=0, 
canceladoAJ=0, canceladoMER=0,
hormigonadoAJ=0, hormigonadoMER=0,
montadoAJ=0, montadoMER=0;

sitios.forEach(e => {
  e['contratista'] === 'AJ' ? asignadoAJ++ : asignadoMER++;
  if (e['contratista'] === 'AJ') {
    if (e['avance__estado'] === 'EJE') {ejecucionAJ++}
    if (e['avance__estado'] === 'TER') {terminadoAJ++}
    if (e['avance__estado'] === 'PTG') {postergadoAJ++}
    if (e['avance__estado'] === 'CAN') {canceladoAJ++}
    if (e['avance__hormigonado'] !== '' ) {hormigonadoAJ++}
    if (e['avance__montado'] !== '' ) {montadoAJ++} 

  } else {
    if (e['avance__estado'] === 'EJE') {ejecucionMER++}
    if (e['avance__estado'] === 'TER') {terminadoMER++}
    if (e['avance__estado'] === 'PTG') {postergadoMER++}
    if (e['avance__estado'] === 'CAN') {canceladoMER++}
    if (e['avance__hormigonado'] !== '' ) {hormigonadoMER++}
    if (e['avance__montado'] !== '' ) {montadoMER++}
  }
});

// Crear el contenedor para la tabla
var container = L.DomUtil.create('div');


    container.innerHTML = `
    <table class="text-xs">
    <thead>
      <tr>
        <th class="text-left"></th>
        <th class="min-w-8">AJ</th>
        <th class="min-w-8">MER</th>
        <th>TOTAL</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td class="text-left">Asignado</td>
        <td>${asignadoAJ}</td>
        <td>${asignadoMER}</td>
        <td>${asignadoMER + asignadoAJ}</td>
      </tr>
      <tr>
        <td class="text-left">En ejecución</td>
        <td>${ejecucionAJ}</td>
        <td>${ejecucionMER}</td>
        <td>${ejecucionAJ + ejecucionMER}</td>
      </tr>
      <tr>
        <td class="text-left">Hormigonado</td>
        <td>${hormigonadoAJ}</td>
        <td>${hormigonadoMER}</td>
        <td>${hormigonadoAJ + hormigonadoMER}</td>
      </tr>
      <tr>
        <td class="text-left">Montaje</td>
        <td>${montadoAJ}</td>
        <td>${montadoMER}</td>
        <td>${montadoAJ + montadoMER}</td>
      </tr>
      <tr>
        <td class="text-left">Concluido</td>
        <td>${terminadoAJ}</td>
        <td>${terminadoMER}</td>
        <td>${terminadoAJ + terminadoMER}</td>
      </tr>
      <tr>
        <td class="text-left">Suspendido</td>
        <td>${postergadoAJ}</td>
        <td>${postergadoMER}</td>
        <td>${postergadoAJ + postergadoMER}</td>
      </tr>
      <tr>
        <td class="text-left">Cancelado</td>
        <td>${canceladoAJ}</td>
        <td>${canceladoMER}</td>
        <td>${canceladoAJ + canceladoMER}</td>
      </tr>
    </tbody>
  </table>
  
  
  `;

// Estilizar el contenedor si es necesario
container.style.backgroundColor = "white";
container.style.padding = "10px";

// Crear un control personalizado
var customControl = L.control({position: 'bottomleft'});

// Función para cuando se añade el control al mapa
customControl.onAdd = function(map) {
    return container;
};

// Añadir el control personalizado al mapa
customControl.addTo(map)
  


// Sistema de bsuqueda
document.addEventListener("DOMContentLoaded", function() {
  const data = [
      // Tu lista de objetos aquí
  ];

  const searchField = document.getElementById('searchField');
  const results = document.getElementById('results');

  searchField.addEventListener('input', function() {
      const searchTerm = this.value.toLowerCase();
      const filteredData = data.filter(item => item.sitio.toLowerCase().includes(searchTerm) ||
                                                item.entel_id.toLowerCase().includes(searchTerm));
      
      results.innerHTML = '';
      
      filteredData.forEach(item => {
          const optionElement = document.createElement('option');
          optionElement.value = item.entel_id;
          optionElement.textContent = `${item.sitio} (${item.entel_id})`;
          results.appendChild(optionElement);
      });
  });

  results.addEventListener('change', function() {
      const selectedItem = data.find(item => item.entel_id === this.value);
      if (selectedItem) {
          console.log(`Coordenadas de ${selectedItem.sitio}: lat ${selectedItem.lat}, lon ${selectedItem.lon}`);
      }
  });
});




// Buscador
document.getElementById('buscador').addEventListener('input', function() {
  const query = this.value;
  const resultadosElement = document.getElementById('resultados');
  resultadosElement.innerHTML = ''; // Limpiar resultados anteriores

  if(query.length > 2){ // Para empezar a buscar después de 2 caracteres
    fetch(`/buscar_sitio/?q=${query}`)
    .then(response => {
        if (!response.ok) {
            throw new Error('La respuesta de la red no fue ok');
        }
        return response.json();
    })
    .then(data => {
      data.forEach(sitio => {
          const li = document.createElement('li');
          li.textContent = `${sitio.nombre} (${sitio.sitio} - ${sitio.entel_id})`;
          li.addEventListener('click', () => {
              console.log(`Lat: ${sitio.lat}, Lon: ${sitio.lon}`);
              map.flyTo([sitio.lat, sitio.lon], 12, {
                animate: true,
                duration: 2 // Duración de la animación en segundos, ajustable.
              });
              resultadosElement.innerHTML = '';
              buscador.value = '';
          });
          resultadosElement.appendChild(li);
      });
    })
    .catch(error => {
      console.error('Hubo un problema con la operación fetch:', error);
    });
  }
});





});