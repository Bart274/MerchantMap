/* eslint no-unused-vars: "off" */

var merchantStyle = [
  {
    "featureType": "landscape",
    "elementType": "geometry",
    "stylers": [
      {
        "color": "#648a5e"
      }
    ]
  },
  {
    "featureType": "poi",
    "stylers": [
      {
        "visibility": "off"
      }
    ]
  },
  {
    "featureType": "road",
    "elementType": "geometry",
    "stylers": [
      {
        "color": "#ebd292"
      }
    ]
  }
]

var leafletTileStyles = {
    'style_merchant': {
        layers: ['https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png'],
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        maxZoom: 20
    },
    'roadmap': {
        layers: ['https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'],
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19
    },
    'satellite': {
        layers: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
        attribution: 'Tiles &copy; Esri',
        maxZoom: 19
    },
    'hybrid': {
        layers: [
            'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}'
        ],
        attribution: 'Tiles &copy; Esri',
        maxZoom: 19
    }
}

function useLeaflet() {
    return mapProvider === 'leaflet'
}

//
// LocalStorage helpers
//

var StoreTypes = {
    Boolean: {
        parse: function (str) {
            switch (str.toLowerCase()) {
                case '1':
                case 'true':
                case 'yes':
                    return true
                default:
                    return false
            }
        },
        stringify: function (b) {
            return b ? 'true' : 'false'
        }
    },
    JSON: {
        parse: function (str) {
            return JSON.parse(str)
        },
        stringify: function (json) {
            return JSON.stringify(json)
        }
    },
    String: {
        parse: function (str) {
            return str
        },
        stringify: function (str) {
            return str
        }
    },
    Number: {
        parse: function (str) {
            return parseInt(str, 10)
        },
        stringify: function (number) {
            return number.toString()
        }
    }
}

// set the default parameters for you map here
var StoreOptions = {
    'map_style': {
        default: 'style_merchant', // roadmap, satellite, hybrid, nolabels_style, dark_style, style_light2, style_pgo, dark_style_nl, style_pgo_day, style_pgo_night, style_pgo_dynamic
        type: StoreTypes.String
    },
    'showScanned': {
        default: true,
        type: StoreTypes.Boolean
    },
    'showAccounts': {
        default: true,
        type: StoreTypes.Boolean
    },
    'useAccountSidebar': {
        default: true,
        type: StoreTypes.Boolean
    },
    'showLocations': {
        default: true,
        type: StoreTypes.Boolean
    },
    "useLocationSidebar": {
        default: true,
        type: StoreTypes.Boolean
    },
    'geoLocate': {
        default: false,
        type: StoreTypes.Boolean
    },
    'lockMarker': {
        default: isTouchDevice(), // default to true if touch device
        type: StoreTypes.Boolean
    },
    'startAtUserLocation': {
        default: false,
        type: StoreTypes.Boolean
    },
    'followMyLocation': {
        default: false,
        type: StoreTypes.Boolean
    },
    'followMyLocationPosition': {
        default: [],
        type: StoreTypes.JSON
    },
    'iconSizeModifier': {
        default: 0,
        type: StoreTypes.Number
    },
    'zoomLevel': {
        default: 16,
        type: StoreTypes.Number
    },
    'maxClusterZoomLevel': {
        default: 14,
        type: StoreTypes.Number
    },
    'clusterZoomOnClick': {
        default: false,
        type: StoreTypes.Boolean
    },
    'clusterGridSize': {
        default: 60,
        type: StoreTypes.Number
    },
    'mapServiceProvider': {
        default: 'googlemaps',
        type: StoreTypes.String
    },
    'isBounceDisabled': {
        default: false,
        type: StoreTypes.Boolean
    }
}

var Store = {
    getOption: function (key) {
        var option = StoreOptions[key]
        if (!option) {
            throw new Error('Store key was not defined ' + key)
        }
        return option
    },
    get: function (key) {
        var option = this.getOption(key)
        var optionType = option.type
        var rawValue = localStorage[key]
        if (rawValue === null || rawValue === undefined) {
            return option.default
        }
        var value = optionType.parse(rawValue)
        return value
    },
    set: function (key, value) {
        var option = this.getOption(key)
        var optionType = option.type || StoreTypes.String
        var rawValue = optionType.stringify(value)
        localStorage[key] = rawValue
    },
    reset: function (key) {
        localStorage.removeItem(key)
    }
}

var mapData = {
    accounts: {},
    locations: {},
    scanned: {},
}

function getGoogleSprite(index, sprite, displayHeight) {
    displayHeight = Math.max(displayHeight, 3)
    var scale = displayHeight / sprite.iconHeight
    // Crop icon just a tiny bit to avoid bleedover from neighbor
    var iconWidth = scale * sprite.iconWidth - 1
    var iconHeight = scale * sprite.iconHeight - 1
    var offsetX = (index % sprite.columns) * sprite.iconWidth * scale + 0.5
    var offsetY = Math.floor(index / sprite.columns) * sprite.iconHeight * scale + 0.5
    var spriteWidth = scale * sprite.spriteWidth
    var spriteHeight = scale * sprite.spriteHeight
    var centerX = scale * sprite.iconWidth / 2
    var centerY = scale * sprite.iconHeight / 2

    var makeSize = useLeaflet()
        ? function (w, h) { return {width: w, height: h} }
        : function (w, h) { return new google.maps.Size(w, h) }
    var makePoint = useLeaflet()
        ? function (x, y) { return {x: x, y: y} }
        : function (x, y) { return new google.maps.Point(x, y) }

    return {
        url: sprite.filename,
        size: makeSize(iconWidth, iconHeight),
        scaledSize: makeSize(spriteWidth, spriteHeight),
        origin: makePoint(offsetX, offsetY),
        anchor: makePoint(centerX, centerY)
    }
}

function isTouchDevice() {
    // Should cover most browsers
    return 'ontouchstart' in window || navigator.maxTouchPoints
}

function isMobileDevice() {
    //  Basic mobile OS (not browser) detection
    return (/Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent))
}
