# -*- coding: utf-8 -*-
"""verify_sag.py — independent verifier of the BikeLab SAG Calculator.

Written from the model as documented in README.md (not translated from the JavaScript):

  Air spring, positive chamber only, polytropic with a single exponent:
      A  = pi * (d/2)^2                           piston area (d in m)
      V0 = max(V - tokens * Vtoken, Vtoken or 1)  chamber volume (cc -> m^3)
      F(x, P) = P * 6894.76 * A * (V0 / (V0 - A*x))^1.30 - Ff     x in m, P in psi, Ff in N
  Load on the spring at the sag point:
      W = m * 9.81 * beta / LR      beta = 0.40 fork, 0.60 shock; LR = 1 for forks
  Target sag (% of stroke): middle of the discipline range, shifted by riding style,
      then clamped to the range +-2 points.
  Pressure P = root of F(sag*stroke, P) = W, bracketed in 20..500 psi (bisection).
  Band shown to the rider: P * (1 +- b), b = 0.15 / 0.10 / 0.07 / 0.05 by segment.

Checks the 13 golden vectors produced by the live engine, plus physical sign guards.
Standard library only.  Run:  python3 verify_sag.py
"""
import json, math, os

GAMMA = 1.30
G = 9.81
PSI_TO_PA = 6894.76
DISC = {  # sag range fork (sf) and shock (ss), % of stroke; progression window pm..px
    "XC": {"sf": (15, 20), "ss": (25, 28), "pm": 1.6, "px": 1.8},
    "Trail": {"sf": (20, 23), "ss": (28, 30), "pm": 1.8, "px": 2.1},
    "Enduro": {"sf": (23, 26), "ss": (30, 33), "pm": 2.0, "px": 2.4},
    "DH": {"sf": (25, 28), "ss": (33, 38), "pm": 2.2, "px": 2.7},
}
STYLE = {"Smooth": 0.92, "Neutral": 1.0, "Aggressive": 1.08}
BAND = {"entry": 0.15, "mid": 0.10, "mid_high": 0.07, "high": 0.05}
DEFAULT_LR = {"XC": 2.2, "Trail": 2.5, "Enduro": 2.7, "DH": 3.0}


def force(x_mm, p_psi, d_mm, v_cc, tc, tok, ff, gamma=GAMMA):
    a = math.pi * (d_mm / 2000.0) ** 2
    v0 = max(v_cc - tok * (tc or 0), (tc or 1)) * 1e-6
    x = min(x_mm / 1000.0, v0 / a * 0.96)
    vx = v0 - a * x
    if vx <= 0:
        return 0.0
    return p_psi * PSI_TO_PA * (v0 / vx) ** gamma * a - ff


def solve_pressure(w, x_mm, d, v, tc, tok, ff):
    lo, hi = 20.0, 500.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if force(x_mm, mid, d, v, tc, tok, ff) < w:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-6:
            break
    return (lo + hi) / 2


def interp(curve, p):
    s = sorted(curve)
    if p <= s[0][0]:
        return s[0][1]
    if p >= s[-1][0]:
        return s[-1][1]
    for (x0, y0), (x1, y1) in zip(s, s[1:]):
        if x0 <= p <= x1:
            return y0 + (p - x0) / (x1 - x0) * (y1 - y0)


def target_sag(disc, kind, style):
    lo, hi = DISC[disc]["sf" if kind == "fork" else "ss"]
    s = (lo + hi) / 2 + (STYLE[style] - 1) * 3
    return min(max(s, lo - 2), hi + 2)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    gv = json.load(open(os.path.join(here, "golden_vectors.json"), encoding="utf-8"))
    tol = gv["tolerance_psi"]
    ok = n = 0

    def check(cond, msg):
        nonlocal ok, n
        n += 1
        ok += bool(cond)
        print(("OK   " if cond else "FAIL ") + msg)

    for v in gv["vectors"]:
        i, m, e = v["input"], v["model"], v["expected"]
        kind = m["type"]
        sag = target_sag(i["disc"], kind, i["style"])
        lr = 1.0
        if kind == "shock":
            lr = interp(m["leverage_curve"], sag) if m["leverage_curve"] else DEFAULT_LR[i["disc"]]
        beta = 0.40 if kind == "fork" else 0.60
        w = i["mass"] * G * beta / lr
        x = sag * i["stroke"] / 100
        p = solve_pressure(w, x, m["piston_d_mm"], m["volume_cc"], m["token_cc"], i["tokens"], m["Ff_N"])
        b = BAND[m["segment"]]
        check(abs(round(sag, 1) - e["sag_pct"]) < 1e-9, f"{i['key']:<22} target sag {sag:.1f}% (engine {e['sag_pct']}%)")
        check(abs(round(lr, 3) - e["lr"]) < 1e-9, f"{i['key']:<22} leverage {lr:.3f} (engine {e['lr']})")
        check(abs(p - e["psi"]) <= tol, f"{i['key']:<22} pressure {p:.2f} psi (engine {e['psi']})")
        check(abs(p * (1 - b) - e["pMin"]) <= 0.15 and abs(p * (1 + b) - e["pMax"]) <= 0.15,
              f"{i['key']:<22} band {p*(1-b):.1f}-{p*(1+b):.1f} psi (engine {e['pMin']}-{e['pMax']})")

    # Sign guards on one fork (Pike-like data from the first vector)
    m = gv["vectors"][0]["model"]
    args = (m["piston_d_mm"], m["volume_cc"], m["token_cc"], 0, m["Ff_N"])
    x = 0.215 * 140
    ps = [solve_pressure(mass * G * 0.40, x, *args) for mass in range(50, 121, 5)]
    check(all(b > a for a, b in zip(ps, ps[1:])), "sign guard: heavier rider -> higher pressure (50..120 kg)")
    p20 = solve_pressure(80 * G * 0.40, 0.20 * 140, *args)
    p25 = solve_pressure(80 * G * 0.40, 0.25 * 140, *args)
    check(p25 < p20, "sign guard: more sag at the same load -> lower pressure")
    check(force(x, 90, *args, gamma=1.30) > force(x, 90, *args, gamma=1.0),
          "sign guard: polytropic (gamma 1.30) spring is stiffer than isothermal (gamma 1.00) at the same sag")

    print(f"\n{ok}/{n} checks passed")
    raise SystemExit(0 if ok == n else 1)


if __name__ == "__main__":
    main()
