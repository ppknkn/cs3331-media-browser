/* Frame: same-origin local media explorer. User-provided names only use textContent. */
"use strict";

const $ = (id) => document.getElementById(id);
const icons = {
  folder: '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/></svg>',
  play: '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="m8 5 11 7-11 7Z"/></svg>'
};
const collator = new Intl.Collator("zh-CN", {numeric: true, sensitivity: "base"});
const state = {
  token: "", session: "", root: null, rootName: "", path: "", library: null,
  filter: "all", query: "", sort: "name", view: "grid", request: 0,
  controller: null, rootBusy: false, visibleMedia: [], viewerItems: [], viewerIndex: 0, zoom: 1
};

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function icon(name, className) {
  const element = node("span", className);
  // Only authored, immutable SVG constants are inserted here.
  element.innerHTML = icons[name];
  return element;
}

function mediaUrl(item) {
  return `/media/${encodeURIComponent(state.session)}/${item.path.split("/").map(encodeURIComponent).join("/")}`;
}

function bytes(value) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function date(value) {
  return new Date(value * 1000).toLocaleDateString("zh-CN", {year: "numeric", month: "2-digit", day: "2-digit"});
}

async function api(path, options = {}) {
  const response = await fetch(path, {cache: "no-store", ...options});
  let result;
  try { result = await response.json(); }
  catch { throw new Error("无法读取服务响应，请确认本地服务仍在运行。"); }
  if (!response.ok) {
    const error = new Error(result.error || "操作失败，请稍后重试。");
    error.code = result.code;
    error.status = response.status;
    throw error;
  }
  return result;
}

function notify(message, error = false) {
  $("status").replaceChildren(node("span", "", message));
  $("status").className = `status${error ? " error" : ""}`;
  $("status").hidden = !message;
}

function rootControls(busy) {
  state.rootBusy = busy;
  for (const id of ["openButton", "welcomeOpen", "pathButton", "pathSubmit", "emptyAction"]) $(id).disabled = busy;
  $("openButton").querySelector("span").textContent = busy ? "正在打开…" : "打开文件夹";
}

function updateRoot(summary) {
  state.root = summary.root;
  state.rootName = summary.name || "本地媒体库";
  state.session = summary.session;
  $("rootName").textContent = state.rootName;
  $("rootPath").textContent = state.root || "";
  $("rootPath").title = state.root || "";
  $("rootPanel").hidden = !state.root;
  $("welcome").hidden = !!state.root;
  $("toolbar").hidden = !state.root;
  $("breadcrumbs").hidden = !state.root;
  $("libraryStats").hidden = !state.root;
  if (!state.root) {
    $("content").hidden = true;
    $("empty").hidden = true;
    $("pageTitle").replaceChildren(document.createTextNode("你的每一帧，都值得看见"), node("span", "title-dot", "."));
    $("pageSubtitle").textContent = "打开一个本地文件夹，把散落的照片和视频变成你的私人图集。";
  }
}

async function initialize() {
  try {
    const summary = await api("/api/bootstrap");
    state.token = summary.token;
    updateRoot(summary);
    if (state.root) await loadFolder("");
  } catch (error) {
    notify(error.message, true);
  }
}

function breadcrumbs() {
  const container = $("breadcrumbs");
  container.replaceChildren();
  const root = node("button", "", state.rootName);
  root.type = "button";
  root.addEventListener("click", () => loadFolder(""));
  container.append(root);
  const parts = state.path.split("/").filter(Boolean);
  parts.forEach((part, index) => {
    container.append(node("span", "", "/"));
    const button = node("button", "", part);
    button.type = "button";
    button.title = part;
    button.addEventListener("click", () => loadFolder(parts.slice(0, index + 1).join("/")));
    if (index === parts.length - 1) button.setAttribute("aria-current", "location");
    container.append(button);
  });
  if (!parts.length) root.setAttribute("aria-current", "location");
  const name = parts.length ? parts[parts.length - 1] : "全部图集";
  $("pageTitle").replaceChildren(document.createTextNode(name), node("span", "title-dot", "."));
  $("pageSubtitle").textContent = parts.length ? "收好每一个值得记住的瞬间。" : "每个文件夹都是一个图集，让照片与视频重新被看见。";
}

async function loadFolder(path, preserveSearch = false) {
  if (!state.root) return;
  const request = ++state.request;
  const session = state.session;
  state.controller?.abort();
  state.controller = new AbortController();
  closeViewer();
  // Toolbar events during an in-flight scan must not render the previous album.
  state.library = null;
  state.visibleMedia = [];
  state.path = path;
  if (!preserveSearch) {
    state.query = "";
    $("searchInput").value = "";
  }
  breadcrumbs();
  $("loading").hidden = false;
  $("content").hidden = true;
  $("empty").hidden = true;
  $("refreshButton").disabled = true;
  notify("");
  try {
    const library = await api(`/api/library?${new URLSearchParams({path, session})}`, {signal: state.controller.signal});
    if (request !== state.request || session !== state.session) return;
    state.library = library;
    render();
    if (library.warnings.length) notify(library.warnings.join(" "));
  } catch (error) {
    if (error.name === "AbortError" || request !== state.request) return;
    if (error.code === "stale_session") {
      const summary = await api("/api/bootstrap");
      state.token = summary.token;
      updateRoot(summary);
      await loadFolder("");
      return;
    }
    state.library = null;
    notify(error.message, true);
    showEmpty("暂时无法打开这个图集", "文件夹可能已移动，或者无法读取。可点击刷新重试，也可通过上方路径返回其他图集。");
  } finally {
    if (request === state.request) {
      $("loading").hidden = true;
      $("refreshButton").disabled = false;
    }
  }
}

function filtered() {
  if (!state.library) return {albums: [], media: []};
  const query = state.query.trim().toLocaleLowerCase();
  const matches = (item) => !query || item.name.toLocaleLowerCase().includes(query);
  const sorter = (a, b) => {
    if (state.sort === "newest") return b.modified - a.modified || collator.compare(a.name, b.name);
    if (state.sort === "oldest") return a.modified - b.modified || collator.compare(a.name, b.name);
    return collator.compare(a.name, b.name);
  };
  return {
    // A truncated count is unknown, rather than proof that a type is absent.
    albums: state.library.albums.filter((album) => matches(album) && (state.filter === "all" || album.partial || (state.filter === "image" ? album.imageCount > 0 : album.videoCount > 0))).sort(sorter),
    media: state.library.media.filter((item) => matches(item) && (state.filter === "all" || state.filter === item.type)).sort(sorter)
  };
}

function coverImage(item, container, isAlbum = false) {
  const image = node("img");
  image.src = mediaUrl(item);
  image.alt = "";
  image.loading = "lazy";
  image.decoding = "async";
  image.addEventListener("error", () => {
    image.remove();
    const fallback = node("div", "media-fallback broken", "图片暂时无法预览");
    container.prepend(fallback);
    if (!isAlbum) container.title = "浏览器可能不支持此图片格式，或文件已经移走。";
  }, {once: true});
  container.append(image);
}

function albumCard(album) {
  const button = node("button", "album-card");
  button.type = "button";
  button.setAttribute("aria-label", `打开图集 ${album.name}，${album.partial ? "至少 " : ""}${album.count} 项媒体${album.partial ? "，统计未完成" : ""}`);
  const visual = node("div", "album-visual");
  if (album.cover?.type === "image") coverImage(album.cover, visual, true);
  else {
    const fallback = node("div", "album-fallback");
    fallback.append(icon("folder"), node("span", "", album.videoCount ? "移动的记忆" : "等待新的故事"));
    visual.append(fallback);
  }
  visual.append(icon("folder", "album-folder"), node("span", "album-count", `${album.count}${album.partial ? "+" : ""} 项`));
  const caption = node("div", "card-caption");
  const details = node("div", "card-details");
  const name = node("strong", "card-name", album.name);
  name.title = album.name;
  details.append(name, node("span", "card-subtitle", album.partial ? `已统计 ${album.count} 项 · 总数未知` : `${album.imageCount} 张图片 · ${album.videoCount} 个视频`));
  if (album.partial) button.title = "统计尚未完成，图集可能包含更多图片或视频；进入图集继续查看。";
  caption.append(details, node("span", "card-arrow", "↗"));
  button.append(visual, caption);
  button.addEventListener("click", () => loadFolder(album.path));
  return button;
}

function mediaCard(item, index) {
  const button = node("button", "media-card");
  button.type = "button";
  button.setAttribute("aria-label", `${item.type === "image" ? "查看图片" : "播放视频"} ${item.name}`);
  const visual = node("div", "media-visual");
  if (item.type === "image") coverImage(item, visual);
  else {
    visual.append(node("div", "media-fallback"), icon("play", "play-icon"));
    // Video previews are intentionally not loaded in the grid: playback starts on request.
  }
  visual.append(node("span", "media-badge", item.extension));
  const caption = node("div", "card-caption");
  const details = node("div", "card-details");
  const name = node("strong", "card-name", item.name);
  name.title = item.name;
  details.append(name, node("span", "card-subtitle", `${bytes(item.size)} · ${date(item.modified)}`));
  caption.append(details);
  button.append(visual, caption);
  button.addEventListener("click", () => openViewer(index));
  return button;
}

function showEmpty(title, text) {
  $("emptyTitle").textContent = title;
  $("emptyText").textContent = text;
  $("empty").hidden = false;
  $("content").hidden = true;
}

function render() {
  if (!state.library) return;
  const {albums, media} = filtered();
  state.visibleMedia = media;
  $("albumGrid").replaceChildren(...albums.map(albumCard));
  $("mediaGrid").replaceChildren(...media.map(mediaCard));
  $("albumsSection").hidden = albums.length === 0;
  $("mediaSection").hidden = media.length === 0;
  $("albumCount").textContent = albums.length;
  $("mediaCount").textContent = media.length;
  $("sideCount").textContent = state.library.albums.length;
  const total = state.library.media.length + state.library.albums.reduce((sum, album) => sum + album.count, 0);
  $("statTotal").textContent = total.toLocaleString("zh-CN") + (state.library.partial || state.library.albums.some((album) => album.partial) ? "+" : "");
  $("resultSummary").textContent = `${albums.length} 个图集 · ${media.length} 项当前文件夹媒体　/　支持键盘浏览　/　内容来自本地文件夹`;
  $("content").classList.toggle("list-view", state.view === "list");
  $("empty").hidden = true;
  $("content").hidden = false;
  if (!albums.length && !media.length) {
    if (state.query || state.filter !== "all") {
      showEmpty("没有找到匹配的内容", "试试其他关键词，或将类型筛选切回“全部”。搜索范围是当前文件夹下的图集名称和媒体名称。");
      $("emptyAction").textContent = "清除筛选";
    } else {
      showEmpty("这里还没有媒体", "当前文件夹没有支持的图片、视频或子文件夹。可打开其他文件夹，或添加媒体后点击刷新。");
      $("emptyAction").textContent = "打开其他文件夹";
    }
  }
}

async function changeRoot(path = null) {
  if (state.rootBusy || !state.token) return;
  rootControls(true);
  $("pathError").hidden = true;
  const isPicker = path === null;
  if (isPicker) notify("已打开本机文件夹选择窗口；如未看到窗口，可使用“输入路径”。选择窗口 90 秒后自动关闭。");
  try {
    const summary = await api(isPicker ? "/api/picker" : "/api/root", {
      method: "POST", headers: {"Content-Type": "application/json", "X-App-Token": state.token},
      body: JSON.stringify(isPicker ? {session: state.session} : {path, session: state.session})
    });
    if (summary.cancelled) { notify("已取消选择。随时可以打开一个文件夹。"); return; }
    state.controller?.abort();
    state.request++;
    state.library = null;
    updateRoot(summary);
    $("pathDialog").close();
    await loadFolder("");
  } catch (error) {
    if (error.code === "stale_session") {
      await initialize();
      notify("文件夹已在其他页面切换，已同步当前媒体库。");
    } else {
      notify(error.message, true);
      if ($("pathDialog").open) {
        $("pathError").textContent = error.message;
        $("pathError").hidden = false;
      }
      if (isPicker && ["picker_timeout", "picker_unavailable"].includes(error.code)) openPathDialog();
    }
  } finally { rootControls(false); }
}

function openPathDialog() {
  $("pathInput").value = state.root || "";
  $("pathError").hidden = true;
  if (!$("pathDialog").open) $("pathDialog").showModal();
  $("pathInput").focus();
  $("pathInput").select();
}

function stopMedia() {
  const video = $("viewerCanvas").querySelector("video");
  if (video) { video.pause(); video.removeAttribute("src"); video.load(); }
  $("viewerCanvas").replaceChildren();
}

function closeViewer() {
  stopMedia();
  if ($("viewer").open) $("viewer").close();
  document.body.style.overflow = "";
}

function openViewer(index) {
  state.viewerItems = [...state.visibleMedia];
  state.viewerIndex = index;
  if (!state.viewerItems.length) return;
  if (!$("viewer").open) $("viewer").showModal();
  document.body.style.overflow = "hidden";
  showViewer();
  $("viewerClose").focus();
}

function applyZoom(value) {
  state.zoom = Math.max(1, Math.min(3, value));
  const image = $("viewerCanvas").querySelector("img");
  if (image) {
    image.style.transform = `scale(${state.zoom})`;
    image.style.cursor = state.zoom > 1 ? "zoom-out" : "zoom-in";
  }
  $("zoomReset").textContent = state.zoom === 1 ? "适应" : `${Math.round(state.zoom * 100)}%`;
}

function showViewer() {
  stopMedia();
  const item = state.viewerItems[state.viewerIndex];
  if (!item) return;
  const isImage = item.type === "image";
  state.zoom = 1;
  $("viewerError").hidden = true;
  $("viewerName").textContent = item.name;
  $("viewerMeta").textContent = `${item.extension} · ${bytes(item.size)} · ${date(item.modified)}`;
  $("viewerCounter").textContent = `${state.viewerIndex + 1} / ${state.viewerItems.length}`;
  $("viewerTip").textContent = isImage ? "← → 切换 · Esc 关闭 · 双击图片放大" : "← → 切换 · Esc 关闭 · 使用播放器控件调整进度和音量";
  $("viewerPrev").disabled = $("viewerNext").disabled = state.viewerItems.length < 2;
  for (const id of ["zoomIn", "zoomOut", "zoomReset"]) $(id).hidden = !isImage;
  $("zoomReset").textContent = "适应";
  const element = node(isImage ? "img" : "video");
  element.src = mediaUrl(item);
  if (isImage) {
    element.alt = item.name;
    element.addEventListener("dblclick", () => applyZoom(state.zoom > 1 ? 1 : 2));
  } else {
    element.controls = true;
    element.preload = "metadata";
    element.playsInline = true;
    element.setAttribute("aria-label", item.name);
  }
  element.addEventListener("error", () => {
    if (!element.isConnected) return;
    $("viewerError").textContent = isImage ? "无法预览此图片。浏览器可能不支持该格式，或文件已移动；请刷新图集。" : "此视频暂时无法播放。容器支持并不代表编码支持；请使用浏览器支持的编码（如 MP4/H.264），或用系统播放器打开原文件。";
    $("viewerError").hidden = false;
  });
  $("viewerCanvas").append(element);
}

function moveViewer(delta) {
  if (!state.viewerItems.length) return;
  state.viewerIndex = (state.viewerIndex + delta + state.viewerItems.length) % state.viewerItems.length;
  showViewer();
}

function selectFilter(filter) {
  state.filter = filter;
  document.querySelectorAll(".filter-tab").forEach((button) => {
    const selected = button.dataset.filter === filter;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", selected);
  });
  render();
}

function setView(view) {
  state.view = view;
  for (const mode of ["grid", "list"]) {
    $(mode + "Button").classList.toggle("selected", mode === view);
    $(mode + "Button").setAttribute("aria-pressed", mode === view);
  }
  try { localStorage.setItem("frame-view", view); } catch { /* storage can be disabled */ }
  render();
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $("themeButton").querySelector("span").textContent = theme === "dark" ? "切换浅色外观" : "切换深色外观";
  try { localStorage.setItem("frame-theme", theme); } catch { /* storage can be disabled */ }
}

$("openButton").addEventListener("click", () => changeRoot());
$("welcomeOpen").addEventListener("click", () => changeRoot());
$("pathButton").addEventListener("click", openPathDialog);
$("pathClose").addEventListener("click", () => $("pathDialog").close());
$("pathCancel").addEventListener("click", () => $("pathDialog").close());
$("pathForm").addEventListener("submit", (event) => { event.preventDefault(); changeRoot($("pathInput").value.trim()); });
$("homeButton").addEventListener("click", () => loadFolder(""));
$("refreshButton").addEventListener("click", () => loadFolder(state.path, true));
$("searchInput").addEventListener("input", (event) => { state.query = event.target.value; render(); });
$("sortSelect").addEventListener("change", (event) => { state.sort = event.target.value; render(); });
document.querySelectorAll(".filter-tab").forEach((button) => button.addEventListener("click", () => selectFilter(button.dataset.filter)));
$("gridButton").addEventListener("click", () => setView("grid"));
$("listButton").addEventListener("click", () => setView("list"));
$("themeButton").addEventListener("click", () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
$("emptyAction").addEventListener("click", () => {
  if (state.query || state.filter !== "all") {
    state.query = "";
    $("searchInput").value = "";
    selectFilter("all");
  } else changeRoot();
});
$("viewerClose").addEventListener("click", closeViewer);
$("viewer").addEventListener("cancel", (event) => { event.preventDefault(); closeViewer(); });
$("viewer").addEventListener("close", () => { stopMedia(); document.body.style.overflow = ""; });
$("viewerPrev").addEventListener("click", () => moveViewer(-1));
$("viewerNext").addEventListener("click", () => moveViewer(1));
$("zoomIn").addEventListener("click", () => applyZoom(state.zoom + .25));
$("zoomOut").addEventListener("click", () => applyZoom(state.zoom - .25));
$("zoomReset").addEventListener("click", () => applyZoom(1));
document.addEventListener("keydown", (event) => {
  const editing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
  if ($("viewer").open) {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      // Preserve native player arrow seeking when the video itself has focus.
      if (document.activeElement?.tagName === "VIDEO") return;
      event.preventDefault();
      moveViewer(event.key === "ArrowLeft" ? -1 : 1);
    }
    if (event.key === "0") applyZoom(1);
    return;
  }
  if (event.key === "/" && !editing && state.root && !$("pathDialog").open) {
    event.preventDefault();
    $("searchInput").focus();
  }
});

try {
  setTheme(localStorage.getItem("frame-theme") === "dark" ? "dark" : "light");
  setView(localStorage.getItem("frame-view") === "list" ? "list" : "grid");
} catch { setTheme("light"); }
initialize();
