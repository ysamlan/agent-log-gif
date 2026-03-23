/**
 * Dedicated Web Worker for gifsicle GIF optimization.
 *
 * Runs in a separate execution context from the main pipeline (Apache 2.0)
 * to maintain clear boundary separation — communication is solely via
 * "arms length" CLI arguments / outputs passed via postMessage, analogous 
 * to agent-log-gif's CLI usage of gifsicle via Python's subprocess.run().
 *
 * Message protocol:
 *   In:  {type: "optimize", gif: ArrayBuffer, args: string[]}
 *   Out: {type: "done", gif: ArrayBuffer, inputSize: number, outputSize: number}
 *        {type: "error", message: string}
 *
 * gifsicle by Eddie Kohler, released under the GNU GPL v2.
 * WASM build from gifsicle-bin (https://github.com/ysamlan/gifsicle-bin),
 * approach based on simonw/tools (https://github.com/simonw/tools/tree/main/lib/gifsicle).
 */

let wasmBinaryCache = null;
let scriptLoaded = false;

async function init() {
  if (scriptLoaded) return;

  importScripts("lib/gifsicle/gifsicle.js");

  const resp = await fetch("lib/gifsicle/gifsicle.wasm");
  wasmBinaryCache = await resp.arrayBuffer();

  scriptLoaded = true;
}

async function optimize(gifBuffer, args) {
  await init();

  const mod = await createGifsicle({
    wasmBinary: wasmBinaryCache,
    print: () => {},
    printErr: () => {},
  });

  mod.FS.writeFile("/input.gif", new Uint8Array(gifBuffer));

  const fullArgs = ["gifsicle", ...args, "-o", "/output.gif", "/input.gif"];
  const argv = mod._malloc((fullArgs.length + 1) * 4);
  const ptrs = [];
  for (let i = 0; i < fullArgs.length; i++) {
    const p = mod.stringToNewUTF8(fullArgs[i]);
    ptrs.push(p);
    mod.setValue(argv + i * 4, p, "i32");
  }
  mod.setValue(argv + fullArgs.length * 4, 0, "i32");

  let returnCode;
  try {
    returnCode = mod._run_gifsicle(fullArgs.length, argv);
  } catch (e) {
    returnCode = -1;
  }

  ptrs.forEach((p) => mod._free(p));
  mod._free(argv);

  let outputBytes = null;
  try {
    outputBytes = mod.FS.readFile("/output.gif");
  } catch (e) {
    // output file may not exist if gifsicle failed
  }

  return { outputBytes, returnCode };
}

onmessage = async (e) => {
  const { type, gif, args } = e.data;
  if (type !== "optimize") return;

  try {
    const inputSize = gif.byteLength;
    const { outputBytes } = await optimize(gif, args);

    // Use optimized if smaller, otherwise return original
    let resultBuf;
    let outputSize;
    if (outputBytes && outputBytes.byteLength < inputSize) {
      resultBuf = outputBytes.buffer.slice(
        outputBytes.byteOffset,
        outputBytes.byteOffset + outputBytes.byteLength
      );
      outputSize = outputBytes.byteLength;
    } else {
      resultBuf = gif;
      outputSize = inputSize;
    }

    postMessage(
      { type: "done", gif: resultBuf, inputSize, outputSize },
      [resultBuf]
    );
  } catch (e) {
    postMessage({ type: "error", message: e.message || String(e) });
  }
};
