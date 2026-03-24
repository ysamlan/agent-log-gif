/**
 * Web Worker for agent-log-gif rendering pipeline (Apache 2.0).
 *
 * Loads Pyodide + Pillow, unpacks the agent_log_gif source bundle,
 * runs the Python rendering pipeline, then delegates GIF optimization
 * to a separate gifsicle worker (GPL v2) via postMessage for clean
 * license boundary separation.
 *
 * Message protocol:
 *   Main -> Worker: {type: "render", jsonl: string, options: {...}}
 *   Worker -> Main: {type: "status", message: string}
 *                   {type: "progress", current: number, total: number}
 *                   {type: "done", gif: ArrayBuffer, frames: number, rawSize: number, optimizedSize: number}
 *                   {type: "error", message: string}
 */

// Pyodide CDN
const PYODIDE_CDN = "https://cdn.jsdelivr.net/pyodide/v0.27.5/full/";

let pyodide = null;
let gifsicleWorker = null;

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------
function status(message) {
  postMessage({ type: "status", message });
}

function progress(current, total) {
  postMessage({ type: "progress", current, total });
}

// ---------------------------------------------------------------------------
// Pyodide initialization
// ---------------------------------------------------------------------------
async function initPyodide() {
  status("Loading Python runtime...");
  importScripts(PYODIDE_CDN + "pyodide.js");
  pyodide = await loadPyodide({ indexURL: PYODIDE_CDN });

  status("Loading Pillow...");
  await pyodide.loadPackage("Pillow");

  status("Loading rendering pipeline...");
  // Fetch and unpack the agent_log_gif source bundle
  const resp = await fetch("agent_log_gif.zip");
  const buf = await resp.arrayBuffer();
  pyodide.unpackArchive(buf, "zip", { extractDir: "/home/pyodide" });

  // Fetch and register the pipeline script
  const pipelineResp = await fetch("pipeline.py");
  const pipelineCode = await pipelineResp.text();

  // Register JS callbacks that Python can call
  globalThis.js_report_status = (msg) => status(msg);
  globalThis.js_report_progress = (current, total) => progress(current, total);

  // Run the pipeline module to define render_gif()
  await pyodide.runPythonAsync(pipelineCode);
}

// ---------------------------------------------------------------------------
// gifsicle optimization via dedicated sub-worker (GPL boundary)
// ---------------------------------------------------------------------------
function initGifsicleWorker() {
  if (gifsicleWorker) return;
  gifsicleWorker = new Worker("gifsicle-worker.js");
}

function optimizeWithGifsicle(gifBuffer, args) {
  return new Promise((resolve, reject) => {
    gifsicleWorker.onmessage = (e) => {
      if (e.data.type === "done") {
        resolve(e.data);
      } else if (e.data.type === "error") {
        reject(new Error(e.data.message));
      }
    };
    gifsicleWorker.onerror = (e) => reject(new Error(e.message));
    gifsicleWorker.postMessage(
      { type: "optimize", gif: gifBuffer, args },
      [gifBuffer]
    );
  });
}

function gifsicleArgs(rawSizeBytes) {
  // Benchmark results (native, extrapolated to wasm ~3x):
  //   O1 saves ~37%, O2 saves ~40% (3pp more), O2 is ~1.6x slower
  //   At 10 MB raw: O2 wasm ~10s, O1 wasm ~7s
  //   At 35 MB raw: O2 wasm ~48s, O1 wasm ~36s
  // Use O2 up to 10 MB (keeps gifsicle under ~10s wasm), O1 above.
  const sizeMB = rawSizeBytes / (1024 * 1024);
  const level = sizeMB > 10 ? "-O1" : "-O2";
  return [level, "--lossy=80"];
}

// ---------------------------------------------------------------------------
// Shared: optimize raw GIF and post result
// ---------------------------------------------------------------------------
async function optimizeAndPost(rawGif, frameCount, minimalEvents) {
  const rawSize = rawGif.byteLength;

  status("Optimizing with gifsicle...");
  const args = gifsicleArgs(rawSize);
  const rawBuf = rawGif.buffer.slice(
    rawGif.byteOffset,
    rawGif.byteOffset + rawGif.byteLength
  );
  const optimized = await optimizeWithGifsicle(rawBuf, args);

  postMessage(
    {
      type: "done",
      gif: optimized.gif,
      rawSize,
      optimizedSize: optimized.outputSize,
      frames: frameCount,
      minimalEvents: minimalEvents || null,
    },
    [optimized.gif]
  );
}

// ---------------------------------------------------------------------------
// Ensure Pyodide + gifsicle are initialized
// ---------------------------------------------------------------------------
async function ensureInit() {
  if (!pyodide) {
    initGifsicleWorker();
    await initPyodide();
  }
}

// ---------------------------------------------------------------------------
// Main render handler
// ---------------------------------------------------------------------------
async function handleRender(jsonl, options) {
  try {
    await ensureInit();

    pyodide.globals.set("jsonl_content", jsonl);
    pyodide.globals.set("render_options", pyodide.toPy(options));

    const result = await pyodide.runPythonAsync(
      "render_gif(jsonl_content, dict(render_options))"
    );

    const rawGif = result.gif instanceof Uint8Array ? result.gif : result.gif.toJs();
    // minimal_events is already a native JS array (to_js called in Python)
    const minimalEvents = result.minimal_events || null;
    await optimizeAndPost(rawGif, result.frames, minimalEvents);
  } catch (e) {
    postMessage({ type: "error", message: e.message || String(e) });
  }
}

// ---------------------------------------------------------------------------
// Share render handler — renders from pre-extracted events
// ---------------------------------------------------------------------------
async function handleRenderShare(events, options) {
  try {
    await ensureInit();

    pyodide.globals.set("share_events", pyodide.toPy(events));
    pyodide.globals.set("render_options", pyodide.toPy(options));

    const result = await pyodide.runPythonAsync(
      "render_gif_from_share(list(share_events), dict(render_options))"
    );

    const rawGif = result.gif instanceof Uint8Array ? result.gif : result.gif.toJs();
    // minimal_events is already a native JS array (to_js called in Python)
    const minimalEvents = result.minimal_events || null;
    await optimizeAndPost(rawGif, result.frames, minimalEvents);
  } catch (e) {
    postMessage({ type: "error", message: e.message || String(e) });
  }
}

// ---------------------------------------------------------------------------
// Message handler
// ---------------------------------------------------------------------------
onmessage = async (e) => {
  const { type, jsonl, events, options } = e.data;
  if (type === "render") {
    await handleRender(jsonl, options || {});
  } else if (type === "render_share") {
    await handleRenderShare(events, options || {});
  }
};
