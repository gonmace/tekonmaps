
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
      'OpenStreetMap_Dark': OpenStreetMap_Dark,
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
      if (e['estado'] === 'ASG') {
        selectedIcon = yellowIcon;
      } else if (e['estado'] === 'EJE') {
        selectedIcon = greenIcon;
      } else if (e['estado'] === 'PTG') {
        selectedIcon = grayIcon;
      } else if (e['estado'] === 'CAN') {
        selectedIcon = redIcon;
      } else {
        selectedIcon = blueIcon;
      }

      var marker = L.marker([e['lat'], e['lon']], {
        icon: selectedIcon, // Asegúrate de que selectedIcon esté definido
        title: e['comuna'],
        contratista: e.contratista // Asegúrate de tener esta propiedad en tus datos
      });

      marker.bindTooltip(e['cod'], {permanent: true}).openTooltip();

    // Definiendo las rutas a los íconos
    var checkIconPath = static_url+'img/check.png';
    var crossIconPath = static_url+'img/cross.png';

    var progressValue = e['avance']; // Este es el valor de progreso. Reemplázalo con tu valor dinámico

    var popupContent = `
    <div>
    <strong> ${e['cod']} ${e['comuna']} - ${e['contratista']} </strong>
    <p>${e['descripcion']}</p>
    <div class="flex items-center mb-1">
        <img src="${e['hormigonado'] ? checkIconPath : crossIconPath}" alt="Cross" class="w-3 h-3 mr-1"> Hormigonado
    </div>
    <div class="flex items-center mb-1">
        <img src="${e['montado'] ? checkIconPath : crossIconPath}" alt="Check" class="w-3 h-3 mr-1"> Montado
    </div>
    <div class="flex items-center mb-1">
      <img src="${e['empalmeE'] ? checkIconPath : crossIconPath}" alt="Check" class="w-3 h-3 mr-1"> Empalme Electrico
    </div>
    <div class="flex items-center mb-1">
      Fecha Entrega: <b>${e['fechaFin']} </b>
    </div>
    <div class="flex items-center">
        <div class="w-full h-4 bg-gray-200 rounded-full overflow-hidden relative mr-2">
            <div class="h-full bg-red-400 rounded-full" style="width: ${progressValue}%;"></div>
        </div>
        <span>${progressValue}%</span>
    </div>
    <a href="/media/pdfs/${e['cod']}.pdf" class="text-blue-500 hover:text-blue-700" download>Descargar Reporte</a>
</div>
  `;
    // <iframe src="/media/pdfs/${e['cod']}.pdf" width="600" height="400"></iframe>
  // <a href="#" class="text-blue-500 hover:text-blue-700" onclick="openPdfModal('static/reportes/${e['cod']}.pdf')">Ver Reporte</a>
  marker.bindPopup(popupContent);
      
      if (e.contratista == 'AJ') {
        ajgroup.addLayer(marker);
      } else {
        mergroup.addLayer(marker);
      }
      allMarkers.push(marker);
    });
    
// Función para reagregar marcadores
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
var radiusControl = L.control({ position: 'topright' });
radiusControl.onAdd = function (map) {
    var div = L.DomUtil.create('div', 'leaflet-control leaflet-bar radius-control');
    div.innerHTML = `
        <div class="leaflet-control-container" background-color: white; padding: 5px; border-radius: 4px;">
            <label for="radiusSlider">Radio del Cluster:</label>
            <input type="range" id="radiusSlider" min="10" max="500" value="150" />
            <span id="radiusValue">20</span>
        </div>
    `;
    return div;
};
radiusControl.addTo(map);
// Función para actualizar el valor mostrado
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
      { icon: 'marker-icon-gris.png', text: 'Postergado' },
      { icon: 'marker-icon-red.png', text: 'Cancelado' },
  ];

  div.innerHTML += '<h4>LEYENDA</h4>';
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
    if (e['estado'] === 'EJE') {ejecucionAJ++}
    if (e['estado'] === 'TER') {terminadoAJ++}
    if (e['estado'] === 'PTG') {postergadoAJ++}
    if (e['estado'] === 'CAN') {canceladoAJ++}
    if (e['hormigonado'] === 1 ) {hormigonadoAJ++}
    if (e['montado'] === 1 ) {montadoAJ++} 

  } else {
    if (e['estado'] === 'EJE') {ejecucionMER++}
    if (e['estado'] === 'TER') {terminadoMER++}
    if (e['estado'] === 'PTG') {postergadoMER++}
    if (e['estado'] === 'CAN') {canceladoMER++}
    if (e['hormigonado'] === 1 ) {hormigonadoMER++}
    if (e['montado'] === 1 ) {montadoMER++}
  }
});

// Crear el contenedor para la tabla
var container = L.DomUtil.create('div');


    container.innerHTML = `
    <table>
      <td></td>
      <td>AJ</td>
      <td>MER</td>
      <td>TOTAL</td>
    </tr>
    <tr>
      <td> Asignado</td>
      <td>${asignadoAJ}</td>
      <td>${asignadoMER}</td>
      <td>${asignadoMER + asignadoAJ}</td>
    </tr>
    <tr>
      <td>Ejecutandose</td>
      <td>${ejecucionAJ}</td>
      <td>${ejecucionMER}</td>
      <td>${ejecucionAJ + ejecucionMER}</td>
    </tr>
    <tr>
      <td>Concluido</td>
      <td>${terminadoAJ}</td>
      <td>${terminadoMER}</td>
      <td>${terminadoAJ + terminadoMER}</td>
    </tr>
    <tr>
      <td>Postergado</td>
      <td>${postergadoAJ}</td>
      <td>${postergadoMER}</td>
      <td>${postergadoAJ + postergadoMER}</td>
    </tr>
    <tr>
      <td>Cancelado</td>
      <td>${canceladoAJ}</td>
      <td>${canceladoMER}</td>
      <td>${canceladoAJ + canceladoMER}</td>
    </tr>
    <tr>
    </tr>
    <tr>
      <td>Hormigonado</td>
      <td>${hormigonadoAJ}</td>
      <td>${hormigonadoMER}</td>
      <td>${hormigonadoAJ + hormigonadoMER}</td>
    </tr>
    <td>Montaje</td>
      <td>${montadoAJ}</td>
      <td>${montadoMER}</td>
      <td>${montadoAJ + montadoMER}</td>
    </tr>
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
  






});