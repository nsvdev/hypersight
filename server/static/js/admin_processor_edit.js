var camera_id = -1;
var image_layer = null;
var image_w = 0;
var image_h = 0;
var zones_str = $('#zones_str');
var map_div = $('<div id="map" style="height: 600px; width: 100%"></div>');
map_div.insertAfter(zones_str);
var map = L.map('map', {
    crs: L.CRS.Simple,
    // drawControl: true,
    // zoomControl: false
});
// map.dragging.disable();
// map.touchZoom.disable();
// map.doubleClickZoom.disable();
map.scrollWheelZoom.disable();


// Initialise the FeatureGroup to store editable layers
var editableLayers = new L.FeatureGroup();
map.addLayer(editableLayers);

var drawPluginOptions = {
    position: 'topright',
    draw: {
        polygon: {
            allowIntersection: true, // Restricts shapes to simple polygons
            drawError: {
                color: '#e1e100', // Color the shape will turn when intersects
                message: '<strong>Oh snap!<strong> you can\'t draw that!' // Message that will show when intersect
            },
            shapeOptions: {
                color: '#97009c'
            }
        },
        // disable toolbar item by setting it to false
        polyline: false,
        circlemarker: false,
        circle: false, // Turns off this drawing tool
        rectangle: false,
        marker: false,
    },
    edit: {
        featureGroup: editableLayers
    }
};

// Initialise the draw control and pass it the FeatureGroup of editable layers
var drawControl = new L.Control.Draw(drawPluginOptions);
map.addControl(drawControl);

map.on(L.Draw.Event.CREATED, function (e) {
    let type = e.layerType,
        layer = e.layer;
    editableLayers.addLayer(layer);
    if (type === 'polygon') {
        update_coord_string()
    }


});

map.on(L.Draw.Event.EDITED, function (e) {
    update_coord_string();
});

map.on(L.Draw.Event.DELETED, function (e) {
    update_coord_string();
});

function update_coord_string() {
    let res = [];
    editableLayers.eachLayer(function (layer) {
        let raw_coords = layer.toGeoJSON().geometry.coordinates[0];
        let coords = [];
        raw_coords.forEach(function (coord) {
            coords.push([
                round(limitNumber(coord[0] / image_w, 0, 1), 2),
                round(limitNumber((image_h - coord[1]) / image_h, 0, 1), 2)
            ])
            ;
        });
        res.push(coords);
    });
    zones_str.val(JSON.stringify(res));
}

function update_map_image() {
    let new_camera_id = camera_id;
    let selected_text = $(this).text();
    if (selected_text.trim() !== '') {
        new_camera_id = $('#camera option').filter(function () {
            return $(this).html() === HtmlEncode(selected_text);
        }).val();
    }
    if (new_camera_id !== camera_id) {
        // get image with bounds (sizes)
        let data = {'camera_id': new_camera_id};
        $.ajaxSetup({
            contentType: "application/json"
        });
        $.post({
            url: '/getFrame',
            data: JSON.stringify(data),
            success: function (data) {
                if (data['err']) {
                    console.log(data['msg']);
                    zones_str.show();
                    map_div.hide();
                    clean_map();
                } else {
                    zones_str.hide();
                    map_div.show();
                    image_h = data['height'];
                    image_w = data['width'];
                    // init map
                    init_map(data['path'], [[0, 0], [data['height'], data['width']]]);
                    //draw polygons from str
                    draw_str_polygons();
                }

            },
            dataType: "json"
        });
    }


}

function draw_str_polygons() {
    let pols_coords = [];
    try {
        pols_coords = JSON.parse(zones_str.val());
    } catch (SyntaxError) {
        console.log('badly formatted coords string')
    }
    pols_coords.forEach(function (raw_coords) {
        let coords = [];
        raw_coords.forEach(function (coord) {
            coords.push([image_h * (1 - coord[1]), coord[0] * image_w])
        });
        L.polygon(coords).addTo(editableLayers);
    })

}

function clean_map() {
    // remove current image
    if (image_layer != null) {
        map.removeLayer(image_layer)
    }
    //remove all existing polygons
    editableLayers.eachLayer(function (layer) {
        map.removeLayer(layer);
    });
}

function init_map(image_path, bounds) {
    clean_map();
    //draw image layer
    image_layer = L.imageOverlay(image_path, bounds);
    image_layer.addTo(map);
    map.fitBounds(bounds);
}

$(document).on('DOMSubtreeModified', '#select2-chosen-1', update_map_image);


/**
 * @return {string}
 */
function HtmlEncode(s) {
    let el = document.createElement("div");
    el.innerText = el.textContent = s;
    s = el.innerHTML;
    return s
}

function limitNumber(num, min, max) {
    return Math.min(Math.max(num, min), max)
}

function round(x, n) {
    return Math.round(x * 10 ** n) / 10 ** n;
}

function getQueryVariable(variable) {
    let query = window.location.search.substring(1);
    let vars = query.split('&');
    for (let i = 0; i < vars.length; i++) {
        let pair = vars[i].split('=');
        if (decodeURIComponent(pair[0]) === variable) {
            return decodeURIComponent(pair[1]);
        }
    }
    console.log('Query variable %s not found', variable);
}

function launchPreview() {
    let proc_id = getQueryVariable('id');
    let manifest_url = `/videos/${proc_id}/processed_stream.m3u8`;
    let video = document.getElementById('preview_hls');
    if (Hls.isSupported()) {
        let hls = new Hls();
        hls.loadSource(manifest_url);
        hls.attachMedia(video);
        hls.on(Hls.Events.MANIFEST_PARSED, function () {
            video.play();
        });
    }
        // hls.js is not supported on platforms that do not have Media Source Extensions (MSE) enabled.
        // When the browser has built-in HLS support (check using `canPlayType`), we can provide an HLS manifest (i.e. .m3u8 URL) directly to the video element through the `src` property.
        // This is using the built-in support of the plain video element, without using hls.js.
        // Note: it would be more normal to wait on the 'canplay' event below however on Safari (where you are most likely to find built-in HLS support) the video.src URL must be on the user-driven
    // white-list before a 'canplay' event will be emitted; the last video event that can be reliably listened-for when the URL is not on the white-list is 'loadedmetadata'.
    else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        video.src = manifest_url;
        video.addEventListener('loadedmetadata', function () {
            video.play();
        });
    }
}

$(document).ready(function () {
    update_map_image();
    if ($('#output_hls').prop('checked')) {
        $('#preview_hls_wrapper').show();
        launchPreview();
    } else {
        $('#preview_hls_wrapper').hide();
    }
});
