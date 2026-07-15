"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";
const Playback = globalThis.ColiseumPlayback;
const state = {
  model: null, position: 0, playing: false, timer: null, speed: 1,
  selected: null, selectedEvent: null,
  camera: {x: 0, y: 0, width: 900, height: 620},
};

const byId = (id) => document.getElementById(id);
const runSelect = byId("run-select");
const loadStatus = byId("load-status");
const eventFilter = byId("event-filter");
const scrubber = byId("scrubber");
const arena = byId("arena");

function node(name, text, className) {
  const element = document.createElement(name);
  if (text !== undefined && text !== null) element.textContent = String(text);
  if (className) element.className = className;
  return element;
}

function svgNode(name, attributes = {}) {
  const element = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value));
  return element;
}

function apiUrl(path) { return new URL(path, document.baseURI); }

async function getJson(path) {
  const response = await fetch(apiUrl(path), {headers: {"Accept": "application/json"}, cache: "no-store"});
  const body = await response.json();
  if (!response.ok) throw new Error(body.error?.code || `HTTP ${response.status}`);
  return body;
}

function currentSnapshot() { return state.model?.snapshots[state.position] || null; }

function setDisabled(disabled) {
  for (const id of ["jump-start", "previous-event", "previous-tick", "play-pause",
                    "next-tick", "next-event", "jump-end", "scrubber", "speed",
                    "zoom-out", "zoom-in", "fit-map", "focus-selection"]) {
    byId(id).disabled = disabled;
  }
}

function stopPlayback() {
  state.playing = false;
  if (state.timer !== null) window.clearTimeout(state.timer);
  state.timer = null;
  byId("play-pause").textContent = "Play";
  byId("play-pause").setAttribute("aria-pressed", "false");
}

function schedulePlayback() {
  if (!state.playing || !state.model) return;
  state.timer = window.setTimeout(() => {
    if (state.position >= state.model.playback.last_position) {
      stopPlayback();
      return;
    }
    seek(state.position + 1);
    schedulePlayback();
  }, Playback.delayForSpeed(state.speed));
}

function togglePlayback() {
  if (!state.model) return;
  if (state.playing) { stopPlayback(); return; }
  if (state.position >= state.model.playback.last_position) seek(0);
  state.playing = true;
  byId("play-pause").textContent = "Pause";
  byId("play-pause").setAttribute("aria-pressed", "true");
  schedulePlayback();
}

function seek(position) {
  if (!state.model) return;
  state.position = Playback.clampPosition(position, state.model.playback.last_position);
  scrubber.value = String(state.position);
  state.selectedEvent = null;
  render();
}

function eventJump(direction) {
  if (!state.model) return;
  const next = Playback.adjacentEventPosition(state.model.events, state.position, direction);
  if (next !== undefined) seek(next);
}

function fitMap() {
  const snapshot = currentSnapshot();
  if (!snapshot || snapshot.rooms.length === 0) return;
  const minX = Math.min(...snapshot.rooms.map((room) => room.x)) - 40;
  const minY = Math.min(...snapshot.rooms.map((room) => room.y)) - 40;
  const maxX = Math.max(...snapshot.rooms.map((room) => room.x + room.width)) + 40;
  const maxY = Math.max(...snapshot.rooms.map((room) => room.y + room.height)) + 40;
  state.camera = {x: minX, y: minY, width: Math.max(300, maxX - minX), height: Math.max(220, maxY - minY)};
  applyCamera();
}

function applyCamera() {
  const c = state.camera;
  arena.setAttribute("viewBox", `${c.x} ${c.y} ${c.width} ${c.height}`);
}

function zoom(factor) {
  const c = state.camera;
  const width = Math.max(180, Math.min(2500, c.width * factor));
  const height = Math.max(140, Math.min(1800, c.height * factor));
  state.camera = {x: c.x + (c.width - width) / 2, y: c.y + (c.height - height) / 2, width, height};
  applyCamera();
}

function focusSelection() {
  const snapshot = currentSnapshot();
  if (!snapshot || !state.selected) return;
  const entity = snapshot.entities.find((item) => item.id === state.selected.id);
  const room = snapshot.rooms.find((item) => item.id === state.selected.id);
  const target = entity || room;
  if (!target) return;
  const x = target.x + (target.width || 0) / 2;
  const y = target.y + (target.height || 0) / 2;
  state.camera = {x: x - 220, y: y - 160, width: 440, height: 320};
  applyCamera();
}

function renderArena() {
  const snapshot = currentSnapshot();
  if (!snapshot) return;
  byId("arena-empty").hidden = true;
  arena.hidden = false;
  const showRooms = byId("overlay-room-labels").checked;
  const showPortals = byId("overlay-portals").checked;
  const showEntities = byId("overlay-entities").checked;
  const portalLayer = byId("portal-layer");
  const roomLayer = byId("room-layer");
  const entityLayer = byId("entity-layer");
  portalLayer.replaceChildren(); roomLayer.replaceChildren(); entityLayer.replaceChildren();
  if (showPortals) {
    for (const portal of snapshot.portals) {
      portalLayer.append(svgNode("line", {x1: portal.x1, y1: portal.y1, x2: portal.x2, y2: portal.y2,
        class: "portal-line", "aria-label": "Recorded directed portal"}));
    }
  }
  for (const room of snapshot.rooms) {
    const group = svgNode("g", {tabindex: "0", role: "button", "aria-label": room.label});
    const classes = ["room-shape"];
    if (state.selected?.id === room.id) classes.push("selected");
    group.append(svgNode("rect", {x: room.x, y: room.y, width: room.width, height: room.height,
      rx: 12, class: classes.join(" ")}));
    if (showRooms) {
      const label = svgNode("text", {x: room.x + 12, y: room.y + 24, class: "room-label"});
      label.textContent = room.label;
      group.append(label);
    }
    const selectRoom = () => { state.selected = {type: "room", id: room.id}; state.selectedEvent = null; render(); };
    group.addEventListener("click", selectRoom);
    group.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectRoom(); } });
    roomLayer.append(group);
  }
  if (showEntities) {
    for (const entity of snapshot.entities) {
      const group = svgNode("g", {tabindex: "0", role: "button", "aria-label": `${entity.label}, ${entity.kind}`});
      const classes = [entity.kind === "agent_body" ? "agent-token" : "object-token", "entity-token"];
      if (state.selected?.id === entity.id) classes.push("selected");
      if (entity.kind === "agent_body") group.append(svgNode("circle", {cx: entity.x, cy: entity.y, r: 13, class: classes.join(" ")}));
      else group.append(svgNode("rect", {x: entity.x - 10, y: entity.y - 10, width: 20, height: 20, rx: 3, class: classes.join(" ")}));
      const label = svgNode("text", {x: entity.x, y: entity.y + 27, "text-anchor": "middle", class: "entity-label"});
      label.textContent = entity.label;
      group.append(label);
      const selectEntity = () => { state.selected = {type: "entity", id: entity.id}; state.selectedEvent = null; render(); };
      group.addEventListener("click", selectEntity);
      group.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectEntity(); } });
      entityLayer.append(group);
    }
  }
  byId("arena-description").textContent = `${snapshot.rooms.length} visible rooms and ${snapshot.entities.length} visible entities at recorded position ${snapshot.position}.`;
}

function renderEvents() {
  const list = byId("event-list");
  list.replaceChildren();
  if (!state.model) return;
  const filter = eventFilter.value;
  for (const event of state.model.events) {
    if (filter !== "all" && event.category !== filter) continue;
    const item = node("li");
    const button = node("button", null, "event-button");
    button.type = "button";
    button.setAttribute("aria-current", String(state.selectedEvent?.id === event.id));
    button.append(node("span", `P${event.position}`, "event-position"));
    button.append(node("span", event.summary, "event-summary"));
    button.addEventListener("click", () => { stopPlayback(); state.selectedEvent = event; state.selected = null; state.position = event.position; scrubber.value = String(state.position); render(); });
    item.append(button); list.append(item);
  }
}

function addDefinition(list, label, value) {
  list.append(node("dt", label));
  list.append(node("dd", value === null || value === undefined ? "Not available" : String(value)));
}

function renderInspector() {
  const container = byId("inspector-content");
  container.replaceChildren();
  const snapshot = currentSnapshot();
  if (!snapshot) { container.append(node("p", "Select an admitted replay.")); return; }
  if (state.selectedEvent) {
    container.append(node("h3", "Recorded event"));
    const list = node("dl");
    addDefinition(list, "Position", state.selectedEvent.position);
    addDefinition(list, "Category", state.selectedEvent.category);
    addDefinition(list, "Summary", state.selectedEvent.summary);
    addDefinition(list, "Source", state.selectedEvent.semantic_source);
    container.append(list);
    const pre = node("pre", JSON.stringify(state.selectedEvent.structured, null, 2));
    pre.setAttribute("aria-label", "Structured authorized event fields");
    container.append(pre);
    return;
  }
  if (state.selected?.type === "entity") {
    const entity = snapshot.entities.find((item) => item.id === state.selected.id);
    if (!entity) { container.append(node("p", "The selected entity is not visible at this position.")); return; }
    container.append(node("h3", entity.label));
    const list = node("dl");
    addDefinition(list, "Identifier", entity.id);
    addDefinition(list, "Kind", entity.kind);
    addDefinition(list, "Room", entity.room_id);
    addDefinition(list, "Location", entity.location.tag);
    addDefinition(list, "Status", entity.status);
    addDefinition(list, "Source", entity.semantic_source);
    container.append(list);
    if (snapshot.dispatch?.agent_id === entity.id) {
      container.append(node("h3", "Recorded dispatch"));
      const dispatch = node("dl");
      addDefinition(dispatch, "Outcome", snapshot.dispatch.outcome);
      addDefinition(dispatch, "Selected action", snapshot.dispatch.selected_action);
      addDefinition(dispatch, "Legal kinds", snapshot.dispatch.legal_action_kinds?.join(", "));
      container.append(dispatch);
    }
    return;
  }
  if (state.selected?.type === "room") {
    const room = snapshot.rooms.find((item) => item.id === state.selected.id);
    if (!room) { container.append(node("p", "The selected room is not available at this position.")); return; }
    container.append(node("h3", room.label));
    const list = node("dl");
    addDefinition(list, "Identifier", room.id);
    addDefinition(list, "Occupants", snapshot.entities.filter((entity) => entity.room_id === room.id).length);
    addDefinition(list, "Geometry", "Derived presentation layout");
    container.append(list);
    return;
  }
  container.append(node("h3", `Position ${snapshot.position}`));
  const list = node("dl");
  addDefinition(list, "Logical step", snapshot.logical_step);
  addDefinition(list, "Visible rooms", snapshot.rooms.length);
  addDefinition(list, "Visible entities", snapshot.entities.length);
  addDefinition(list, "Map source", snapshot.map_state_source);
  container.append(list);
}

function renderResearch() {
  const container = byId("research-content");
  container.replaceChildren();
  if (!state.model) { container.append(node("p", "No run loaded.")); return; }
  const fields = {
    "Run ID": state.model.run_id,
    "Scenario": state.model.experiment.scenario,
    "Seed": state.model.experiment.seed,
    "Perspective": state.model.perspective.label,
    "Artifact validation": state.model.validation.artifact_validation,
    "Replay verification": state.model.validation.replay_verification,
    "Report authentication": state.model.validation.report_authentication,
    "Completion": state.model.validation.completion,
    "Behavioral claimability": state.model.validation.behavioral_claimability,
    "Result status": state.model.validation.result_status,
    "Training admission": state.model.validation.training_admission,
    "Governance approval": state.model.validation.governance_approval,
    "Quarantine": state.model.validation.quarantine,
    "Correction lineage": state.model.validation.correction_lineage,
    "Run schema": state.model.source_schema_versions.spatial_run,
    "Map theme": state.model.map_model.theme,
  };
  if (state.model.experiment.model_regime) {
    fields["Model"] = state.model.experiment.model_regime.model_id;
    fields["Model metadata source"] = state.model.experiment.model_regime.source;
  }
  if (state.model.experiment.termination) {
    fields["Termination"] = state.model.experiment.termination.code || "recorded";
  }
  for (const [label, value] of Object.entries(fields)) {
    const item = node("div", null, `provenance-item status-${String(value).replaceAll(" ", "_")}`);
    item.append(node("strong", label)); item.append(node("span", value)); container.append(item);
  }
}

function render() {
  if (!state.model) return;
  const snapshot = currentSnapshot();
  scrubber.max = String(state.model.playback.last_position);
  scrubber.value = String(state.position);
  byId("position-output").textContent = `Position ${state.position} / ${state.model.playback.last_position}`;
  byId("perspective-badge").textContent = state.model.perspective.label;
  renderArena(); renderEvents(); renderInspector(); renderResearch();
  for (const id of ["jump-start", "previous-tick", "previous-event"]) byId(id).disabled = state.position === 0;
  for (const id of ["jump-end", "next-tick", "next-event"]) byId(id).disabled = state.position === state.model.playback.last_position;
  byId("focus-selection").disabled = !state.selected;
  if (snapshot.rooms.length === 0) byId("fit-map").disabled = true;
}

async function loadRun(runId) {
  stopPlayback(); setDisabled(true); loadStatus.textContent = "Loading validated view model…";
  try {
    state.model = await getJson(`api/v1/runs/${runId}/view`);
    state.position = 0; state.selected = null; state.selectedEvent = null;
    const categories = [...new Set(state.model.events.map((event) => event.category))].sort();
    eventFilter.replaceChildren();
    const all = node("option", "All events"); all.value = "all"; eventFilter.append(all);
    for (const category of categories) { const option = node("option", category); option.value = category; eventFilter.append(option); }
    setDisabled(false); fitMap(); render();
    loadStatus.textContent = `${state.model.playback.position_count} recorded positions; no inference.`;
  } catch (error) {
    state.model = null; loadStatus.textContent = `Run refused: ${error.message}`;
    byId("arena-empty").hidden = false; arena.hidden = true; setDisabled(true);
  }
}

async function initialize() {
  setDisabled(true);
  try {
    const payload = await getJson("api/v1/runs");
    runSelect.replaceChildren();
    for (const run of payload.runs) {
      const option = node("option", `${run.scenario} · seed ${run.seed} · ${run.validation.completion}`);
      option.value = run.run_id; runSelect.append(option);
    }
    if (payload.runs.length === 0) { loadStatus.textContent = "No runs admitted in this perspective."; return; }
    await loadRun(payload.runs[0].run_id);
  } catch (error) { loadStatus.textContent = `Viewer unavailable: ${error.message}`; }
}

runSelect.addEventListener("change", () => loadRun(runSelect.value));
eventFilter.addEventListener("change", renderEvents);
scrubber.addEventListener("input", () => { stopPlayback(); seek(Number(scrubber.value)); });
byId("play-pause").addEventListener("click", togglePlayback);
byId("jump-start").addEventListener("click", () => { stopPlayback(); seek(0); });
byId("jump-end").addEventListener("click", () => { stopPlayback(); seek(state.model.playback.last_position); });
byId("previous-tick").addEventListener("click", () => { stopPlayback(); seek(state.position - 1); });
byId("next-tick").addEventListener("click", () => { stopPlayback(); seek(state.position + 1); });
byId("previous-event").addEventListener("click", () => { stopPlayback(); eventJump(-1); });
byId("next-event").addEventListener("click", () => { stopPlayback(); eventJump(1); });
byId("speed").addEventListener("change", () => { state.speed = Number(byId("speed").value); if (state.playing) { window.clearTimeout(state.timer); schedulePlayback(); } });
byId("fit-map").addEventListener("click", fitMap);
byId("focus-selection").addEventListener("click", focusSelection);
byId("zoom-in").addEventListener("click", () => zoom(0.8));
byId("zoom-out").addEventListener("click", () => zoom(1.25));
for (const id of ["overlay-room-labels", "overlay-portals", "overlay-entities"]) byId(id).addEventListener("change", renderArena);

arena.addEventListener("wheel", (event) => { event.preventDefault(); zoom(event.deltaY > 0 ? 1.12 : 0.88); }, {passive: false});
let drag = null;
arena.addEventListener("pointerdown", (event) => {
  drag = {pointerId: event.pointerId, x: event.clientX, y: event.clientY,
          cameraX: state.camera.x, cameraY: state.camera.y};
  arena.setPointerCapture(event.pointerId);
});
arena.addEventListener("pointermove", (event) => {
  if (!drag || drag.pointerId !== event.pointerId) return;
  const scaleX = state.camera.width / Math.max(1, arena.clientWidth);
  const scaleY = state.camera.height / Math.max(1, arena.clientHeight);
  state.camera.x = drag.cameraX - (event.clientX - drag.x) * scaleX;
  state.camera.y = drag.cameraY - (event.clientY - drag.y) * scaleY;
  applyCamera();
});
function endDrag(event) {
  if (!drag || drag.pointerId !== event.pointerId) return;
  drag = null;
  if (arena.hasPointerCapture(event.pointerId)) arena.releasePointerCapture(event.pointerId);
}
arena.addEventListener("pointerup", endDrag);
arena.addEventListener("pointercancel", endDrag);
document.addEventListener("keydown", (event) => {
  const tag = event.target.tagName;
  if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || tag === "BUTTON") return;
  if (event.key === " ") { event.preventDefault(); togglePlayback(); }
  else if (event.key === "ArrowLeft") { stopPlayback(); seek(state.position - 1); }
  else if (event.key === "ArrowRight") { stopPlayback(); seek(state.position + 1); }
  else if (event.key === "Home") { stopPlayback(); seek(0); }
  else if (event.key === "End" && state.model) { stopPlayback(); seek(state.model.playback.last_position); }
});

initialize();
