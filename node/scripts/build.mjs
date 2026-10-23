// Dual ESM/CJS build with nothing but tsc, so the package stays
// dependency-free and a CommonJS Express app can still require it.
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync, rmSync } from "node:fs";

rmSync("dist", { recursive: true, force: true });
for (const config of ["tsconfig.esm.json", "tsconfig.cjs.json"]) {
  execFileSync("npx", ["tsc", "-p", config], { stdio: "inherit" });
}
// The root package is "type": "module", so the CJS output needs its own marker.
mkdirSync("dist/cjs", { recursive: true });
writeFileSync("dist/cjs/package.json", JSON.stringify({ type: "commonjs" }, null, 2) + "\n");
mkdirSync("dist/esm", { recursive: true });
writeFileSync("dist/esm/package.json", JSON.stringify({ type: "module" }, null, 2) + "\n");
console.log("built dist/esm and dist/cjs");
