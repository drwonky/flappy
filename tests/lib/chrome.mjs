// A small headless-Chrome driver over the DevTools protocol (Node 22's built-in
// WebSocket, nothing to install). Each browser gets a throwaway profile, so
// localStorage starts empty and nothing touches your own Chrome.
import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { GAME } from "./sandbox.mjs";

const CANDIDATES = [process.env.CHROME, "google-chrome", "google-chrome-stable", "chromium", "chromium-browser"].filter(Boolean);
export const chromeBin = CANDIDATES.find(b => {
  try { return spawnSync(b, ["--version"], { stdio: "ignore", timeout: 10000 }).status === 0; } catch { return false; }
}) || null;

export const gameUrl = (search = "") => pathToFileURL(GAME).href + search;
const sleep = ms => new Promise(r => setTimeout(r, ms));

export async function launch() {
  if (!chromeBin) throw new Error("no Chrome found (set CHROME=/path/to/chrome)");
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "flappy-test-"));
  const port = 9300 + Math.floor(Math.random() * 600);
  const proc = spawn(chromeBin, ["--headless=new", "--no-sandbox", "--no-first-run", "--no-default-browser-check", "--hide-scrollbars",
    `--remote-debugging-port=${port}`, `--user-data-dir=${dir}`, "about:blank"], { stdio: "ignore" });
  let version;
  for (let i = 0; i < 100 && !version; i++) {
    try { version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json(); } catch { await sleep(100); }
  }
  if (!version) { proc.kill(); throw new Error("Chrome did not start"); }
  return {
    async page(opts) { return openPage(port, version.webSocketDebuggerUrl, opts); },
    async close() { proc.kill(); await sleep(150); fs.rmSync(dir, { recursive: true, force: true }); },
  };
}

// each page gets a window of its own: a second tab in one window would be a background
// tab, and Chrome stops animating those (so tests running side by side would stall)
async function newWindow(browserWs) {
  const ws = new WebSocket(browserWs);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  const r = await new Promise((res, rej) => {
    ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id === 1) (m.error ? rej(new Error(m.error.message)) : res(m.result)); };
    ws.send(JSON.stringify({ id: 1, method: "Target.createTarget", params: { url: "about:blank", newWindow: true } }));
  });
  ws.close();
  return r.targetId;
}

async function openPage(port, browserWs, { width = 390, height = 844, dpr = 1, mobile = false, preload = null } = {}) {
  const targetId = await newWindow(browserWs);
  const ws = new WebSocket(`ws://127.0.0.1:${port}/devtools/page/${targetId}`);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0;
  const pend = new Map(), errors = [], logs = [];
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); }
    if (m.method === "Runtime.exceptionThrown") errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
    if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error") errors.push("console.error: " + m.params.args.map(a => a.value ?? a.description).join(" "));
    if (m.method === "Log.entryAdded" && m.params.entry.level === "error") logs.push(m.params.entry.text);
  };
  const send = (method, params = {}) => new Promise((res, rej) => {
    const i = ++id;
    pend.set(i, m => (m.error ? rej(new Error(method + ": " + m.error.message)) : res(m.result)));
    ws.send(JSON.stringify({ id: i, method, params }));
  });
  await send("Runtime.enable");
  await send("Page.enable");
  await send("Log.enable");
  await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: dpr, mobile, screenWidth: width, screenHeight: height });   // (the screen is the window, as on a TV in fullscreen)
  if (mobile) await send("Emulation.setTouchEmulationEnabled", { enabled: true });
  if (preload) await send("Page.addScriptToEvaluateOnNewDocument", { source: preload });

  const page = {
    errors, logs, send,
    async goto(url, settle = 1200) {
      const loaded = new Promise(res => { const prev = ws.onmessage; ws.onmessage = e => { prev(e); if (JSON.parse(e.data).method === "Page.loadEventFired") { ws.onmessage = prev; res(); } }; });
      await send("Page.navigate", { url });
      await loaded;
      await page.ev("document.fonts ? document.fonts.ready.then(() => 1) : 1");
      if (settle) await sleep(settle);
    },
    /** evaluate in the page (awaits promises); throws on an exception in the page */
    async ev(expr) {
      const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
      if (r.exceptionDetails) throw new Error("in page: " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
      return r.result.value;
    },
    async screenshot(file) {
      const r = await send("Page.captureScreenshot", { format: "png" });
      fs.mkdirSync(path.dirname(file), { recursive: true });
      fs.writeFileSync(file, Buffer.from(r.data, "base64"));
    },
    async tap(selector) {
      const b = await page.ev(`(() => { const r = document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
      if (mobile) {
        await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [b] });
        await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
      } else {
        for (const type of ["mousePressed", "mouseReleased"]) await send("Input.dispatchMouseEvent", { type, x: b.x, y: b.y, button: "left", clickCount: 1 });
      }
    },
    sleep,
    async close() { try { await send("Page.close"); } catch {} ws.close(); },
  };
  return page;
}
