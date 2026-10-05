//
// Global map.js variables
//

var $selectExcludeLocations
var $selectStyle
var $selectIconSize
var $selectLocationIconMarker
var $switchAccountSidebar
var $switchLocationSidebar

const language = document.documentElement.lang === '' ? 'en' : document.documentElement.lang
var idToOccupierType = {}
var i8lnDictionary = {}
var languageLookups = 0
var languageLookupThreshold = 3

var searchMarkerStyles

var timestamp
var excludedLocations = []

var buffer = []

var map
var MapProvider
var markerCluster = window.markerCluster = {}
var rawDataIsLoading = false
var searchMarker
var storeZoom = true

var oSwLat
var oSwLng
var oNeLat
var oNeLng

var lastaccounts
var lastlocations

var polygons = []

var selectedStyle = 'light'

var updateWorker
var lastUpdateTime
var redrawTimeout = null

var dataIsBeingRemovedFromMap = false

//
// Functions
//

function latOf(point) {
    return typeof point.lat === 'function' ? point.lat() : point.lat
}

function lngOf(point) {
    return typeof point.lng === 'function' ? point.lng() : point.lng
}

function leafletOverlaySetMap(value) {
    if (value) {
        if (!this._onMap) {
            this.addTo(map)
            this._onMap = true
        }
    } else if (this._onMap) {
        map.removeLayer(this)
        this._onMap = false
    }
}

function leafletOverlayGetMap() {
    return this._onMap ? map : null
}

function leafletMarkerSetIcon(opts) {
    var size = opts.scaledSize
    L.Marker.prototype.setIcon.call(this, L.icon({
        iconUrl: opts.url,
        iconSize: [size.width, size.height],
        iconAnchor: [size.width / 2, size.height / 2]
    }))
}

function leafletMarkerSetPosition(latlng) {
    this.setLatLng(latlng)
}

function leafletMarkerGetPosition() {
    return this.getLatLng()
}

function leafletMarkerSetZIndex(z) {
    this.setZIndexOffset(z * 1000)
}

function leafletMarkerAddListener(event, handler) {
    var eventMap = {click: 'click', mouseover: 'mouseover', mouseout: 'mouseout'}
    this.on(eventMap[event] || event, handler)
}

function createLeafletMarker(lat, lng) {
    var marker = L.marker([lat, lng])
    marker._onMap = false

    marker.setIcon = leafletMarkerSetIcon
    marker.setPosition = leafletMarkerSetPosition
    marker.getPosition = leafletMarkerGetPosition
    marker.setZIndex = leafletMarkerSetZIndex
    marker.setMap = leafletOverlaySetMap
    marker.getMap = leafletOverlayGetMap
    marker.addListener = leafletMarkerAddListener

    marker.infoWindow = createLeafletInfoWindow(marker)

    return marker
}

function leafletInfoWindowSetContent(html) {
    this.marker.setPopupContent(html)
}

function leafletInfoWindowOpen() {
    this.marker.openPopup()
}

function leafletInfoWindowClose() {
    this.marker.closePopup()
}

function leafletInfoWindowOnCloseClick(handler) {
    this.marker.on('popupclose', handler)
}

function createLeafletInfoWindow(marker) {
    marker.bindPopup('', {autoPan: false})
    return {
        marker: marker,
        setContent: leafletInfoWindowSetContent,
        open: leafletInfoWindowOpen,
        close: leafletInfoWindowClose,
        onCloseClick: leafletInfoWindowOnCloseClick
    }
}

function leafletCircleSetOptions(opts) {
    this.setStyle({color: opts.fillColor, fillColor: opts.fillColor})
}

function createLeafletCircle(lat, lng, options) {
    var circle = L.circle([lat, lng], {
        radius: options.radius,
        interactive: false,
        color: options.fillColor,
        weight: 1,
        opacity: 0.5,
        fillColor: options.fillColor,
        fillOpacity: 0.1
    })
    circle._onMap = false

    circle.setMap = leafletOverlaySetMap
    circle.getMap = leafletOverlayGetMap
    circle.setOptions = leafletCircleSetOptions

    return circle
}
function leafletRectangleSetOptions(opts) {
    this.setStyle({color: opts.fillColor, fillColor: opts.fillColor})
}

function createLeafletRectangle(ne_lat, sw_lat, ne_lng, sw_lng, options) {
    var rectangle = L.rectangle([[sw_lat, sw_lng], [ne_lat, ne_lng]], {
        interactive: false,
        color: options.fillColor,
        weight: 1,
        opacity: 0.5,
        fillColor: options.fillColor,
        fillOpacity: 0.1
    })
    rectangle._onMap = false

    rectangle.setMap = leafletOverlaySetMap
    rectangle.getMap = leafletOverlayGetMap
    rectangle.setOptions = leafletRectangleSetOptions

    return rectangle
}

function buildLeafletMapProvider() {
    return {
        createMarker: function (lat, lng) {
            var marker = createLeafletMarker(lat, lng)
            marker.setMap(map)
            return marker
        },
        createCircle: function (lat, lng, options) {
            var circle = createLeafletCircle(lat, lng, options)
            circle.setMap(map)
            return circle
        },
        createRectangle: function (ne_lat, sw_lat, ne_lng, sw_lng, options) {
            var rectangle = createLeafletRectangle(ne_lat, sw_lat, ne_lng, sw_lng, options)
            rectangle.setMap(map)
            return rectangle
        },
        makeSize: function (width, height) {
            return {width: width, height: height}
        },
        latLng: function (lat, lng) {
            return L.latLng(lat, lng)
        },
        setView: function (lat, lng, zoom) {
            map.setView([lat, lng], zoom || map.getZoom())
        },
        addControl: function (element) {
            var LocationControl = L.Control.extend({
                options: {position: 'bottomright'},
                onAdd: function () {
                    return element
                }
            })
            map.addControl(new LocationControl())
        }
    }
}

function buildGoogleMapProvider() {
    return {
        createMarker: function (lat, lng) {
            var marker = new google.maps.Marker({
                position: {lat: lat, lng: lng},
                map: map
            })
            marker.infoWindow = new google.maps.InfoWindow({
                content: '',
                disableAutoPan: true
            })
            marker.infoWindow.onCloseClick = function (handler) {
                google.maps.event.addListener(marker.infoWindow, 'closeclick', handler)
            }
            return marker
        },
        createCircle: function (lat, lng, options) {
            return new google.maps.Circle({
                map: map,
                clickable: false,
                center: new google.maps.LatLng(lat, lng),
                radius: options.radius,
                fillColor: options.fillColor,
                fillOpacity: 0.1,
                strokeWeight: 1,
                strokeOpacity: 0.5
            })
        },
        createRectangle: function (ne_lat, sw_lat, ne_lng, sw_lng, options) {
            return new google.maps.Rectangle({
                map: map,
                clickable: false,
                fillColor: options.fillColor,
                fillOpacity: 0.1,
                strokeWeight: 1,
                strokeOpacity: 0.5,
                bounds: {
                    north: ne_lat,
                    south: sw_lat,
                    east: ne_lng,
                    west: sw_lng,
                }
            })
        },
        makeSize: function (width, height) {
            return new google.maps.Size(width, height)
        },
        latLng: function (lat, lng) {
            return new google.maps.LatLng(lat, lng)
        },
        setView: function (lat, lng, zoom) {
            map.setCenter(new google.maps.LatLng(lat, lng))
            if (zoom) {
                map.setZoom(zoom)
            }
        },
        addControl: function (element) {
            element.index = 1
            map.controls[google.maps.ControlPosition.RIGHT_BOTTOM].push(element)
        }
    }
}

function excludeLocation(id) { // eslint-disable-line no-unused-vars
    $selectExcludeLocations.val(
        $selectExcludeLocations.val().concat(String(id))
    ).trigger('change')
}

function getIconSizeBasedOnZoom(iconSize){
    var defaultZoom = 17

    var zoom = map.getZoom()

    let newIconSize = iconSize - 12 * (defaultZoom - zoom)

    if (newIconSize < 10) {
        newIconSize = 10
    } else if (newIconSize > 96) {
        newIconSize = 96
    }

    return newIconSize
}

function createServiceWorkerReceiver() {
    navigator.serviceWorker.addEventListener('message', function (event) {
        const data = JSON.parse(event.data)
        if (data.action === 'centerMap' && data.lat && data.lon) {
            centerMap(data.lat, data.lon, 20)
        }
    })
}

function initMap() { // eslint-disable-line no-unused-vars
    var initialLat = Number(getParameterByName('lat')) || centerLat
    var initialLng = Number(getParameterByName('lon')) || centerLng
    var initialZoom = Number(getParameterByName('zoom')) || Store.get('zoomLevel')

    if (useLeaflet()) {
        map = L.map('map', {
            center: [initialLat, initialLng],
            zoom: initialZoom
        })

        map._activeTileLayers = []
        map._activeMapTypeId = null
        map.setMapTypeId = function (id) {
            if (id === this._activeMapTypeId) {
                return
            }
            this._activeMapTypeId = id

            var self = this
            this._activeTileLayers.forEach(function (layer) {
                self.removeLayer(layer)
            })
            this._activeTileLayers = []

            var style = leafletTileStyles[id] || leafletTileStyles['style_merchant']
            style.layers.forEach(function (url) {
                var layer = L.tileLayer(url, {attribution: style.attribution, maxZoom: style.maxZoom})
                layer.addTo(self)
                self._activeTileLayers.push(layer)
            })
        }
        map.addListener = function (googleEventName, handler) {
            var eventMap = {idle: 'moveend', zoom_changed: 'zoomend', dragend: 'dragend'}
            var leafletEvent = eventMap[googleEventName]
            if (leafletEvent) {
                this.on(leafletEvent, handler)
            }
        }

        markerCluster = {repaint: function () {}, redraw: function () {}}

        MapProvider = buildLeafletMapProvider()
        map.setMapTypeId(Store.get('map_style'))
    } else {
        map = new google.maps.Map(document.getElementById('map'), {
            center: {
                lat: initialLat,
                lng: initialLng
            },
            zoom: initialZoom,
            gestureHandling: 'greedy',
            fullscreenControl: true,
            streetViewControl: false,
            mapTypeControl: false,
            clickableIcons: false,
            mapTypeControlOptions: {
                style: google.maps.MapTypeControlStyle.DROPDOWN_MENU,
                position: google.maps.ControlPosition.RIGHT_TOP,
                mapTypeIds: [
                    google.maps.MapTypeId.ROADMAP,
                    google.maps.MapTypeId.SATELLITE,
                    google.maps.MapTypeId.HYBRID,
                    'style_merchant',
                ]
            }
        })

        // Enable clustering.
        var clusterOptions = {
            imagePath: 'static/images/cluster/m',
            maxZoom: Store.get('maxClusterZoomLevel'),
            zoomOnClick: Store.get('clusterZoomOnClick'),
            gridSize: Store.get('clusterGridSize')
        }

        markerCluster = new MarkerClusterer(map, [], clusterOptions)

        var styleMerchant = new google.maps.StyledMapType(merchantStyle, {
            name: 'Merchant Map'
        })
        map.mapTypes.set('style_merchant', styleMerchant)

        map.addListener('maptypeid_changed', function (s) {
            Store.set('map_style', this.mapTypeId)
        })

        MapProvider = buildGoogleMapProvider()
        map.setMapTypeId(Store.get('map_style'))
    }

    map.addListener('idle', updateMap)

    map.addListener('zoom_changed', function () {
        if (storeZoom === true) {
            Store.set('zoomLevel', map.getZoom())
        } else {
            storeZoom = true
        }

        // User scrolled again, reset our timeout.
        if (redrawTimeout) {
            clearTimeout(redrawTimeout)
            redrawTimeout = null
        }

        // Don't redraw constantly even if the user scrolls multiple times,
        // just add it on a timer.
        redrawTimeout = setTimeout(function () {
            // We're done processing the list. Repaint.
            markerCluster.repaint()
        }, 500)
    })

    createMyLocationButton()
    initSidebar()

    if (Push._agents.chrome.isSupported()) {
        createServiceWorkerReceiver()
    }
}

function bootstrapMapProvider() { // eslint-disable-line no-unused-vars
    if (useLeaflet()) {
        initMap()
    }
}

var searchControlURI = 'search_control'

function searchControl(action) {
    $.post(searchControlURI + '?action=' + encodeURIComponent(action))
    $('#scan-here').toggleClass('disabled', action === 'off')
}

function updateSearchStatus() {
    $.getJSON(searchControlURI).then(function (data) {
        $('#search-switch').prop('checked', data.status)
        $('#scan-here').toggleClass('disabled', !data.status)
    })
}

function initSidebar() {
    $('#accounts-switch').prop('checked', Store.get('showAccounts'))
    $('#account-sidebar-switch').prop('checked', Store.get('useAccountSidebar'))
    $('#account-sidebar-wrapper').toggle(Store.get('showAccounts'))

    $('#locations-switch').prop('checked', Store.get('showLocations'))
    $('#location-sidebar-switch').prop('checked', Store.get('useLocationSidebar'))
    $('#location-sidebar-wrapper').toggle(Store.get('showLocations'))
    $('#locations-filter-wrapper').toggle(Store.get('showLocations'))

    $('#geoloc-switch').prop('checked', Store.get('geoLocate'))
    $('#lock-marker-switch').prop('checked', Store.get('lockMarker'))
    $('#start-at-user-location-switch').prop('checked', Store.get('startAtUserLocation'))
    $('#follow-my-location-switch').prop('checked', Store.get('followMyLocation'))
    $('#map-service-provider').val(Store.get('mapServiceProvider'))
    $('#scanned-switch').prop('checked', Store.get('showScanned'))
}

function getTypeSpan(type) {
    return `<span style='padding: 2px 5px; text-transform: uppercase; color: white; margin-right: 2px; border-radius: 4px; font-size: 0.6em; vertical-align: middle; background-color: ${type['color']}'>${type['type']}</span>`
}

function openMapDirections(lat, lng) { // eslint-disable-line no-unused-vars
    var url = ''
    if (Store.get('mapServiceProvider') === 'googlemaps') {
        url = 'https://maps.google.com/maps?daddr=' + lat + ',' + lng
        window.open(url, '_blank')
    } else if (Store.get('mapServiceProvider') === 'applemaps') {
        url = 'https://maps.apple.com/maps?daddr=' + lat + ',' + lng
        window.open(url, '_self')
    }
}

// Converts timestamp to readable String
function getDateStr(t) {
    var dateStr = 'Unknown'
    if (t) {
        dateStr = moment(t).fromNow()
    }
    return dateStr
}

function accountLabel(account) {
    var str

    var latitude = account['latitude']
    var longitude = account['longitude']

    const lastScannedStr = getDateStr(account.last_scanned)

    var iconSrc = "static/images/markers/male.png"
    if (account.sprite) {
        iconSrc = account.sprite;
    }
    let titleText = account.username ? account.username : 'Unknown Account'
    let imgSrc = iconSrc

    var uuid = account['uuid']

    let accountIcon = `<img class='account account-icon sprite' src='${iconSrc}'>`

    str = `
            <div>
              <div class='account name'>
                  <span>${titleText}</span><br/>
              </div>
              <div>
                ${accountIcon}
                <img class='account img sprite' src='${imgSrc}'>
              </div>
              <div class='account container'>
                <div class='account info navigate'>
                  <a href='javascript:void(0);' onclick='javascript:openMapDirections(${latitude},${longitude});' title='Open in Google Maps'>${latitude.toFixed(6)}, ${longitude.toFixed(7)}</a>
                </div>
                <div class='account info last-scanned'>
                  Last Scanned: ${lastScannedStr}
                </div>
              </div>
            </div>`

    return str
}

function locationLabel(location) {
    var str

    var latitude = location['latitude']
    var longitude = location['longitude']

    const lastScannedStr = getDateStr(location.last_scanned)

    var iconSrc = "static/images/markers/compass.png"
    let titleText = 'Land type: ' + location.land_type_id
    if (location.land_type_name) {
        titleText += ' ' + location.land_type_name;
    }
    if (location.name) {
        titleText += ' Name: ' + location.name;
    }
    titleText += ' (ID: ' + location.uuid + ')';
    let districtText = 'District: ' + location.district_id;
    let occupationText = 'Occupation: ' + location.occupation_id;

    let ownerText = "Free location";
    if (location.player_name) {
        ownerText = location.player_name;
        iconSrc = "static/images/markers/tribe.png"
        if (location.player_id) {
            ownerText += ' (' + location.player_id + ')';
            iconSrc = "static/images/markers/settlement.png"
        }
        if (location.owned) {
            ownerText += ' (Owned)';
        }
    }

    if (location.sprite) {
        iconSrc = location.sprite;
    }

    let imgSrc = iconSrc

    var uuid = location['uuid']

    let locationIcon = `<img class='location location-icon sprite' src='${iconSrc}'>`

    str = `
            <div>
              <div class='location name'>
                  <span>${titleText}</span><br/>
                  <span>${ownerText}</span><br/>
                  <span>${districtText}</span><br/>
                  <span>${occupationText}</span><br/>
              </div>
              <div>
                ${locationIcon}
                <img class='location img sprite' src='${imgSrc}'>
              </div>
              <div class='location container'>
                <div class='location info navigate'>
                  <a href='javascript:void(0);' onclick='javascript:openMapDirections(${latitude},${longitude});' title='Open in Google Maps'>${latitude.toFixed(6)}, ${longitude.toFixed(7)}</a>
                </div>
                <div class='location info last-scanned'>
                  Last Scanned: ${lastScannedStr}
                </div>
                <div>
                    <span class='location links exclude'><a href='javascript:excludeLocation(${location.occupation_id})'>Exclude</a></span>
                </div>
              </div>
            </div>`

    return str
}

function updateAccountMarker(item, marker) {
    var icon = "static/images/markers/male.png"
    if (item['sprite']) {
        icon = item['sprite'];
    }
    let markerImage = icon

    let markersize = 48
    markersize = getIconSizeBasedOnZoom(markersize)
    marker.setIcon({
        url: markerImage,
        scaledSize: MapProvider.makeSize(markersize, markersize)
    })

    marker.setZIndex(2)

    marker.setPosition({lat: item['latitude'], lng: item['longitude']})

    let needToReCenterMap = false
    let playeridparam = getParameterByName('playerid')
    let holdlocationparam = getParameterByName('hold')
    if (playeridparam != null && holdlocationparam == null && playeridparam == item['uuid']) {
        let currentMapCenter = getMapCenter()

        if (item['latitude'].toFixed(5) != currentMapCenter['lat'].toFixed(5)) {
            needToReCenterMap = true
        }

        if (item['longitude'].toFixed(5) != currentMapCenter['lng'].toFixed(5)) {
            needToReCenterMap = true
        }
    }

    if (needToReCenterMap){
        centerMap(item['latitude'], item['longitude'], null)
    }

    marker.infoWindow.setContent(accountLabel(item))
    return marker
}

function updateLocationMarker(item, marker) {
    var icon = "static/images/markers/compass.png"

    if (item['player_name']) {
        icon = "static/images/markers/tribe.png"
        if (item['player_id']) {
            icon = "static/images/markers/settlement.png"
        }
    }

    if (item['sprite']) {
        icon = item['sprite'];
    }

    let markerImage = icon

    let markersize = 90
    markersize = getIconSizeBasedOnZoom(markersize)
    marker.setIcon({
        url: markerImage,
        scaledSize: MapProvider.makeSize(markersize, markersize)
    })

    marker.setZIndex(2)

    marker.setPosition({lat: item['latitude'], lng: item['longitude']})

    marker.infoWindow.setContent(locationLabel(item))
    return marker
}

function setupAccountMarker(item) {
    var marker = MapProvider.createMarker(item['latitude'], item['longitude'])
    updateAccountMarker(item, marker)
    if (Store.get('useAccountSidebar')) {
        marker.addListener('click', function () {
            var accountSidebar = document.querySelector('#account-details')
            if (accountSidebar.getAttribute('data-id') === item['uuid'] && accountSidebar.classList.contains('visible')) {
                accountSidebar.classList.remove('visible')
            } else {
                accountSidebar.setAttribute('data-id', item['uuid'])
                showAccountDetails(item['uuid'])
            }
        })

        marker.infoWindow.onCloseClick(function () {
            marker.persist = null
        })

        if (!isMobileDevice() && !isTouchDevice()) {
            marker.addListener('mouseover', function () {
                marker.infoWindow.open(map, marker)
                clearSelection()
                updateLabelDiffTime()
            })
        }

        marker.addListener('mouseout', function () {
            if (!marker.persist) {
                marker.infoWindow.close()
            }
        })
    } else {
        addListeners(marker)
    }
    return marker
}

function setupLocationMarker(item) {
    var marker = MapProvider.createMarker(item['latitude'], item['longitude'])
    updateLocationMarker(item, marker)
    if (Store.get('useLocationSidebar')) {
        marker.addListener('click', function () {
            var locationSidebar = document.querySelector('#location-details')
            if (locationSidebar.getAttribute('data-id') === item['uuid'] && locationSidebar.classList.contains('visible')) {
                locationSidebar.classList.remove('visible')
            } else {
                locationSidebar.setAttribute('data-id', item['uuid'])
                showLocationDetails(item['uuid'])
            }
        })

        marker.infoWindow.onCloseClick(function () {
            marker.persist = null
        })

        if (!isMobileDevice() && !isTouchDevice()) {
            marker.addListener('mouseover', function () {
                marker.infoWindow.open(map, marker)
                clearSelection()
                updateLabelDiffTime()
            })
        }

        marker.addListener('mouseout', function () {
            if (!marker.persist) {
                marker.infoWindow.close()
            }
        })
    } else {
        addListeners(marker)
    }
    return marker
}

function showAccountDetails(id) { // eslint-disable-line no-unused-vars
    var sidebar = document.querySelector('#account-details')
    var sidebarClose

    sidebar.classList.add('visible')

    var data = $.ajax({
        url: 'account_data',
        type: 'GET',
        data: {
            'id': id
        },
        dataType: 'json',
        cache: false
    })

    data.done(function (result) {
        var topPart = accountLabel(result, true, false)
        sidebar.innerHTML = `${topPart}`

        sidebarClose = document.createElement('a')
        sidebarClose.href = '#'
        sidebarClose.className = 'close'
        sidebarClose.tabIndex = 0
        sidebar.appendChild(sidebarClose)

        sidebarClose.addEventListener('click', function (event) {
            event.preventDefault()
            event.stopPropagation()
            sidebar.classList.remove('visible')
        })
    })
}

function showLocationDetails(id) { // eslint-disable-line no-unused-vars
    var sidebar = document.querySelector('#location-details')
    var sidebarClose

    sidebar.classList.add('visible')

    var playeridparam = getParameterByName('playerid')

    var data = $.ajax({
        url: 'location_data',
        type: 'GET',
        data: {
            'id': id,
            'playerid': playeridparam,
        },
        dataType: 'json',
        cache: false
    })

    data.done(function (result) {
        var topPart = locationLabel(result, true, false)
        sidebar.innerHTML = `${topPart}`

        sidebarClose = document.createElement('a')
        sidebarClose.href = '#'
        sidebarClose.className = 'close'
        sidebarClose.tabIndex = 0
        sidebar.appendChild(sidebarClose)

        sidebarClose.addEventListener('click', function (event) {
            event.preventDefault()
            event.stopPropagation()
            sidebar.classList.remove('visible')
        })
    })
}

function lpad(str, len, padstr) {
    return Array(Math.max(len - String(str).length + 1, 0)).join(padstr) + str
}

function repArray(text, find, replace) {
    for (var i = 0; i < find.length; i++) {
        text = text.replace(find[i], replace[i])
    }

    return text
}

function getTimeUntil(time) {
    var now = Date.now()
    var tdiff = time - now

    var sec = Math.floor((tdiff / 1000) % 60)
    var min = Math.floor((tdiff / 1000 / 60) % 60)
    var hour = Math.floor((tdiff / (1000 * 60 * 60)) % 24)

    return {
        'total': tdiff,
        'hour': hour,
        'min': min,
        'sec': sec,
        'now': now,
        'ttime': time
    }
}

function polygonCenter(polygon) {
    var hyp, Lat, Lng

    var X = 0
    var Y = 0
    var Z = 0
    polygon.getPath().forEach(function (vertex, inex) {
        var lat
        var lng
        lat = vertex.lat() * Math.PI / 180
        lng = vertex.lng() * Math.PI / 180
        X += Math.cos(lat) * Math.cos(lng)
        Y += Math.cos(lat) * Math.sin(lng)
        Z += Math.sin(lat)
    })

    hyp = Math.sqrt(X * X + Y * Y)
    Lat = Math.atan2(Z, hyp) * 180 / Math.PI
    Lng = Math.atan2(Y, X) * 180 / Math.PI

    return new google.maps.LatLng(Lat, Lng)
}

function clearSelection() {
    if (document.selection) {
        document.selection.empty()
    }
}

function addListeners(marker) {
    marker.addListener('click', function () {
        if (!marker.infoWindowIsOpen) {
            marker.infoWindow.open(map, marker)
            clearSelection()
            updateLabelDiffTime()
            marker.persist = true
            marker.infoWindowIsOpen = true
        } else {
            marker.persist = null
            marker.infoWindow.close()
            marker.infoWindowIsOpen = false
        }
    })

    marker.infoWindow.onCloseClick(function () {
        marker.persist = null
    })

    if (!isMobileDevice() && !isTouchDevice()) {
        marker.addListener('mouseover', function () {
            marker.infoWindow.open(map, marker)
            clearSelection()
            updateLabelDiffTime()
        })
    }

    marker.addListener('mouseout', function () {
        if (!marker.persist) {
            marker.infoWindow.close()
        }
    })

    return marker
}

function clearStaleMarkers() {
    $.each(mapData.scanned, function (key, scanned) {
        // If older than 15mins remove
        if (scanned['last_modified'] < (new Date().getTime() - 15 * 60 * 1000)) {
            scanned.marker.setMap(null)
            delete mapData.scanned[key]
        }
    })

    $.each(mapData.locations, function (key, location) {
        const occupation_id = location['occupation_id']
        const isLocationExcluded = excludedLocations.indexOf(occupation_id) !== -1

        if (isLocationExcluded) {
            const oldMarker = location.marker

            if (oldMarker.rangeCircle) {
                oldMarker.rangeCircle.setMap(null)
                delete oldMarker.rangeCircle
            }

            oldMarker.setMap(null)
            delete mapData.locations[key]
            // Overwrite method to avoid all timing issues with libraries.
            oldMarker.setMap = function () {}
        }
    })
}

function showInBoundsMarkers(markers, type) {
    $.each(markers, function (key, value) {
        const item = markers[key]
        const marker = item.marker
        var show = false

        if (!item.hidden) {
            if (typeof marker.getBounds === 'function') {
                if (map.getBounds().intersects(marker.getBounds())) {
                    show = true
                }
            } else if (typeof marker.getPosition === 'function') {
                if (map.getBounds().contains(marker.getPosition())) {
                    show = true
                }
            }
        }

        if (show && !marker.getMap()) {
            marker.setMap(map)
            // Not all markers can be animated (ex: scan locations)
            if (marker.setAnimation && marker.oldAnimation) {
                marker.setAnimation(marker.oldAnimation)
            }
        } else if (!show && marker.getMap()) {
            // Not all markers can be animated (ex: scan locations)
            if (marker.getAnimation) {
                marker.oldAnimation = marker.getAnimation()
            }
            marker.setMap(null)
        }
    })
}

function loadRawData() {
    var loadScanned = Store.get('showScanned')
    var loadAccounts = Store.get('showAccounts')
    var loadLocations = Store.get('showLocations')

    var bounds = map.getBounds()
    var swPoint = bounds.getSouthWest()
    var nePoint = bounds.getNorthEast()
    var swLat = latOf(swPoint)
    var swLng = lngOf(swPoint)
    var neLat = latOf(nePoint)
    var neLng = lngOf(nePoint)

    var playeridparam = getParameterByName('playerid')

    return $.ajax({
        url: 'raw_data',
        type: 'GET',
        data: {
            'timestamp': timestamp,
            'accounts': loadAccounts,
            'lastaccounts': lastaccounts,
            'locations': loadLocations,
            'lastlocations': lastlocations,
            'scanned': loadScanned,
            'swLat': swLat,
            'swLng': swLng,
            'neLat': neLat,
            'neLng': neLng,
            'oSwLat': oSwLat,
            'oSwLng': oSwLng,
            'oNeLat': oNeLat,
            'oNeLng': oNeLng,
            'eids_locations': String(excludedLocations),
            'playerid': playeridparam
        },
        dataType: 'json',
        cache: false,
        beforeSend: function () {
            if (rawDataIsLoading) {
                return false
            } else {
                rawDataIsLoading = true
            }
        },
        error: function () {
            // Display error toast
            toastr['error']('Please check connectivity or reduce marker settings.', 'Error getting data')
            toastr.options = {
                'closeButton': true,
                'debug': false,
                'newestOnTop': true,
                'progressBar': false,
                'positionClass': 'toast-top-right',
                'preventDuplicates': true,
                'onclick': null,
                'showDuration': '300',
                'hideDuration': '1000',
                'timeOut': '25000',
                'extendedTimeOut': '1000',
                'showEasing': 'swing',
                'hideEasing': 'linear',
                'showMethod': 'fadeIn',
                'hideMethod': 'fadeOut'
            }
        },
        success: function(data) {
        },
        complete: function () {
            rawDataIsLoading = false
        }
    })
}

function processAccount(i, item) {
    if (!Store.get('showAccounts')) {
        return false
    }

    if (item['uuid'] in mapData.accounts) {
        item.marker = updateAccountMarker(item, mapData.accounts[item['uuid']].marker)
    }
    else {
        // add marker to map and item to dict
        item.marker = setupAccountMarker(item)
    }
    mapData.accounts[item['uuid']] = item
}

function processLocation(i, item) {
    if (!Store.get('showLocations')) {
        return false
    }

    var removeLocationFromMap = function (uuid) {
        if (mapData.locations[uuid] && mapData.locations[uuid].marker) {
            mapData.locations[uuid].marker.setMap(null)
            delete mapData.locations[uuid]
        }
    }

    var needToShow = true

    const isLocationExcluded = excludedLocations.indexOf(item['occupation_id']) !== -1
    if (isLocationExcluded) {
        needToShow = false
    }

    if (!needToShow) {
        removeLocationFromMap(item['uuid'])
        return true
    }

    if (item['uuid'] in mapData.locations) {
        item.marker = updateLocationMarker(item, mapData.locations[item['uuid']].marker)
    }
    else {
        // add marker to map and item to dict
        item.marker = setupLocationMarker(item)
    }
    mapData.locations[item['uuid']] = item
}

function updateAccounts() {
    if (!Store.get('showAccounts')) {
        return false
    }

    $.each(mapData.accounts, function (key, value) {
        value.marker = updateAccountMarker(value, value.marker)
    })
}

function updateLocations() {
    if (!Store.get('showLocations')) {
        return false
    }

    $.each(mapData.locations, function (key, value) {
        value.marker = updateLocationMarker(value, value.marker)
    })
}

function setupScannedMarker(item) {
    return MapProvider.createRectangle(item['ne_lat'], item['sw_lat'], item['ne_lng'], item['sw_lng'], {
        fillColor: getColorByDate(item['last_modified'])
    })
}

function processScanned(i, item) {
    if (!Store.get('showScanned')) {
        return false
    }

    var scanId = item['latitude'] + '|' + item['longitude']

    if (!(scanId in mapData.scanned)) { // add marker to map and item to dict
        if (item.marker) {
            item.marker.setMap(null)
        }
        item.marker = setupScannedMarker(item)
        mapData.scanned[scanId] = item
    } else {
        mapData.scanned[scanId].last_modified = item['last_modified']
    }
}

function updateScanned() {
    if (!Store.get('showScanned')) {
        return false
    }

    $.each(mapData.scanned, function (key, value) {
        if (map.getBounds().intersects(value.marker.getBounds())) {
            value.marker.setOptions({
                fillColor: getColorByDate(value['last_modified'])
            })
        }
    })
}

function getColorByDate(value) {
    // Changes the color from red to green over 15 mins
    var diff = (Date.now() - value) / 1000 / 60 / 15

    if (diff > 1) {
        diff = 1
    }

    // value from 0 to 1 - Green to Red
    var hue = ((1 - diff) * 120).toString(10)
    return ['hsl(', hue, ',100%,50%)'].join('')
}

function getMapCenter(){
    var loc = map.getCenter()
    return {lat : latOf(loc), lng : lngOf(loc)}
}

function updateMap() {
    loadRawData().done(function (result) {
        $.each(result.scanned, processScanned)
        showInBoundsMarkers(mapData.scanned, 'scanned')

        $.each(result.accounts, processAccount)
        showInBoundsMarkers(mapData.accounts, 'account')

        $.each(result.locations, processLocation)
        showInBoundsMarkers(mapData.locations, 'location')

        clearStaleMarkers()

        // We're done processing. Redraw.
        markerCluster.redraw()

        updateScanned()
        updateAccounts()
        updateLocations()

        oSwLat = result.oSwLat
        oSwLng = result.oSwLng
        oNeLat = result.oNeLat
        oNeLng = result.oNeLng

        lastaccounts = result.lastaccounts
        lastlocations = result.lastlocations

        timestamp = result.timestamp
        lastUpdateTime = Date.now()
    })
}

var updateLabelDiffTime = function () {
    $('.label-countdown').each(function (index, element) {
        var disappearsAt = getTimeUntil(parseInt(element.getAttribute('restocks-at')))

        var hours = disappearsAt.hour
        var minutes = disappearsAt.min
        var seconds = disappearsAt.sec
        var timestring = ''

        if (disappearsAt.ttime < disappearsAt.now) {
            timestring = '(expired)'
        } else {
            timestring = lpad(hours, 2, 0) + ':' + lpad(minutes, 2, 0) + ':' + lpad(seconds, 2, 0)
        }

        $(element).text(timestring)
    })
}

function getPointDistance(pointA, pointB) {
    return google.maps.geometry.spherical.computeDistanceBetween(pointA, pointB)
}

function createMyLocationButton() {
    var locationContainer = document.createElement('div')

    var locationButton = document.createElement('button')
    locationButton.style.backgroundColor = '#fff'
    locationButton.style.border = 'none'
    locationButton.style.outline = 'none'
    locationButton.style.width = '28px'
    locationButton.style.height = '28px'
    locationButton.style.borderRadius = '2px'
    locationButton.style.boxShadow = '0 1px 4px rgba(0,0,0,0.3)'
    locationButton.style.cursor = 'pointer'
    locationButton.style.marginRight = '10px'
    locationButton.style.padding = '0px'
    locationButton.title = 'My Location'
    locationContainer.appendChild(locationButton)

    var locationIcon = document.createElement('div')
    locationIcon.style.margin = '5px'
    locationIcon.style.width = '18px'
    locationIcon.style.height = '18px'
    locationIcon.style.backgroundImage = 'url(static/mylocation-sprite-1x.png)'
    locationIcon.style.backgroundSize = '180px 18px'
    locationIcon.style.backgroundPosition = '0px 0px'
    locationIcon.style.backgroundRepeat = 'no-repeat'
    locationIcon.id = 'current-location'
    locationButton.appendChild(locationIcon)

    locationButton.addEventListener('click', function () {
        centerMapOnLocation()
    })

    MapProvider.addControl(locationContainer)

    map.addListener('dragend', function () {
        var currentLocation = document.getElementById('current-location')
        currentLocation.style.backgroundPosition = '0px 0px'
    })
}

function centerMapOnLocation() {
    var currentLocation = document.getElementById('current-location')
    var imgX = '0'
    var animationInterval = setInterval(function () {
        if (imgX === '-18') {
            imgX = '0'
        } else {
            imgX = '-18'
        }
        currentLocation.style.backgroundPosition = imgX + 'px 0'
    }, 500)
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(function (position) {
            MapProvider.setView(position.coords.latitude, position.coords.longitude)
            Store.set('followMyLocationPosition', {
                lat: position.coords.latitude,
                lng: position.coords.longitude
            })
            clearInterval(animationInterval)
            currentLocation.style.backgroundPosition = '-144px 0px'
        })
    } else {
        clearInterval(animationInterval)
        currentLocation.style.backgroundPosition = '0px 0px'
    }
}

function centerMap(lat, lng, zoom) {
    if (zoom) {
        storeZoom = false
    }

    MapProvider.setView(lat, lng, zoom)
}

function i8ln(word) {
    if ($.isEmptyObject(i8lnDictionary) && language !== 'en' && languageLookups < languageLookupThreshold) {
        $.ajax({
            url: 'static/dist/locales/' + language + '.min.json',
            dataType: 'json',
            async: false,
            success: function (data) {
                i8lnDictionary = data
            },
            error: function (jqXHR, status, error) {
                console.log('Error loading i8ln dictionary: ' + error)
                languageLookups++
            }
        })
    }
    if (word in i8lnDictionary) {
        return i8lnDictionary[word]
    } else {
        // Word doesn't exist in dictionary return it as is
        return word
    }
}

function updateGeoLocation() {
    if (navigator.geolocation && (Store.get('geoLocate') || Store.get('followMyLocation'))) {
        navigator.geolocation.getCurrentPosition(function (position) {
            var lat = position.coords.latitude
            var lng = position.coords.longitude
            var center = MapProvider.latLng(lat, lng)

            if (Store.get('geoLocate')) {
                // The search function makes any small movements cause a loop. Need to increase resolution.
                if ((typeof searchMarker !== 'undefined') && (getPointDistance(searchMarker.getPosition(), center) > 40)) {
                    $.post('next_loc?lat=' + lat + '&lon=' + lng).done(function () {
                        map.panTo(center)
                        searchMarker.setPosition(center)
                    })
                }
            }
        })
    }
}

function createUpdateWorker() {
    try {
        if (isMobileDevice() && (window.Worker)) {
            var updateBlob = new Blob([`onmessage = function(e) {
                var data = e.data
                if (data.name === 'backgroundUpdate') {
                    self.setInterval(function () {self.postMessage({name: 'backgroundUpdate'})}, 5000)
                }
            }`])

            var updateBlobURL = window.URL.createObjectURL(updateBlob)

            updateWorker = new Worker(updateBlobURL)

            updateWorker.onmessage = function (e) {
                var data = e.data
                if (document.hidden && data.name === 'backgroundUpdate' && Date.now() - lastUpdateTime > 2500) {
                    updateMap()
                    updateGeoLocation()
                }
            }

            updateWorker.postMessage({
                name: 'backgroundUpdate'
            })
        }
    } catch (ex) {
        console.log('Webworker error: ' + ex.message)
    }
}

function getParameterByName(name, url) {
    if (!url) {
        url = window.location.search
    }
    name = name.replace(/[[\]]/g, '\\$&')
    var regex = new RegExp('[?&]' + name + '(=([^&#]*)|&|#|$)')
    var results = regex.exec(url)
    if (!results) {
        return null
    }
    if (!results[2]) {
        return ''
    }
    return decodeURIComponent(results[2].replace(/\+/g, ' ').replace('_', ' ').replace('%27', "'"))
}


//
// Page Ready Execution
//

$(function () {
    /* TODO: Some items are being loaded asynchronously, but synchronous code
     * depends on it. Restructure to make sure these "loading" tasks are
     * completed before continuing. Right now it "works" because the first
     * map update is scheduled after 5s. */

    // populate Navbar Style menu
    $selectStyle = $('#map-style')

    // Load Stylenames, translate entries, and populate lists
    $.getJSON('static/dist/data/mapstyle.min.json').done(function (data) {
        var styleList = []

        $.each(data, function (key, value) {
            styleList.push({
                id: key,
                text: i8ln(value)
            })
        })

        // setup the stylelist
        $selectStyle.select2({
            placeholder: 'Select Style',
            data: styleList,
            minimumResultsForSearch: Infinity
        })

        // setup the list change behavior
        $selectStyle.on('change', function (e) {
            selectedStyle = $selectStyle.val()
            map.setMapTypeId(selectedStyle)
            Store.set('map_style', selectedStyle)
        })

        // recall saved mapstyle
        $selectStyle.val(Store.get('map_style')).trigger('change')
    })

    var mapServiceProvider = $('#map-service-provider')

    mapServiceProvider.select2({
        placeholder: 'Select map provider',
        data: ['googlemaps', 'applemaps'],
        minimumResultsForSearch: Infinity
    })

    mapServiceProvider.on('change', function (e) {
        var selectedVal = mapServiceProvider.val()
        Store.set('mapServiceProvider', selectedVal)
    })

    $switchAccountSidebar = $('#account-sidebar-switch')

    $switchAccountSidebar.on('change', function () {
        Store.set('useAccountSidebar', this.checked)
        lastaccounts = false
        $.each(['accounts'], function (d, dType) {
            $.each(mapData[dType], function (key, value) {
                // for any marker you're turning off, you'll want to wipe off the range
                mapData[dType][key].marker.setMap(null)
            })
            mapData[dType] = {}
        })
        updateMap()
    })

    $switchLocationSidebar = $('#location-sidebar-switch')

    $switchLocationSidebar.on('change', function () {
        Store.set('useLocationSidebar', this.checked)
        lastlocations = false
        $.each(['locations'], function (d, dType) {
            $.each(mapData[dType], function (key, value) {
                // for any marker you're turning off, you'll want to wipe off the range
                mapData[dType][key].marker.setMap(null)
            })
            mapData[dType] = {}
        })
        updateMap()
    })

    $.getJSON('static/dist/data/searchmarkerstyle.min.json').done(function (data) {
        searchMarkerStyles = data
        var searchMarkerStyleList = []

        $.each(data, function (key, value) {
            searchMarkerStyleList.push({
                id: key,
                text: value.name
            })
        })

    })
})

$(function () {
    bootstrapMapProvider()

    moment.locale(language)

    function formatOccupierState(state) {
        if (!state.id) {
            return state.text
        }
        var $state = $(
            '<span><img class="occupier sprite" src="static/images/markers/occupiers/' + state.id.toString() + '.webp"> ' + state.text + '</span>'
        )
        return $state
    }

    if (Store.get('startAtUserLocation') && getParameterByName('lat') == null && getParameterByName('lon') == null) {
        centerMapOnLocation()
    }

    $selectExcludeLocations = $('#exclude-location')

    // Load Occupier type names and populate lists
    $.getJSON('static/dist/data/occupier_type.min.json').done(function (data) {
        var occupier_typeList = []

        $.each(data, function (key, value) {
            var _types = []
            occupier_typeList.push({
                id: key,
                text: i8ln(value)
            })
            value = i8ln(value)
            idToOccupierType[key] = value
        })

        // setup the filter lists
        $selectExcludeLocations.select2({
            placeholder: i8ln('Select Occupier Type'),
            data: occupier_typeList,
            templateResult: formatOccupierState
        })

        // setup list change behavior now that we have the list to work from
        $selectExcludeLocations.on('change', function (e) {
            buffer = excludedLocations
            excludedLocations = $selectExcludeLocations.val().map(Number)
            buffer = buffer.filter(function (e) {
                return this.indexOf(e) < 0
            }, excludedLocations)
            clearStaleMarkers()
            Store.set('remember_select_exclude_locations', excludedLocations)
        })

        // recall saved lists
        $selectExcludeLocations.val(Store.get('remember_select_exclude_locations')).trigger('change')

        if (isTouchDevice() && isMobileDevice()) {
            $('.select2-search input').prop('readonly', true)
        }
    })

    // run interval timers to regularly update map and timediffs
    window.setInterval(updateLabelDiffTime, 1000)
    window.setInterval(updateMap, 5000)
    window.setInterval(updateGeoLocation, 1000)

    createUpdateWorker()

    // Wipe off/restore map icons when switches are toggled
    function buildSwitchChangeListener(data, dataType, storageKey) {
        return function () {
            Store.set(storageKey, this.checked)

            if (storageKey === 'showAccounts') {
                if (Store.get('showAccounts')) {
                    lastaccounts = false
                    updateMap()
                } else {
                    $.each(dataType, function (d, dType) {
                        $.each(data[dType], function (key, value) {
                            // for any marker you're turning off, you'll want to wipe off the range
                            data[dType][key].marker.setMap(null)
                        })
                        data[dType] = {}
                    })
                }
            }

            if (storageKey === 'showLocations') {
                if (Store.get('showLocations')) {
                    lastlocations = false
                    updateMap()
                } else {
                    $.each(dataType, function (d, dType) {
                        $.each(data[dType], function (key, value) {
                            // for any marker you're turning off, you'll want to wipe off the range
                            data[dType][key].marker.setMap(null)
                        })
                        data[dType] = {}
                    })
                }
            }

        }
    }

    // Setup UI element interactions
    $('#geoloc-switch').change(function () {
        $('#next-location').prop('disabled', this.checked)
        $('#next-location').css('background-color', this.checked ? '#e0e0e0' : '#ffffff')
        if (!navigator.geolocation) {
            this.checked = false
        } else {
            Store.set('geoLocate', this.checked)
        }
    })

    $('#accounts-switch').change(function () {
        var options = {
            'duration': 500
        }
        lastaccounts = false
        buildSwitchChangeListener(mapData, ['accounts'], 'showAccounts').bind(this)()
    })

    $('#locations-switch').change(function () {
        var options = {
            'duration': 500
        }
        lastlocations = false
        var wrapperLocations = $('#locations-filter-wrapper')
        if (this.checked) {
            wrapperLocations.show(options)
        } else {
            wrapperLocations.hide(options)
        }
        buildSwitchChangeListener(mapData, ['locations'], 'showLocations').bind(this)()
    })

    $('#scanned-switch').change(function () {
        buildSwitchChangeListener(mapData, ['scanned'], 'showScanned').bind(this)()
    })

    $('#lock-marker-switch').change(function () {
        Store.set('lockMarker', this.checked)

        if (searchMarker) {
            searchMarker.setDraggable(!this.checked)
        }
    })

    $('#start-at-user-location-switch').change(function () {
        Store.set('startAtUserLocation', this.checked)
    })

    $('#follow-my-location-switch').change(function () {
        if (!navigator.geolocation) {
            this.checked = false
        } else {
            Store.set('followMyLocation', this.checked)
        }

    })
})
