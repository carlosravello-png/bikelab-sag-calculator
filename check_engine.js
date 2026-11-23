// check_engine.js — runs the calculator's own engine (sag_engine.js, copied verbatim
// from the live page) against golden_vectors.json and against a fresh implementation of
// the documented model on a grid: every model in the database x riders of 50..110 kg.
// Run:  node check_engine.js      (Node.js 18+, no dependencies)
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const E = require("./sag_engine.js");
const gv = JSON.parse(fs.readFileSync(path.join(__dirname, "golden_vectors.json"), "utf8"));

let ok = 0, n = 0;
const check = (c, msg) => { n++; if (c) ok++; console.log(`${c ? "OK  " : "FAIL"} ${msg}`); };

// 1. The verbatim block has not changed since the vectors were generated.
const src = fs.readFileSync(path.join(__dirname, "sag_engine.js"), "utf8");
const block = src.slice(src.indexOf("// ---- BEGIN verbatim ----\n") + 28, src.indexOf("\n// ---- END verbatim ----"));
const sha = crypto.createHash("sha256").update(block, "utf8").digest("hex");
check(sha === gv.engine_sha256, `engine block SHA-256 ${sha.slice(0, 16)}… matches the one recorded with the vectors`);

// 2. Golden vectors.
for (const v of gv.vectors) {
  const r = E.calc(v.input);
  const same = r.psi === v.expected.psi && r.pMin === v.expected.pMin && r.pMax === v.expected.pMax &&
               r.sag === v.expected.sag_pct && r.tokens === v.expected.tokens && r.lr === v.expected.lr;
  check(same, `${v.input.key} ${v.input.mass} kg ${v.input.disc}: ${r.psi} psi, sag ${r.sag}%, LR ${r.lr}`);
}

// 3. Grid: engine vs an independent implementation of the documented model (forks, LR = 1).
const GAM = 1.30, PSI = 6894.76, g = 9.81;
const F = (x, P, d, V, tc, tok, Ff) => {
  const A = Math.PI * (d / 2000) ** 2, V0 = Math.max(V - tok * (tc || 0), (tc || 1)) * 1e-6;
  const xm = Math.min(x / 1000, V0 / A * 0.96), Vx = V0 - A * xm;
  return Vx <= 0 ? 0 : P * PSI * (V0 / Vx) ** GAM * A - Ff;
};
const solve = (W, x, d, V, tc, tok, Ff) => {
  let lo = 20, hi = 500;
  for (let i = 0; i < 200 && hi - lo > 1e-7; i++) { const m = (lo + hi) / 2; F(x, m, d, V, tc, tok, Ff) < W ? lo = m : hi = m; }
  return (lo + hi) / 2;
};
const SF = { XC: [15, 20], Trail: [20, 23], Enduro: [23, 26], DH: [25, 28] };
let worst = 0, cells = 0;
for (const [key, s] of Object.entries(E.C)) {
  if (s[2] !== "fork") continue;
  const [d, V, Ff, tc] = E.F[key];
  for (const disc of Object.keys(SF)) for (let mass = 50; mass <= 110; mass += 5) {
    const stroke = s[4][Math.floor(s[4].length / 2)];
    const r = E.calc({ mass, disc, style: "Neutral", terrain: "mixed", key, stroke, tokens: 0 });
    const sag = (SF[disc][0] + SF[disc][1]) / 2;
    const p = solve(mass * g * 0.40, sag * stroke / 100, d, V, tc, 0, Ff);
    worst = Math.max(worst, Math.abs(r.psi - p)); cells++;
  }
}
check(worst <= 0.06, `grid of ${cells} inputs (102 forks x 4 disciplines x 13 rider masses): max |engine - model| = ${worst.toFixed(3)} psi (engine rounds to 0.1)`);

console.log(`\n${ok}/${n} checks passed`);
process.exit(ok === n ? 0 : 1);
