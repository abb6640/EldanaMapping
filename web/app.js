const signals = [
  { id: 1, type: "need", title: "A softer landing for new neighbors", place: "North Market", description: "People are looking for an easier way to meet the block." , x: 28, y: 36 },
  { id: 2, type: "idea", title: "Repair circles, not repair shops", place: "Eastbank", description: "Share tools, skills, and a little more time." , x: 62, y: 52 },
  { id: 3, type: "need", title: "Shade would change this walk", place: "Cedar Loop", description: "The route is loved, but the summer heat is a barrier." , x: 48, y: 73 },
  { id: 4, type: "idea", title: "A library of useful things", place: "Old Station", description: "What if borrowing a drill was as easy as borrowing a book?" , x: 77, y: 29 },
  { id: 5, type: "need", title: "Keep the lights on later", place: "South Commons", description: "An evening bus stop should feel like a place, not a gap." , x: 20, y: 68 },
  { id: 6, type: "idea", title: "Sidewalk tables, shared stories", place: "Juniper Row", description: "The best third place in the neighborhood is the sidewalk." , x: 70, y: 80 },
];

const list = document.querySelector("#signal-list");
const map = document.querySelector("#map-canvas");
const count = document.querySelector("#signal-count");

function render(filter = "all") {
  const visible = filter === "all" ? signals : signals.filter((signal) => signal.type === filter);
  list.innerHTML = visible.map((signal) => `<article class="signal-item" data-id="${signal.id}"><span class="signal-tag">${signal.type} · ${signal.place}</span><h4>${signal.title}</h4><p>${signal.description}</p></article>`).join("");
  count.textContent = String(visible.length).padStart(2, "0");
  map.querySelectorAll(".map-pin").forEach((pin) => pin.remove());
  visible.forEach((signal) => { const pin = document.createElement("button"); pin.className = "map-pin"; pin.style.left = `${signal.x}%`; pin.style.top = `${signal.y}%`; pin.title = signal.title; pin.addEventListener("click", () => focusSignal(signal.id)); map.appendChild(pin); });
}

function focusSignal(id) { const item = list.querySelector(`[data-id="${id}"]`); item?.scrollIntoView({ behavior: "smooth", block: "center" }); item?.animate([{ background: "#f6ddcf" }, { background: "transparent" }], { duration: 900 }); }

document.querySelectorAll(".filter").forEach((button) => button.addEventListener("click", () => { document.querySelector(".filter.active").classList.remove("active"); button.classList.add("active"); render(button.dataset.filter); }));
document.querySelectorAll('[data-action="new-signal"]').forEach((button) => button.addEventListener("click", () => document.querySelector("#signal-dialog").showModal()));
document.querySelector("#signal-form").addEventListener("submit", (event) => { const data = new FormData(event.target); signals.unshift({ id: Date.now(), type: data.get("type"), title: data.get("title"), place: data.get("place") || "Just shared", description: data.get("description") || "A new observation from the community.", x: 35 + Math.random() * 35, y: 25 + Math.random() * 50 }); render(document.querySelector(".filter.active").dataset.filter); });
render();
