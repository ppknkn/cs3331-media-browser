/* Reproducible headless acceptance checks. Uses only artificial offline demo files.
 * Set NODE_PATH to a Playwright installation and PYTHON_EXE to Python 3.10+.
 * Optional BROWSER_CHANNEL=msedge|chrome (default msedge on Windows).
 */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const {spawn} = require("node:child_process");
const {chromium} = require("playwright");

const project = path.resolve(__dirname, "..");
const evidence = path.join(project, "docs", "test-results");
const screenshots = path.join(project, "docs", "screenshots");
fs.mkdirSync(evidence, {recursive: true});
fs.mkdirSync(screenshots, {recursive: true});
const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const started = new Date().toISOString();
const records = [];
const consoleErrors = [];
const pageErrors = [];
const expectedConsoleErrors = [];
let expectedErrorWindow = false;
let browser, server, serverOutput = "", baseURL;
// Also preserve errors originating in asynchronous browser event callbacks.
let abortAsync;
const asynchronousFailure = new Promise((_, reject) => {abortAsync = reject;});
process.on("unhandledRejection", error => abortAsync(error));
const fixture = fs.mkdtempSync(path.join(os.tmpdir(), "frame-e2e-"));
const library = path.join(fixture, "人工演示媒体");
const empty = path.join(fixture, "空媒体库");
const specialName = "中文 ［img onerror=alert(1)］ & #.jpg";
fs.mkdirSync(empty);
const python = process.env.PYTHON_EXE || (process.platform === "win32"
  ? path.join(os.homedir(), "miniconda3", "envs", "cheshi_handedit", "python.exe") : "python3");

async function check(name, action) {
  const begin = performance.now();
  try {
    await action();
    records.push({name, status: "passed", seconds: +((performance.now() - begin) / 1000).toFixed(4)});
    console.log("PASS " + name);
  } catch (error) {
    records.push({name, status: "failed", seconds: +((performance.now() - begin) / 1000).toFixed(4), error: error.stack});
    console.error("FAIL " + name + "\n" + error.stack);
    throw error;
  }
}

async function startServer() {
  server = spawn(python, ["-u", "app.py", "--port", "0", "--no-browser"], {
    cwd: project, windowsHide: true, env: {...process.env, PYTHONIOENCODING: "utf-8"}, stdio: ["ignore", "pipe", "pipe"]
  });
  server.stderr.on("data", data => { serverOutput += data.toString("utf8"); });
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Server startup timeout: " + serverOutput)), 15000);
    server.stdout.on("data", data => {
      serverOutput += data.toString("utf8");
      const match = serverOutput.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (match) { baseURL = match[0]; clearTimeout(timer); resolve(); }
    });
    server.once("error", error => { clearTimeout(timer); reject(error); });
    server.once("exit", code => { clearTimeout(timer); reject(new Error("Server exited " + code + ": " + serverOutput)); });
  });
}

function monitor(page) {
  page.on("pageerror", error => pageErrors.push(error.stack));
  page.on("console", message => {
    if (message.type() === "error") (expectedErrorWindow ? expectedConsoleErrors : consoleErrors).push(message.text());
  });
}

async function visible(page, selector) { await page.locator(selector).waitFor({state: "visible"}); }
async function hidden(page, selector) { await page.locator(selector).waitFor({state: "hidden"}); }
async function settle(page) { await hidden(page, "#loading"); await page.waitForFunction(() => !document.querySelector("#refreshButton").disabled); }
async function loadPath(page, value) {
  await page.locator("#pathButton").click();
  await page.locator("#pathInput").fill(value);
  await page.locator("#pathSubmit").click();
  await hidden(page, "#pathDialog");
  await settle(page);
}
async function noOverflow(page) {
  const dimensions = await page.evaluate(() => ({width: innerWidth, scroll: document.documentElement.scrollWidth}));
  assert.ok(dimensions.scroll <= dimensions.width + 1, JSON.stringify(dimensions));
}

async function captureScreenshot(page, filename, fullPage = false) {
  // Public assignment screenshots hide the complete local directory path.
  // Toggle the native hidden attribute only during capture and restore it afterwards.
  // This avoids injecting inline CSS, which the application's CSP correctly blocks.
  const rootPath = page.locator("#rootPath");
  const wasHidden = await rootPath.evaluate(element => element.hidden);
  await rootPath.evaluate(element => {element.hidden = true;});
  try {
    await page.screenshot({path: path.join(screenshots, filename), fullPage});
  } finally {
    await rootPath.evaluate((element, hidden) => {element.hidden = hidden;}, wasHidden);
  }
}

async function main() {
  try {
    if (!fs.existsSync(path.join(project, "demo-media", "旅行记", "03-海边短片.mp4"))) {
      throw new Error("Generate demo-media first: python scripts/generate_demo.py --ffmpeg <ffmpeg path>");
    }
    fs.cpSync(path.join(project, "demo-media"), library, {recursive: true});
    fs.copyFileSync(path.join(library, "01-海边暮色.jpg"), path.join(library, specialName));
    fs.utimesSync(path.join(library, "01-海边暮色.jpg"), 1600000000, 1600000000);
    fs.utimesSync(path.join(library, "02-山间晨光.jpg"), 1700000000, 1700000000);
    fs.utimesSync(path.join(library, specialName), 1800000000, 1800000000);
    await startServer();
    const launch = {headless: true};
    const channel = process.env.BROWSER_CHANNEL || (process.platform === "win32" ? "msedge" : "");
    if (channel) launch.channel = channel;
    browser = await chromium.launch(launch);
    const context = await browser.newContext({viewport: {width: 1440, height: 1000}, locale: "zh-CN"});
    const page = await context.newPage();
    monitor(page);

    await check("welcome and real manual absolute-path open", async () => {
      await page.goto(baseURL);
      await visible(page, "#welcome");
      await loadPath(page, library);
      assert.equal(await page.locator(".album-card").count(), 2);
      assert.equal(await page.locator(".media-card").count(), 3);
      assert.equal(await page.locator("#rootName").innerText(), "人工演示媒体");
    });
    await check("Unicode and HTML-like filename renders as text", async () => {
      const item = page.getByRole("button", {name: "查看图片 " + specialName, exact: true});
      assert.ok(await item.isVisible());
      assert.equal(await item.locator(".card-name").innerText(), specialName);
      assert.equal(await item.locator(".card-name img, .card-name script").count(), 0);
      await page.locator("#searchInput").fill("［img");
      assert.equal(await page.locator(".media-card").count(), 1);
      await page.locator("#searchInput").fill("");
    });
    await check("search, no results and clear filters", async () => {
      await page.locator("#searchInput").fill("城市");
      assert.equal(await page.locator(".album-card").count(), 1);
      assert.equal(await page.locator(".media-card").count(), 0);
      await page.locator("#searchInput").fill("no-such-media");
      await visible(page, "#empty");
      assert.match(await page.locator("#emptyTitle").innerText(), /没有找到/);
      await page.locator("#emptyAction").click();
      await visible(page, "#content");
      assert.equal(await page.locator(".album-card").count(), 2);
    });
    await check("sort by oldest, newest and name", async () => {
      await page.locator("#sortSelect").selectOption("oldest");
      assert.equal(await page.locator("#mediaGrid .card-name").first().innerText(), "01-海边暮色.jpg");
      await page.locator("#sortSelect").selectOption("newest");
      assert.equal(await page.locator("#mediaGrid .card-name").first().innerText(), specialName);
      await page.locator("#sortSelect").selectOption("name");
      assert.equal(await page.locator("#mediaGrid .card-name").first().innerText(), "01-海边暮色.jpg");
    });
    await check("list view, grid view, theme and persistence", async () => {
      await page.locator("#listButton").click();
      assert.ok(await page.locator("#content").evaluate(node => node.classList.contains("list-view")));
      await page.locator("#themeButton").click();
      assert.equal(await page.locator("html").getAttribute("data-theme"), "dark");
      await page.reload(); await settle(page);
      assert.equal(await page.locator("html").getAttribute("data-theme"), "dark");
      assert.ok(await page.locator("#content").evaluate(node => node.classList.contains("list-view")));
      await page.locator("#themeButton").click();
      await page.locator("#gridButton").click();
    });
    await check("desktop layout and gallery screenshot", async () => {
      // Filename adversarial case is complete; gallery screenshots show the 9 original demo items.
      fs.unlinkSync(path.join(library, specialName));
      await page.locator("#refreshButton").click(); await settle(page);
      await noOverflow(page);
      await page.locator("#mediaGrid img").first().waitFor({state: "visible"});
      await page.waitForFunction(() => [...document.querySelectorAll("#content img")].every(img => img.complete && img.naturalWidth > 0));
      await captureScreenshot(page, "desktop-gallery.png", true);
    });
    await check("image next, previous, zoom, Escape and focus restoration", async () => {
      const first = page.getByRole("button", {name: "查看图片 01-海边暮色.jpg", exact: true});
      await first.click();
      await visible(page, "#viewer");
      await page.waitForFunction(() => document.querySelector("#viewerCanvas img")?.naturalWidth > 0);
      assert.equal(await page.locator("#viewerName").innerText(), "01-海边暮色.jpg");
      await page.keyboard.press("ArrowRight");
      assert.equal(await page.locator("#viewerName").innerText(), "02-山间晨光.jpg");
      await page.locator("#viewerPrev").click();
      assert.equal(await page.locator("#viewerName").innerText(), "01-海边暮色.jpg");
      await page.locator("#zoomIn").click();
      assert.match(await page.locator("#viewerCanvas img").getAttribute("style"), /scale\(1\.25\)/);
      await page.locator("#zoomReset").click();
      assert.match(await page.locator("#viewerCanvas img").getAttribute("style"), /scale\(1\)/);
      await page.locator("#viewerCanvas img").dblclick();
      assert.match(await page.locator("#viewerCanvas img").getAttribute("style"), /scale\(2\)/);
      await page.locator("#zoomReset").click();
      await captureScreenshot(page, "image-viewer.png");
      await page.keyboard.press("Escape");
      await hidden(page, "#viewer");
      assert.ok(await first.evaluate(node => node === document.activeElement));
    });
    await check("nested albums and breadcrumb navigation", async () => {
      await page.getByRole("button", {name: /打开图集 旅行记/}).click(); await settle(page);
      assert.equal(await page.locator(".media-card").count(), 3);
      await page.getByRole("button", {name: /打开图集 山间小径/}).click(); await settle(page);
      assert.equal(await page.locator(".media-card").count(), 2);
      assert.equal(await page.locator("#breadcrumbs button").count(), 3);
      await page.locator("#breadcrumbs").getByRole("button", {name: "旅行记", exact: true}).click(); await settle(page);
      assert.equal(await page.locator(".media-card").count(), 3);
    });
    await check("image and video filters", async () => {
      await page.locator('[data-filter="image"]').click();
      assert.equal(await page.locator(".media-card").count(), 2);
      assert.equal(await page.locator(".album-card").count(), 1);
      await page.locator('[data-filter="video"]').click();
      assert.equal(await page.locator(".media-card").count(), 1);
      assert.equal(await page.locator(".album-card").count(), 0);
    });
    await check("real H.264 playback advances and seeks", async () => {
      await page.getByRole("button", {name: "播放视频 03-海边短片.mp4", exact: true}).click();
      await page.waitForFunction(() => {const v = document.querySelector("#viewerCanvas video"); return v && v.readyState >= 2 && v.duration > 0;});
      assert.ok(await page.locator("#zoomIn").isHidden());
      const before = await page.locator("video").evaluate(async video => {video.muted = true; await video.play(); return video.currentTime;});
      await page.waitForFunction(before => document.querySelector("video").currentTime > before + .3, before);
      await page.locator("video").evaluate(video => {video.pause(); video.currentTime = 2.5;});
      await page.waitForFunction(() => {const v = document.querySelector("video"); return !v.seeking && Math.abs(v.currentTime - 2.5) < .15;});
      const playback = await page.locator("video").evaluate(video => ({duration: video.duration, currentTime: video.currentTime, readyState: video.readyState}));
      records.push({name: "video measurements", status: "measurement", ...playback});
      await captureScreenshot(page, "video-player.png");
      await page.locator("#viewerClose").click();
      assert.equal(await page.locator("#viewerCanvas video").count(), 0);
      await page.locator('[data-filter="all"]').click();
    });
    await check("loading race: toolbar never resurrects previous library", async () => {
      await page.locator("#homeButton").click(); await settle(page);
      let release;
      const gate = new Promise(resolve => {release = resolve;});
      let intercepted;
      const arrived = new Promise(resolve => {intercepted = resolve;});
      const pattern = "**/api/library?*";
      let routeTask, routeError;
      const handler = route => {
        intercepted();
        routeTask = gate.then(() => route.continue()).catch(error => {routeError = error;});
        return routeTask;
      };
      await page.route(pattern, handler);
      try {
        await page.getByRole("button", {name: /打开图集 旅行记/}).click();
        await arrived;
        await visible(page, "#loading");
        await page.locator('[data-filter="image"]').click();
        await page.locator("#searchInput").fill("01");
        await page.locator("#sortSelect").selectOption("newest");
        await page.locator("#listButton").click();
        assert.ok(await page.locator("#content").isHidden());
        assert.ok(await page.locator("#loading").isVisible());
      } finally {release(); await routeTask; await page.unroute(pattern, handler);}
      if (routeError) throw routeError;
      await settle(page);
      assert.equal(await page.locator("#mediaGrid .card-name").first().innerText(), "01-海湾.jpg");
      await page.locator("#searchInput").fill("");
      await page.locator('[data-filter="all"]').click();
      await page.locator("#sortSelect").selectOption("name");
      await page.locator("#gridButton").click();
    });
    await check("partial album stays reachable under image/video filters", async () => {
      const pattern = "**/api/library?*";
      await page.route(pattern, async route => {
        const response = await route.fetch();
        const result = await response.json();
        result.albums = [{name: "统计尚未完成", path: "山间小径", imageCount: 0, videoCount: 0, count: 0, partial: true, cover: null, modified: 0}];
        await route.fulfill({response, json: result});
      });
      await page.locator("#refreshButton").click(); await settle(page);
      for (const type of ["image", "video"]) {
        await page.locator(`[data-filter="${type}"]`).click();
        assert.equal(await page.locator(".album-card").count(), 1);
      }
      await page.unroute(pattern);
      await page.locator('[data-filter="all"]').click();
      await page.locator("#refreshButton").click(); await settle(page);
    });
    await check("empty root and invalid manual path errors", async () => {
      await loadPath(page, empty);
      await visible(page, "#empty");
      assert.match(await page.locator("#emptyTitle").innerText(), /还没有媒体/);
      await page.locator("#pathButton").click();
      await page.locator("#pathInput").fill(path.join(fixture, "does-not-exist"));
      expectedErrorWindow = true;
      await page.locator("#pathSubmit").click();
      await visible(page, "#pathError");
      assert.match(await page.locator("#pathError").innerText(), /找不到/);
      assert.ok(await page.locator("#pathDialog").isVisible());
      expectedErrorWindow = false;
      await page.locator("#pathCancel").click();
      await loadPath(page, library);
    });
    await check("deleted album gives 404 recovery state", async () => {
      const gone = path.join(library, "稍后移走");
      fs.mkdirSync(gone);
      await page.locator("#refreshButton").click(); await settle(page);
      assert.ok(await page.getByRole("button", {name: /打开图集 稍后移走/}).isVisible());
      fs.rmdirSync(gone);
      expectedErrorWindow = true;
      await page.getByRole("button", {name: /打开图集 稍后移走/}).click(); await settle(page);
      await visible(page, "#empty");
      assert.match(await page.locator("#emptyTitle").innerText(), /暂时无法打开/);
      expectedErrorWindow = false;
      await page.locator("#breadcrumbs button").first().click(); await settle(page);
      await visible(page, "#content");
    });
    await check("390x844 mobile layout and viewer without horizontal overflow", async () => {
      await page.setViewportSize({width: 390, height: 844});
      await noOverflow(page);
      await captureScreenshot(page, "mobile-gallery.png", true);
      await page.getByRole("button", {name: "查看图片 01-海边暮色.jpg", exact: true}).click();
      await visible(page, "#viewer");
      await noOverflow(page);
      assert.ok(await page.locator("#viewerClose").isVisible());
      await page.keyboard.press("Escape");
      await hidden(page, "#viewer");
    });
    await check("no JavaScript exceptions or unexpected console errors", async () => {
      assert.deepEqual(pageErrors, []);
      assert.deepEqual(consoleErrors, []);
    });
  } catch (error) {
    if (!records.some(record => record.status === "failed")) records.push({name: "setup or runtime", status: "failed", error: error.stack});
    process.exitCode = 1;
  } finally {
    if (browser) await browser.close();
    if (server && server.exitCode === null) {
      server.kill();
      await new Promise(resolve => {server.once("exit", resolve); setTimeout(resolve, 3000);});
    }
    fs.rmSync(fixture, {recursive: true, force: true});
    const report = {started_utc: started, finished_utc: new Date().toISOString(), node: process.version, platform: process.platform,
      browser_channel: process.env.BROWSER_CHANNEL || (process.platform === "win32" ? "msedge" : "chromium"),
      scope: "headless browser; real local HTTP and artificial demo media; manual path entry; picker not physically operated",
      total_checks: records.filter(r => r.status !== "measurement").length, passed: records.filter(r => r.status === "passed").length,
      failed: records.filter(r => r.status === "failed").length, records, page_errors: pageErrors, unexpected_console_errors: consoleErrors,
      expected_console_errors: expectedConsoleErrors, server_output: serverOutput};
    fs.writeFileSync(path.join(evidence, "browser-" + stamp + ".json"), JSON.stringify(report, null, 2), "utf8");
    fs.writeFileSync(path.join(evidence, "browser-" + stamp + ".log"), records.map(r => `${r.status.toUpperCase()} ${r.name}${r.error ? "\n" + r.error : ""}`).join("\n") + "\n", "utf8");
    console.log(`Evidence saved: docs/test-results/browser-${stamp}.json`);
  }
}

Promise.race([main(), asynchronousFailure]).catch(error => {
  // main normally records controlled failures; this is a last-resort callback failure log.
  fs.writeFileSync(path.join(evidence, "browser-" + stamp + "-async-error.log"), error.stack || String(error), "utf8");
  if (server && server.exitCode === null) server.kill();
  process.exitCode = 1;
});
