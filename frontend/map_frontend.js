// Paste into the <script> of the Eldana site. Replaces the hard-coded updateMapMarkers().
// It reads the anonymized public API, so it is safe on a public page.
// Never put the admin key in this file: anyone can read it. Coordinators use the admin routes from a private page.

const API_BASE = "http://localhost:8000";   // change when deployed
const LAYER_COLORS = { vol: "#84cc16", client: "#f59e0b", chapter: "#047857" };

function esc(s) {                           // names come from the database, so never insert them as raw HTML
    return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function formatSchedule(schedule) {
    return Object.entries(schedule || {}).map(([day, slots]) => `${day} ${slots.join(", ")}`).join("<br>");
}

async function updateMapMarkers() {
    if (!leafletMap) return;
    mapMarkers.forEach(m => leafletMap.removeLayer(m));
    mapMarkers = [];

    const layers = [];
    if (document.getElementById("toggle-volunteers").checked) layers.push("vol");
    if (document.getElementById("toggle-clients").checked) layers.push("client");
    if (document.getElementById("toggle-chapters").checked) layers.push("chapter");
    if (!layers.length) return;

    let data;
    try {
        const demoLayers = layers.filter(layer => layer === "vol" || layer === "client");
        const requests = [];
        if (demoLayers.length) requests.push(fetch(`${API_BASE}/api/map/demo-geojson?layers=${demoLayers.join(",")}`));
        if (layers.includes("chapter")) requests.push(fetch(`${API_BASE}/api/map/geojson?layers=chapter`));
        const responses = await Promise.all(requests);
        if (responses.some(res => !res.ok)) throw new Error("map request failed");
        const collections = await Promise.all(responses.map(res => res.json()));
        data = { type: "FeatureCollection", features: collections.flatMap(collection => collection.features) };
    } catch (e) {
        // Live Server may be running without the FastAPI process. Use the
        // synthetic hackathon layer locally so the map remains explorable.
        try {
            const localFiles = await Promise.all([
                layers.includes("vol") ? fetch("demo_data/volunteers.geojson") : null,
                layers.includes("client") ? fetch("demo_data/clients.geojson") : null
            ].filter(Boolean));
            if (localFiles.some(res => !res.ok)) throw new Error("local map data unavailable");
            const localCollections = await Promise.all(localFiles.map(res => res.json()));
            data = { type: "FeatureCollection", features: localCollections.flatMap(collection => collection.features) };
            if (layers.includes("chapter")) {
                data.features.push({ type: "Feature", geometry: { type: "Point", coordinates: [-75.1652, 39.9526] }, properties: { layer: "chapter", title: "Eldana HQ Chapter", desc: "Regional Dispatch Center" } });
            }
        } catch (fallbackError) {
            showToast("Could not load the map data. Start FastAPI or open frontend/Eldana.html with Live Server.");
            return;
        }
    }

    const group = L.geoJSON(data, {
        pointToLayer: (f, latlng) => {
            const p = f.properties;
            // client points are density cells (several clients), so size them by count
            const radius = p.layer === "client" ? Math.min(30, 10 + 3 * (p.count || 1)) : 10;
            return L.circleMarker(latlng, {
                radius, fillColor: LAYER_COLORS[p.layer], color: "#ffffff",
                weight: 2, opacity: 1, fillOpacity: p.layer === "client" ? 0.55 : 0.9
            });
        },
        onEachFeature: (f, layer) => {
            const p = f.properties, c = LAYER_COLORS[p.layer];
            const schedule = p.layer === "client" ? formatSchedule(p.schedule) : formatSchedule(p.availability);
            const detail = p.layer === "client" ? `<strong>Needs:</strong> ${esc((p.needs || []).join(", "))}<br><strong>Address:</strong> ${esc(p.address || "")}<br><strong>Schedule:</strong><br>${schedule}<br><strong>Request:</strong> ${esc(p.request || "")}`
                         : p.layer === "vol" ? `<strong>Skills:</strong> ${esc((p.skills || []).join(", "))}<br><strong>Address:</strong> ${esc(p.address || "")}<br><strong>Available:</strong><br>${schedule}`
                         : esc(p.desc || "");
            layer.bindPopup(`<div style="font-family:'Libre Baskerville',serif;">
                <span style="color:${c};">${esc(p.title)}</span><br>
                <span style="font-size:12px;color:#444;">${detail}</span></div>`);
        }
    }).addTo(leafletMap);
    mapMarkers.push(group);
}
