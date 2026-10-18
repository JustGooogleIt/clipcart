import * as esbuild from "esbuild";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const root = dirname(fileURLToPath(import.meta.url));

await esbuild.build({
  absWorkingDir: root,
  entryPoints: [join(root, "src/checkout.js")],
  outfile: join(root, "checkout.bundle.js"),
  bundle: true,
  format: "iife",
  globalName: "ClipCartCheckout",
  platform: "browser",
  target: ["es2020"],
  sourcemap: true,
  minify: false,
  mainFields: ["browser", "module", "main"],
  conditions: ["browser"],
  define: {
    global: "globalThis",
    "process.env.NODE_DEBUG": "false",
    "process.env.NODE_ENV": '"production"',
  },
  inject: [join(root, "polyfill.js")],
  logLevel: "info",
});

console.log("wrote checkout.bundle.js");
