const list = document.querySelector("#signal-list");
const map = document.querySelector("#map-canvas");
const count = document.querySelector("#signal-count");
const state = { volunteers: [], clients: [] };

const label = (value) => value.replaceAll("_", " ");
const shifts = (schedule) => Object.entries(schedule).map(([day, slots]) => `${day} ${slots.join(" / ")}`).join(" · ");
const hasOverlap = (volunteer, client) => Object.entries(client.properties.schedule).some(([day, slots]) => (volunteer.properties.availability[day] || []).some((slot) => slots.includes(slot)));
const matchesFor = (client) => state.volunteers.filter((volunteer) => volunteer.properties.skills.some((skill) => client.properties.needs.includes(skill)) && hasOverlap(volunteer, client));

function volunteerCard(feature) {
  const props = feature.properties;
  return `<article class="signal-item person-item volunteer" data-id="${feature.id}"><span class="signal-tag">volunteer · ${props.address}</span><h4>${props.name}</h4><p>Available for ${props.skills.slice(0, 2).map(label).join(" and ")}.</p><div class="skill-row">${props.skills.map((skill) => `<span>${label(skill)}</span>`).join("")}</div><small class="schedule-line">${props.skills.length} skills offered · ${shifts(props.availability)}</small></article>`;
}

function clientCard(feature) {
  const props = feature.properties;
  const matches = matchesFor(feature);
  const matchNames = matches.map((match) => match.properties.name).join(", ");
  return `<article class="signal-item person-item client" data-id="${feature.id}"><span class="signal-tag">client · ${props.address}</span><h4>${props.name}</h4><p>${props.request}</p><div class="skill-row">${props.needs.map((need) => `<span>${label(need)}</span>`).join("")}</div><small class="schedule-line">${matches.length} matching volunteer${matches.length === 1 ? "" : "s"} · ${shifts(props.schedule)}</small>${matches.length ? `<div class="match-note">Best overlap: ${matchNames}</div>` : '<div class="match-note muted">No exact schedule overlap yet</div>'}</article>`;
}

function render() {
  const people = [...state.volunteers.map((feature) => ({ feature, kind: "volunteer" })), ...state.clients.map((feature) => ({ feature, kind: "client" }))];
  list.innerHTML = people.map(({ feature, kind }) => kind === "volunteer" ? volunteerCard(feature) : clientCard(feature)).join("");
  count.textContent = String(people.length).padStart(2, "0");
  map.querySelectorAll(".map-pin").forEach((pin) => pin.remove());
  people.forEach(({ feature, kind }) => { const pin = document.createElement("button"); pin.className = `map-pin ${kind}-pin`; pin.style.left = `${feature.properties.x}%`; pin.style.top = `${feature.properties.y + (kind === "client" ? 3 : 0)}%`; pin.title = `${feature.properties.name} — ${kind}`; pin.addEventListener("click", () => focusPerson(feature.id)); map.appendChild(pin); });
}

function focusPerson(id) { const item = list.querySelector(`[data-id="${id}"]`); item?.scrollIntoView({ behavior: "smooth", block: "center" }); item?.animate([{ background: "#f6ddcf" }, { background: "transparent" }], { duration: 900 }); }

async function loadGeoJson() { const [volunteers, clients] = await Promise.all([fetch("../data/volunteers.geojson").then((response) => response.json()), fetch("../data/clients.geojson").then((response) => response.json())]); state.volunteers = volunteers.features; state.clients = clients.features; render(); }

loadGeoJson().catch(() => { list.innerHTML = "<p class='empty-state'>Start the local server to load the volunteer and client GeoJSON layers.</p>"; });
