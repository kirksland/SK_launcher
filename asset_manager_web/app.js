const projects = [
  { name: "Nebula", path: "D:\\Productions\\Nebula", assets: 24, shots: 18, code: "NB" },
  { name: "Atlas", path: "D:\\Productions\\Atlas", assets: 31, shots: 26, code: "AT" },
  { name: "Echo Valley", path: "D:\\Productions\\EchoValley", assets: 16, shots: 12, code: "EV" },
  { name: "Kintsugi", path: "D:\\Productions\\Kintsugi", assets: 19, shots: 8, code: "KI" }
];

const entities = {
  assets: [
    { id: "a1", name: "Hero_Robot", group: "Character", context: "modeling", version: "v014", status: "Published", artist: "JM", updated: "12 min", ext: "USD", color: "#234858", glow: "rgba(84,217,232,.48)", shape: "45%", rotate: "-8deg" },
    { id: "a2", name: "Desert_Rover", group: "Vehicle", context: "lookdev", version: "v008", status: "In progress", artist: "CL", updated: "38 min", ext: "USD", color: "#554026", glow: "rgba(245,190,103,.46)", shape: "28%", rotate: "8deg" },
    { id: "a3", name: "Station_Core", group: "Environment", context: "modeling", version: "v021", status: "Published", artist: "JM", updated: "1 h", ext: "USD", color: "#25354e", glow: "rgba(108,156,255,.42)", shape: "8%", rotate: "0deg" },
    { id: "a4", name: "Void_Creature", group: "Character", context: "lookdev", version: "v006", status: "In progress", artist: "SD", updated: "2 h", ext: "USD", color: "#432c58", glow: "rgba(168,140,255,.48)", shape: "50%", rotate: "13deg" },
    { id: "a5", name: "Airlock_A7", group: "Props", context: "modeling", version: "v011", status: "Published", artist: "AK", updated: "hier", ext: "USD", color: "#29433d", glow: "rgba(100,214,155,.38)", shape: "10%", rotate: "0deg" },
    { id: "a6", name: "Pilot_Helmet", group: "Props", context: "lookdev", version: "v017", status: "Published", artist: "CL", updated: "hier", ext: "USD", color: "#49402d", glow: "rgba(245,190,103,.32)", shape: "50%", rotate: "-5deg" }
  ],
  shots: [
    { id: "s1", name: "SQ010_SH020", group: "Sequence 010", context: "animation", version: "v032", status: "Published", artist: "AK", updated: "9 min", ext: "MOV", color: "#263d4d", glow: "rgba(84,217,232,.35)", shape: "5%", rotate: "-2deg" },
    { id: "s2", name: "SQ010_SH030", group: "Sequence 010", context: "animation", version: "v019", status: "In progress", artist: "JM", updated: "42 min", ext: "MOV", color: "#4c3429", glow: "rgba(245,190,103,.42)", shape: "5%", rotate: "4deg" },
    { id: "s3", name: "SQ020_SH010", group: "Sequence 020", context: "animation", version: "v025", status: "Published", artist: "SD", updated: "3 h", ext: "MOV", color: "#302f51", glow: "rgba(168,140,255,.42)", shape: "5%", rotate: "-5deg" }
  ],
  library: [
    { id: "l1", name: "Rock_Formation_A", group: "Geometry", context: "modeling", version: "source", status: "Ready", artist: "JM", updated: "2 j", ext: "FBX", color: "#424035", glow: "rgba(245,190,103,.28)", shape: "38%", rotate: "12deg" },
    { id: "l2", name: "Surface_Mars_04", group: "Texture", context: "lookdev", version: "source", status: "Ready", artist: "CL", updated: "4 j", ext: "EXR", color: "#4b3028", glow: "rgba(239,121,80,.32)", shape: "4%", rotate: "0deg" },
    { id: "l3", name: "Antenna_Kit", group: "Geometry", context: "modeling", version: "source", status: "Ready", artist: "AK", updated: "1 sem", ext: "BLEND", color: "#283d43", glow: "rgba(84,217,232,.28)", shape: "12%", rotate: "-14deg" }
  ],
  videos: [
    { id: "v1", name: "SQ010_SH020_comp", group: "Daily Review", gallery: "Daily Review", sequence: "SQ010", context: "animation", version: "v032", status: "Approved", artist: "AK", updated: "9 min", age: 9, duration: 5.0, frames: "120 fr", ext: "MOV", board: "Nebula / Edit v12", source: "shots/SQ010/SH020/publish/SQ010_SH020_comp_v032.mov", color: "#263d4d", glow: "rgba(84,217,232,.35)", shape: "5%", rotate: "-2deg" },
    { id: "v2", name: "SQ010_SH030_anim", group: "Daily Review", gallery: "Daily Review", sequence: "SQ010", context: "animation", version: "v019", status: "Needs work", artist: "JM", updated: "42 min", age: 42, duration: 8.0, frames: "192 fr", ext: "MP4", board: "Nebula / Edit v12", source: "shots/SQ010/SH030/playblast/SQ010_SH030_anim_v019.mp4", color: "#4c3429", glow: "rgba(245,190,103,.42)", shape: "5%", rotate: "4deg" },
    { id: "v3", name: "SQ010_SH040_layout", group: "Sequence 010", gallery: "Sequence 010", sequence: "SQ010", context: "animation", version: "v011", status: "WIP", artist: "CL", updated: "1 h", age: 60, duration: 6.5, frames: "156 fr", ext: "MOV", board: "Nebula / Layout Board", source: "shots/SQ010/SH040/playblast/SQ010_SH040_layout_v011.mov", color: "#3b3153", glow: "rgba(168,140,255,.42)", shape: "8%", rotate: "-5deg" },
    { id: "v4", name: "SQ020_SH010_comp", group: "Client Selects", gallery: "Client Selects", sequence: "SQ020", context: "animation", version: "v025", status: "Approved", artist: "SD", updated: "3 h", age: 180, duration: 4.0, frames: "96 fr", ext: "MOV", board: "Nebula / Client Review 04", source: "shots/SQ020/SH010/publish/SQ020_SH010_comp_v025.mov", color: "#302f51", glow: "rgba(168,140,255,.42)", shape: "5%", rotate: "-5deg" },
    { id: "v5", name: "SQ020_SH020_fx", group: "Sequence 020", gallery: "Sequence 020", sequence: "SQ020", context: "animation", version: "v014", status: "WIP", artist: "JM", updated: "hier", age: 1440, duration: 12.0, frames: "288 fr", ext: "MP4", board: "Nebula / FX Board", source: "shots/SQ020/SH020/playblast/SQ020_SH020_fx_v014.mp4", color: "#24443f", glow: "rgba(100,214,155,.35)", shape: "15%", rotate: "3deg" },
    { id: "v6", name: "SQ030_SH010_light", group: "Client Selects", gallery: "Client Selects", sequence: "SQ030", context: "lookdev", version: "v007", status: "Review", artist: "AK", updated: "hier", age: 1500, duration: 7.5, frames: "180 fr", ext: "MOV", board: "Nebula / Client Review 04", source: "shots/SQ030/SH010/playblast/SQ030_SH010_light_v007.mov", color: "#4a3f29", glow: "rgba(245,190,103,.35)", shape: "35%", rotate: "-3deg" }
  ]
};

const state = { project: 0, kind: "assets", selected: "a1", query: "", context: "all", gallery: "all", sort: "board", compare: [], videoLimit: 60, inspectorTab: "details" };

const $ = (selector) => document.querySelector(selector);
const projectList = $("#project-list");
const assetGrid = $("#asset-grid");
const inspectorContent = $("#inspector-content");
const videoExtensions = new Set(["mp4", "mov", "avi", "mkv", "webm", "m4v"]);
const localObjectUrls = new Set();
const localVideoKeys = new Set();
const folderSources = [];

function renderProjects() {
  projectList.innerHTML = projects.map((project, index) => `
    <button class="project-button ${state.project === index ? "active" : ""}" data-project="${index}">
      <span class="project-dot"></span>
      <span>${project.name}</span>
      <small>${project.code}</small>
    </button>
  `).join("");
}

function renderProjectHeader() {
  const project = projects[state.project];
  $("#project-title").textContent = project.name;
  $("#breadcrumb-project").textContent = project.name;
  $("#project-path").textContent = project.path;
  $("#asset-count").textContent = project.assets;
  $("#shot-count").textContent = project.shots;
  $("#assets-tab-count").textContent = project.assets;
  $("#shots-tab-count").textContent = project.shots;
}

function filteredEntities() {
  const query = state.query.toLowerCase().trim();
  const items = entities[state.kind].filter(entity => {
    const matchesQuery = !query || `${entity.name} ${entity.group} ${entity.context}`.toLowerCase().includes(query);
    const matchesContext = state.kind === "videos" || state.context === "all" || entity.context === state.context;
    const matchesGallery = state.kind !== "videos" || state.gallery === "all" || entity.gallery === state.gallery;
    return matchesQuery && matchesContext && matchesGallery;
  });
  if (state.kind !== "videos") return items;
  if (state.sort === "board") return items;
  return [...items].sort((a, b) => {
    if (state.sort === "recent") return a.age - b.age;
    if (state.sort === "name") return a.name.localeCompare(b.name);
    if (state.sort === "duration") return b.duration - a.duration;
    return 0;
  });
}

function renderGrid() {
  const allItems = filteredEntities();
  const items = state.kind === "videos" ? allItems.slice(0, state.videoLimit) : allItems;
  assetGrid.classList.toggle("video-grid", state.kind === "videos");
  assetGrid.innerHTML = items.map(entity => {
    const thumbnailUrl = entity.localFile ? ensureLocalUrl(entity) : null;
    return `
    <article class="asset-card ${state.selected === entity.id ? "selected" : ""}" data-id="${entity.id}"
      style="--tone:${entity.color};--glow:${entity.glow};--shape:${entity.shape};--rotate:${entity.rotate}">
      <div class="thumbnail ${entity.localFile ? "local-video-thumbnail" : ""}">
        ${thumbnailUrl ? `<video class="thumb-video" src="${thumbnailUrl}" preload="metadata" muted playsinline></video>` : ""}
        <span class="thumb-type">${state.kind === "videos" ? (entity.localFile ? "LOCAL" : "DEMO") : entity.ext}</span>
        <button class="icon-button thumb-menu">•••</button>
        ${state.kind === "videos" ? `
          <button class="compare-toggle ${state.compare.includes(entity.id) ? "active" : ""}" data-compare="${entity.id}" title="Ajouter a la comparaison">${state.compare.includes(entity.id) ? "OK" : "+"}</button>
          <span class="video-duration">${entity.duration > 0 ? `${entity.duration.toFixed(1)}s` : entity.ext}</span>
          <span class="video-play ${entity.localFile ? "" : "demo"}">${entity.localFile ? "Lire" : "Demo"}</span>
        ` : ""}
      </div>
      <div class="asset-meta">
        <div class="asset-title-row">
          <strong>${entity.name}</strong>
          <span class="version">${entity.version}</span>
        </div>
        <p>${entity.group} · ${entity.context}${state.kind === "videos" ? ` · ${entity.frames}` : ""}</p>
        <div class="card-footer">
          <span class="status ${entity.status === "In progress" ? "wip" : ""}">${entity.status}</span>
          <span>${entity.updated}</span>
          <span class="mini-avatar">${entity.artist}</span>
        </div>
      </div>
    </article>
  `;
  }).join("");
  bindVideoThumbnails();
  $("#empty-state").hidden = items.length > 0;
  assetGrid.hidden = items.length === 0;
  const loadMoreButton = $("#load-more-videos");
  loadMoreButton.hidden = state.kind !== "videos" || items.length >= allItems.length;
  loadMoreButton.textContent = `Afficher plus de videos (${items.length}/${allItems.length})`;

  if (items.length && !items.some(item => item.id === state.selected)) {
    state.selected = items[0].id;
  }
  renderInspector();
  renderCompareTray();
}

function bindVideoThumbnails() {
  assetGrid.querySelectorAll(".thumb-video").forEach(video => {
    video.addEventListener("loadedmetadata", () => {
      if (Number.isFinite(video.duration) && video.duration > 0) {
        video.currentTime = Math.min(0.1, video.duration / 10);
      }
    }, { once: true });
  });
}

function selectedEntity() {
  return Object.values(entities).flat().find(entity => entity.id === state.selected) || entities.assets[0];
}

function isVideoEntity(entity) {
  return Boolean(entity && (entity.localFile || entity.id.startsWith("v")));
}

function renderInspector() {
  const entity = selectedEntity();
  const isLibrary = entity.id.startsWith("l");
  const isShot = entity.id.startsWith("s");
  const isVideo = isVideoEntity(entity);
  const role = isVideo ? "Board media" : isLibrary ? "Library asset" : isShot ? "Shot" : "Pipeline asset";
  const fileName = isVideo ? entity.source.split("/").pop() : `${entity.name}_${entity.version}.${isShot ? "mov" : isLibrary ? entity.ext.toLowerCase() : "usdnc"}`;
  const inspectorVideoUrl = isVideo && entity.localFile ? ensureLocalUrl(entity) : "";

  inspectorContent.innerHTML = `
    <div class="inspector-body">
      ${inspectorVideoUrl ? `
        <div class="inspector-video-wrap">
          <video class="real-video-player inspector-video-player" src="${inspectorVideoUrl}" preload="auto" playsinline></video>
          <button class="inspector-play-button" data-play-inspector aria-label="Lire la vidéo">
            <span>▶</span>
            <strong>Lire</strong>
          </button>
          <div class="video-player-message" hidden>
            <strong>Cette vidéo ne peut pas être lue par le navigateur.</strong>
            <span>Le fichier est trouvé, mais son codec n'est probablement pas compatible.</span>
          </div>
        </div>
      ` : `<div class="preview-visual" style="--tone:${entity.color};--glow:${entity.glow};--shape:${entity.shape};--rotate:${entity.rotate}">
        <div class="preview-controls">
          <span class="passive-preview-label">${isVideo ? "Preview indisponible" : "Preview"}</span>
          <span class="scrub"><i></i></span>
          <span class="frame-count">${isVideo ? entity.frames : isShot ? "042 / 120" : "Turntable"}</span>
        </div>
      </div>`}
      <div class="entity-header">
        <span class="type">${role}</span>
        <h2>${entity.name}</h2>
        <p>${entity.group} / ${entity.context}</p>
      </div>
      <div class="inspector-tabs">
        <button class="inspector-tab ${state.inspectorTab === "details" ? "active" : ""}" data-inspector-tab="details">Details</button>
        <button class="inspector-tab ${state.inspectorTab === "pipeline" ? "active" : ""}" data-inspector-tab="pipeline">Pipeline</button>
        <button class="inspector-tab ${state.inspectorTab === "history" ? "active" : ""}" data-inspector-tab="history">History</button>
      </div>
      ${renderInspectorTab(entity, fileName, role)}
    </div>
  `;
  queueMicrotask(() => bindInspectorVideo());
}

function renderInspectorTab(entity, fileName, role) {
  if (state.inspectorTab === "pipeline") {
    return `
      <div class="detail-section">
        <div class="section-title"><span>Pipeline status</span><a href="#">Healthy</a></div>
        <div class="process-row active">
          <span class="file-icon">USD</span>
          <span class="file-copy"><strong>publish.asset.usd</strong><small>Source et destination résolus</small></span>
          <span class="process-state">●</span>
        </div>
        <div class="process-row">
          <span class="file-icon">CHK</span>
          <span class="file-copy"><strong>validate.geometry</strong><small>Validation de topologie</small></span>
          <span class="process-state">●</span>
        </div>
        <button id="run-process" class="pipeline-action">Run selected process</button>
      </div>
      <div class="detail-section">
        <div class="section-title"><span>Execution plan</span></div>
        <div class="detail-grid">
          <div class="detail-item"><small>Context</small><strong>${entity.context}</strong></div>
          <div class="detail-item"><small>Backend</small><strong>Houdini</strong></div>
          <div class="detail-item"><small>Role</small><strong>${role}</strong></div>
          <div class="detail-item"><small>State</small><strong>Ready</strong></div>
        </div>
      </div>
    `;
  }

  if (state.inspectorTab === "history") {
    return `
      <div class="detail-section">
        <div class="section-title"><span>Recent activity</span><a href="#">Voir tout</a></div>
        ${["Published " + entity.version, "Preview generated", "Source updated"].map((item, i) => `
          <div class="file-row" style="margin-bottom:7px">
            <span class="file-icon">${i === 0 ? "PUB" : i === 1 ? "IMG" : "SRC"}</span>
            <span class="file-copy"><strong>${item}</strong><small>${i === 0 ? "Aujourd’hui, 14:32" : i === 1 ? "Hier, 18:04" : "Il y a 3 jours"}</small></span>
          </div>
        `).join("")}
      </div>
    `;
  }

  return `
    <div class="detail-section">
      <div class="section-title"><span>Overview</span><a href="#">Open folder ↗</a></div>
      <div class="detail-grid">
        <div class="detail-item"><small>Context</small><strong>${entity.context}</strong></div>
        <div class="detail-item"><small>Version</small><strong>${entity.version}</strong></div>
        <div class="detail-item"><small>Artist</small><strong>${entity.artist}</strong></div>
        <div class="detail-item"><small>Updated</small><strong>${entity.updated}</strong></div>
      </div>
    </div>
    ${isVideoEntity(entity) ? renderComfyPrompt(entity) : ""}
    ${isVideoEntity(entity) ? `
      <div class="detail-section">
        <div class="section-title"><span>Board provenance</span><a href="#">Ouvrir le board</a></div>
        <div class="source-path"><small>${entity.board}</small><strong>${entity.source}</strong></div>
        <div class="media-actions">
          <button class="pipeline-action" data-reveal-source>Telecharger une copie</button>
          <button class="pipeline-action secondary-action" data-add-sequence>Ajouter la sequence</button>
        </div>
      </div>
    ` : ""}
    <div class="detail-section">
      <div class="section-title"><span>Inventory</span><a href="#">Tout voir</a></div>
      <div class="file-row">
        <span class="file-icon">${entity.ext}</span>
        <span class="file-copy"><strong>${fileName}</strong><small>${entity.id.startsWith("s") ? "384 MB" : "48.2 MB"} · Published</small></span>
        <span class="process-state">✓</span>
      </div>
    </div>
    <div class="detail-section">
      <div class="section-title"><span>Pipeline</span><a href="#" data-open-pipeline>Inspecter</a></div>
      <div class="detail-grid">
        <div class="detail-item"><small>Status</small><strong style="color:var(--green)">● Healthy</strong></div>
        <div class="detail-item"><small>Artifacts</small><strong>3 registered</strong></div>
      </div>
    </div>
  `;
}

function renderComfyPrompt(entity) {
  if (entity.comfyMetadataState === "loading") {
    return `
      <div class="detail-section comfy-prompt-card">
        <div class="section-title"><span>Prompt</span><small>Analyse...</small></div>
      </div>
    `;
  }
  const metadata = entity.comfyMetadata;
  if (!metadata?.positivePrompt) return "";
  return `
    <div class="detail-section comfy-prompt-card">
      <div class="comfy-prompt-head">
        <span>Prompt</span>
        <button class="comfy-copy-button" data-copy-comfy="prompt" title="Copier le prompt">Copier</button>
      </div>
      <div class="comfy-prompt-text">${escapeHtml(metadata.positivePrompt)}</div>
    </div>
  `;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2400);
}

function showImportStatus(message, tone = "info") {
  const status = $("#video-import-status");
  status.hidden = false;
  status.dataset.tone = tone;
  status.textContent = message;
}

function setupVideoFilters() {
  const galleryFilter = $("#gallery-filter");
  const isVideoLibrary = state.kind === "videos";
  galleryFilter.hidden = !isVideoLibrary;
  $("#sort-filter").hidden = !isVideoLibrary;
  $("#context-filter").hidden = isVideoLibrary;
  $("#video-library-help").hidden = !isVideoLibrary;
  document.querySelectorAll(".video-action").forEach(button => { button.hidden = !isVideoLibrary; });
  if (!isVideoLibrary) return;
  const selectedGallery = state.gallery;
  galleryFilter.innerHTML = '<option value="all">Toutes les galeries</option>';
  [...new Set(entities.videos.map(video => video.gallery))].sort().forEach(gallery => {
    const option = document.createElement("option");
    option.value = gallery;
    option.textContent = gallery;
    galleryFilter.appendChild(option);
  });
  galleryFilter.value = [...galleryFilter.options].some(option => option.value === selectedGallery)
    ? selectedGallery
    : "all";
  state.gallery = galleryFilter.value;
}

function renderCompareTray() {
  const tray = $("#compare-tray");
  tray.hidden = state.kind !== "videos" || state.compare.length === 0;
  $("#compare-count").textContent = state.compare.length;
  $("#compare-items").innerHTML = state.compare.map(id => {
    const entity = entities.videos.find(video => video.id === id);
    return `<span title="${entity.name}">${entity.name.replace(/^.*_SH/, "SH")}</span>`;
  }).join("");
  $("#open-compare").disabled = state.compare.length < 2;
}

function toggleCompare(id) {
  if (state.compare.includes(id)) {
    state.compare = state.compare.filter(item => item !== id);
  } else if (state.compare.length < 4) {
    state.compare.push(id);
  } else {
    showToast("La comparaison est limitee a 4 medias");
  }
  renderGrid();
}

function openCompare() {
  if (state.compare.length < 2) return;
  $("#compare-grid").innerHTML = state.compare.map(id => {
    const entity = entities.videos.find(video => video.id === id);
    const localUrl = entity.localFile ? ensureLocalUrl(entity) : entity.localUrl;
    return `
      <article class="compare-player" style="--tone:${entity.color};--glow:${entity.glow};--shape:${entity.shape};--rotate:${entity.rotate}">
        ${localUrl
          ? `<video class="compare-video" src="${localUrl}" controls muted preload="metadata"></video>`
          : `<div class="preview-visual"><span class="compare-play">&#9654;</span></div>`}
        <div><strong>${entity.name}</strong><small>${entity.version} / ${entity.duration.toFixed(1)}s / ${entity.status}</small></div>
      </article>
    `;
  }).join("");
  $("#compare-modal").hidden = false;
}

function extensionOf(name) {
  return String(name).split(".").pop().toLowerCase();
}

function isVideoFile(file) {
  return file && videoExtensions.has(extensionOf(file.name));
}

function colorForName(name) {
  let hash = 0;
  for (const char of name) hash = ((hash << 5) - hash + char.charCodeAt(0)) | 0;
  const hues = [
    ["#263d4d", "rgba(84,217,232,.35)"],
    ["#4c3429", "rgba(245,190,103,.42)"],
    ["#302f51", "rgba(168,140,255,.42)"],
    ["#24443f", "rgba(100,214,155,.35)"]
  ];
  return hues[Math.abs(hash) % hues.length];
}

function registerLocalVideo(file, options = {}) {
  const relativePath = options.relativePath || file.webkitRelativePath || file.name;
  const localKey = options.localKey || relativePath;
  if (localVideoKeys.has(localKey)) return null;
  localVideoKeys.add(localKey);
  const [color, glow] = colorForName(relativePath);
  const gallery = options.gallery || relativePath.split(/[\\/]/).slice(0, -1).pop() || "Local folder";
  const entity = {
    id: `local-${crypto.randomUUID ? crypto.randomUUID() : Date.now() + Math.random()}`,
    name: file.name.replace(/\.[^.]+$/, ""),
    group: gallery,
    gallery,
    sequence: options.sequence || gallery,
    context: "review",
    version: "local",
    status: options.board ? "Board" : "Local",
    artist: "HD",
    updated: new Date(file.lastModified || Date.now()).toLocaleDateString("fr-FR"),
    age: Math.max(0, Date.now() - (file.lastModified || Date.now())),
    duration: 0,
    frames: "Local",
    ext: extensionOf(file.name).toUpperCase(),
    board: options.board || "Dossier local",
    source: relativePath,
    localKey,
    localFile: file,
    localUrl: null,
    mimeType: file.type || "",
    aspectRatio: null,
    color,
    glow,
    shape: "8%",
    rotate: "0deg"
  };
  entities.videos.push(entity);
  hydrateComfyMetadata(entity);
  return entity;
}

async function hydrateComfyMetadata(entity) {
  if (!entity.localFile || entity.comfyMetadataState) return;
  entity.comfyMetadataState = "loading";
  try {
    entity.comfyMetadata = await readComfyVideoMetadata(entity.localFile);
    entity.comfyMetadataState = entity.comfyMetadata ? "ready" : "empty";
  } catch (error) {
    entity.comfyMetadata = null;
    entity.comfyMetadataState = "error";
  }
  if (state.selected === entity.id) renderInspector();
}

async function readComfyVideoMetadata(file) {
  const regionSize = 8 * 1024 * 1024;
  const regions = file.size <= regionSize * 2
    ? [file]
    : [file.slice(Math.max(0, file.size - regionSize)), file.slice(0, regionSize)];
  for (const region of regions) {
    const text = new TextDecoder("utf-8", { fatal: false }).decode(await region.arrayBuffer());
    const payload = extractComfyPayload(text);
    if (!payload) continue;
    const prompt = coerceJsonObject(payload.prompt);
    const workflow = coerceJsonObject(payload.workflow);
    if (!Object.keys(prompt).length && !Object.keys(workflow).length) continue;
    const texts = extractComfyPromptTexts(prompt);
    const sampler = findComfySampler(prompt);
    return {
      positivePrompt: texts.positive,
      negativePrompt: texts.negative,
      seed: numberOrNull(sampler.seed),
      steps: numberOrNull(sampler.steps),
      cfg: numberOrNull(sampler.cfg),
      sampler: String(sampler.sampler_name || ""),
      scheduler: String(sampler.scheduler || ""),
      model: findComfyModel(prompt),
      workflow
    };
  }
  return null;
}

function extractComfyPayload(text) {
  let markerIndex = text.indexOf('"prompt"');
  while (markerIndex >= 0) {
    const objectStart = text.lastIndexOf("{", markerIndex);
    const jsonText = objectStart >= 0 ? extractBalancedJson(text, objectStart) : "";
    if (jsonText) {
      try {
        const payload = JSON.parse(jsonText);
        if (payload && (payload.prompt != null || payload.workflow != null)) return payload;
      } catch (error) {
        // Continue to the next prompt marker.
      }
    }
    markerIndex = text.indexOf('"prompt"', markerIndex + 8);
  }
  return null;
}

function extractBalancedJson(text, start) {
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let index = start; index < text.length; index += 1) {
    const char = text[index];
    if (inString) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === '"') inString = false;
      continue;
    }
    if (char === '"') inString = true;
    else if (char === "{") depth += 1;
    else if (char === "}") {
      depth -= 1;
      if (depth === 0) return text.slice(start, index + 1);
    }
  }
  return "";
}

function coerceJsonObject(value) {
  if (value && typeof value === "object" && !Array.isArray(value)) return value;
  if (typeof value !== "string") return {};
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch (error) {
    return {};
  }
}

function extractComfyPromptTexts(prompt) {
  const positive = [];
  const negative = [];
  Object.values(prompt).forEach(node => {
    if (!node || typeof node !== "object" || !node.inputs) return;
    const text = typeof node.inputs.text === "string" ? node.inputs.text.trim() : "";
    if (!text) return;
    const title = `${node.class_type || ""} ${node._meta?.title || ""}`.toLowerCase();
    (title.includes("negative") || /\bneg\b/.test(title) ? negative : positive).push(text);
  });
  return { positive: positive.join("\n\n"), negative: negative.join("\n\n") };
}

function findComfySampler(prompt) {
  return Object.values(prompt)
    .map(node => node?.inputs)
    .find(inputs => inputs && inputs.seed != null && (inputs.steps != null || inputs.sampler_name)) || {};
}

function findComfyModel(prompt) {
  for (const key of ["unet_name", "ckpt_name", "model_name", "vae_name"]) {
    for (const node of Object.values(prompt)) {
      const value = node?.inputs?.[key];
      if (typeof value === "string" && value.trim()) return value.trim();
    }
  }
  return "";
}

function numberOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function ensureLocalUrl(entity) {
  if (!entity.localUrl && entity.localFile) {
    entity.localUrl = URL.createObjectURL(entity.localFile);
    localObjectUrls.add(entity.localUrl);
  }
  return entity.localUrl;
}

function bindInspectorVideo() {
  const player = inspectorContent.querySelector(".real-video-player");
  if (!player) return;
  const message = inspectorContent.querySelector(".video-player-message");
  const playButton = inspectorContent.querySelector("[data-play-inspector]");
  const showPlaybackError = () => {
    player.hidden = true;
    if (playButton) playButton.hidden = true;
    if (message) message.hidden = false;
  };
  player.addEventListener("error", showPlaybackError, { once: true });
  if (selectedEntity().playbackError) {
    showPlaybackError();
    return;
  }

  player.addEventListener("loadedmetadata", () => {
    if (Number.isFinite(player.duration) && player.duration > 0) {
      player.currentTime = Math.min(0.1, player.duration / 10);
    }
  }, { once: true });

  playButton?.addEventListener("click", () => {
    player.controls = true;
    player.muted = false;
    playButton.hidden = true;
    const playRequest = player.play();
    if (playRequest) {
      playRequest.catch(error => {
        if (error.name !== "NotAllowedError") showPlaybackError();
      });
    }
  });
}

function addFolderSource(label, count, kind = "folder") {
  folderSources.push({ label, count, kind });
  const host = $("#folder-sources");
  host.hidden = false;
  host.innerHTML = folderSources.map(source => `
    <span><b>${source.kind === "board" ? "BOARD" : "DOSSIER"}</b>${source.label}<small>${source.count} videos</small></span>
  `).join("");
}

async function walkDirectory(handle, prefix = "") {
  const files = [];
  for await (const [name, entry] of handle.entries()) {
    const relativePath = prefix ? `${prefix}/${name}` : name;
    if (entry.kind === "file") {
      const file = await entry.getFile();
      files.push({ file, relativePath });
    } else if (entry.kind === "directory") {
      files.push(...await walkDirectory(entry, relativePath));
    }
  }
  return files;
}

async function importDirectoryFiles(files, rootName, boardOnly = false) {
  showImportStatus(`Analyse de ${files.length} fichier${files.length > 1 ? "s" : ""} dans ${rootName}...`);
  const boardEntry = files.find(entry => entry.relativePath === ".skyforge_board.json");
  let boardVideoPaths = null;
  if (boardOnly && !boardEntry) {
    showImportStatus("Aucun .skyforge_board.json trouvé dans ce dossier.", "error");
    showToast("Ce dossier ne contient pas de .skyforge_board.json");
    return;
  }
  if (boardEntry) {
    try {
      const payload = JSON.parse(await boardEntry.file.text());
      boardVideoPaths = new Set(
        (Array.isArray(payload.items) ? payload.items : [])
          .filter(item => item && item.type === "video" && item.file)
          .map(item => `.skyforge_board_assets/${String(item.file).replace(/\\/g, "/")}`)
      );
    } catch (error) {
      showImportStatus("Le fichier .skyforge_board.json est invalide.", "error");
      showToast("Le fichier .skyforge_board.json est invalide");
      return;
    }
  }
  const candidates = files.filter(entry => {
    if (!isVideoFile(entry.file)) return false;
    return !boardOnly || (boardVideoPaths && boardVideoPaths.has(entry.relativePath));
  });
  const addedEntities = candidates.map(entry => registerLocalVideo(entry.file, {
    relativePath: entry.relativePath,
    localKey: `${rootName}/${entry.relativePath}`,
    gallery: boardOnly ? `Board · ${rootName}` : rootName,
    board: boardOnly ? rootName : ""
  })).filter(Boolean);
  if (!addedEntities.length) {
    showImportStatus(
      candidates.length
        ? "Ces vidéos sont déjà présentes dans la bibliothèque."
        : boardOnly
        ? "Le Board a été trouvé, mais aucune vidéo référencée n'est présente dans .skyforge_board_assets."
        : "Aucune vidéo trouvée. Formats recherchés: MP4, MOV, AVI, MKV, WebM et M4V.",
      candidates.length ? "info" : "error"
    );
  } else {
    showImportStatus(`${addedEntities.length} vidéo${addedEntities.length > 1 ? "s" : ""} chargée${addedEntities.length > 1 ? "s" : ""}. Clique pour inspecter, double-clique pour lire.`, "success");
  }
  addFolderSource(rootName, addedEntities.length, boardOnly ? "board" : "folder");
  state.kind = "videos";
  state.videoLimit = 60;
  state.selected = addedEntities.length ? addedEntities[0].id : state.selected;
  document.querySelectorAll(".tab").forEach(item => item.classList.toggle("active", item.dataset.kind === "videos"));
  setupVideoFilters();
  renderGrid();
  showToast(`${addedEntities.length} video${addedEntities.length > 1 ? "s" : ""} ajoutee${addedEntities.length > 1 ? "s" : ""}`);
}

async function chooseDirectory(boardOnly = false) {
  const input = $("#folder-input");
  input.dataset.boardOnly = boardOnly ? "true" : "false";
  input.value = "";
  showImportStatus("Choisis maintenant le dossier dans la fenêtre qui vient de s'ouvrir.");
  input.click();
}

function openVideoModal(entity) {
  const modal = $("#video-modal");
  const player = $("#video-modal-player");
  const error = $("#video-modal-error");
  $("#video-modal-title").textContent = entity.name;
  $("#video-modal-path").textContent = entity.source;
  error.hidden = true;
  player.hidden = false;
  player.src = ensureLocalUrl(entity);
  player.onloadedmetadata = () => {
    if (Number.isFinite(player.duration)) entity.duration = player.duration;
    if (player.videoWidth > 0 && player.videoHeight > 0) {
      entity.aspectRatio = `${player.videoWidth} / ${player.videoHeight}`;
    }
  };
  player.onerror = () => {
    player.hidden = true;
    error.hidden = false;
  };
  modal.hidden = false;
  const request = player.play();
  if (request) {
    request.catch(playError => {
      if (playError.name !== "NotAllowedError") {
        player.hidden = true;
        error.hidden = false;
      }
    });
  }
}

function closeVideoModal() {
  const modal = $("#video-modal");
  const player = $("#video-modal-player");
  player.pause();
  player.removeAttribute("src");
  player.load();
  modal.hidden = true;
}

projectList.addEventListener("click", event => {
  const button = event.target.closest("[data-project]");
  if (!button) return;
  state.project = Number(button.dataset.project);
  renderProjects();
  renderProjectHeader();
  showToast(`Projet ${projects[state.project].name} chargé`);
});

document.querySelector(".tabs").addEventListener("click", event => {
  const tab = event.target.closest("[data-kind]");
  if (!tab) return;
  state.kind = tab.dataset.kind;
  state.selected = entities[state.kind][0].id;
  document.querySelectorAll(".tab").forEach(item => item.classList.toggle("active", item === tab));
  setupVideoFilters();
  renderGrid();
});

assetGrid.addEventListener("click", event => {
  const compareButton = event.target.closest("[data-compare]");
  if (compareButton) {
    event.stopPropagation();
    toggleCompare(compareButton.dataset.compare);
    return;
  }
  const card = event.target.closest("[data-id]");
  if (!card) return;
  state.selected = card.dataset.id;
  renderGrid();
  $("#inspector").classList.add("open");
  const entity = selectedEntity();
  if (isVideoEntity(entity) && !entity.localFile) {
    showToast("Cette carte est une donnee de demonstration. Ajoute un dossier pour lire un vrai fichier.");
  }
});

assetGrid.addEventListener("dblclick", event => {
  const card = event.target.closest("[data-id]");
  if (!card || event.target.closest("[data-compare]")) return;
  state.selected = card.dataset.id;
  const entity = selectedEntity();
  if (entity.localFile) {
    openVideoModal(entity);
  } else if (isVideoEntity(entity)) {
    showToast("Cette carte est une donnee de demonstration. Ajoute un dossier pour lire un vrai fichier.");
  }
});

inspectorContent.addEventListener("click", event => {
  const tab = event.target.closest("[data-inspector-tab]");
  if (tab) {
    state.inspectorTab = tab.dataset.inspectorTab;
    renderInspector();
    return;
  }
  if (event.target.closest("[data-open-pipeline]")) {
    event.preventDefault();
    state.inspectorTab = "pipeline";
    renderInspector();
    return;
  }
  const runButton = event.target.closest("#run-process");
  if (runButton) {
    runButton.disabled = true;
    runButton.textContent = "Process en cours...";
    window.setTimeout(() => {
      runButton.disabled = false;
      runButton.textContent = "Run selected process";
      showToast(`publish.asset.usd terminé pour ${selectedEntity().name}`);
    }, 1400);
  }
  if (event.target.closest("[data-reveal-source]")) {
    const entity = selectedEntity();
    if (!entity.localUrl) {
      showToast(`Source simulee: ${entity.source}`);
      return;
    }
    const link = document.createElement("a");
    link.href = entity.localUrl;
    link.download = entity.source.split(/[\\/]/).pop();
    link.click();
    showToast(`Copie preparee: ${link.download}`);
  }
  if (event.target.closest("[data-add-sequence]")) {
    showToast(`Sequence ${selectedEntity().sequence} ajoutee a la selection`);
  }
  const copyComfy = event.target.closest("[data-copy-comfy]");
  if (copyComfy) {
    const metadata = selectedEntity().comfyMetadata;
    if (!metadata) return;
    const text = metadata.positivePrompt;
    copyTextToClipboard(text || "");
    copyComfy.textContent = "Copié";
    window.setTimeout(() => { copyComfy.textContent = "Copier"; }, 1200);
    showToast("Prompt copié");
  }
});

async function copyTextToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch (error) {
      // file:// pages may not have clipboard permission.
    }
  }
  const field = document.createElement("textarea");
  field.value = text;
  field.setAttribute("readonly", "");
  field.style.position = "fixed";
  field.style.opacity = "0";
  document.body.appendChild(field);
  field.select();
  document.execCommand("copy");
  field.remove();
}

$("#search").addEventListener("input", event => {
  state.query = event.target.value;
  state.videoLimit = 60;
  renderGrid();
});

$("#context-filter").addEventListener("change", event => {
  state.context = event.target.value;
  renderGrid();
});

$("#gallery-filter").addEventListener("change", event => {
  state.gallery = event.target.value;
  state.videoLimit = 60;
  renderGrid();
});

$("#open-board-button").addEventListener("click", () => chooseDirectory(true));
$("#add-folder-button").addEventListener("click", () => chooseDirectory(false));
$("#add-files-button").addEventListener("click", () => {
  const input = $("#video-files-input");
  input.value = "";
  showImportStatus("Choisis une ou plusieurs vidéos dans la fenêtre qui vient de s'ouvrir.");
  input.click();
});
$("#folder-input").addEventListener("change", async event => {
  if (!event.target.files.length) {
    showImportStatus("Aucun dossier sélectionné.", "error");
    return;
  }
  const files = [...event.target.files].map(file => ({
    file,
    relativePath: file.webkitRelativePath.split("/").slice(1).join("/")
  }));
  const rootName = event.target.files[0]?.webkitRelativePath.split("/")[0] || "Dossier local";
  await importDirectoryFiles(files, rootName, event.target.dataset.boardOnly === "true");
  event.target.value = "";
});
$("#video-files-input").addEventListener("change", async event => {
  if (!event.target.files.length) {
    showImportStatus("Aucune vidéo sélectionnée.", "error");
    return;
  }
  const files = [...event.target.files].map(file => ({ file, relativePath: file.name }));
  await importDirectoryFiles(files, "Sélection manuelle", false);
  event.target.value = "";
});

$("#sort-filter").addEventListener("change", event => {
  state.sort = event.target.value;
  state.videoLimit = 60;
  renderGrid();
});

$("#load-more-videos").addEventListener("click", () => {
  state.videoLimit += 60;
  renderGrid();
});

$("#clear-compare").addEventListener("click", () => {
  state.compare = [];
  renderGrid();
});
$("#open-compare").addEventListener("click", openCompare);
$("#close-compare").addEventListener("click", () => { $("#compare-modal").hidden = true; });
$("#compare-modal").addEventListener("click", event => {
  if (event.target.id === "compare-modal") event.currentTarget.hidden = true;
});
$("#close-video-modal").addEventListener("click", closeVideoModal);
$("#video-modal").addEventListener("click", event => {
  if (event.target.id === "video-modal") closeVideoModal();
});

$("#refresh-button").addEventListener("click", event => {
  const button = event.currentTarget;
  button.classList.add("loading");
  button.disabled = true;
  window.setTimeout(() => {
    button.classList.remove("loading");
    button.disabled = false;
    showToast("Workspace synchronisé");
  }, 900);
});

$("#menu-button").addEventListener("click", () => document.body.classList.toggle("menu-open"));
$("#close-inspector").addEventListener("click", () => $("#inspector").classList.remove("open"));

document.addEventListener("keydown", event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    $("#search").focus();
  }
  if (event.key === "Escape") {
    $("#search").blur();
    document.body.classList.remove("menu-open");
    $("#inspector").classList.remove("open");
    $("#compare-modal").hidden = true;
    closeVideoModal();
  }
});

window.addEventListener("beforeunload", () => {
  localObjectUrls.forEach(url => URL.revokeObjectURL(url));
});

renderProjects();
renderProjectHeader();
setupVideoFilters();
renderGrid();
