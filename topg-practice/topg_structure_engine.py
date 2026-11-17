"""TopG structure engine (scope: structure marking, TJL1/TJL2, CHOCH, Dual CHOCH, ISS).

Rules implemented (from the course PDFs / Lecture 5):
- Bullish structure: 2 consecutive red candles, 2nd BODY closes below 1st candle's low -> the swing HIGH
  is confirmed. The LOW is confirmed when a candle CLOSES above that confirmed high (BOS). Do not look for a
  new 2-candle retracement until the previous confirmed high is broken. Bearish = mirror.
- Levels on a BOS: level 1 = the broken confirmed high/low, level 2 = the confirmed low/high (last support /
  last resistance), level 3 = the running extreme after the break.
- TJL1 = zone at level 1, TJL2 (A+ setup) = zone at level 2. Continuation entries.
- CHOCH: 2 consecutive candles CLOSE beyond last support/resistance, first candle in the new direction's
  colour. Then counter zones: SBR/RBS (level 2), A+ / QML (level 1), DT/DB (level 3).
- Dual CHOCH: after a CHOCH, price closes back beyond level 3 (DT/DB) with 2 candles before the new trend
  has made its own BOS.
- ISS: inside the last impulse (level 2 -> 3), a 5-wave move against the trend forms on the same TF while
  level 2 still holds; waves 3 & 4 become entry zones.
- Zones: wick + 1% of the body of the extreme candle.

Usage: python topg.py SYMBOL [INTERVAL] [PERIOD] [OUT_PNG]
"""
import sys
import json
import numpy as np
import pandas as pd


def load(symbol, interval="1h", period="60d"):
    import yfinance as yf
    d = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=False)
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    d = d[["Open", "High", "Low", "Close"]].dropna()
    d = d[(d["High"] > d["Low"])]  # drop flat placeholder bars
    return d


def zone_high(o, h, l, c):
    body = abs(c - o)
    top = h
    bot = max(o, c) - 0.01 * body
    return (bot, top)


def zone_low(o, h, l, c):
    body = abs(c - o)
    bot = l
    top = min(o, c) + 0.01 * body
    return (bot, top)


class Engine:
    def __init__(self, df):
        self.df = df
        self.O = df["Open"].values
        self.H = df["High"].values
        self.L = df["Low"].values
        self.C = df["Close"].values
        self.t = df.index
        self.events = []

    def zh(self, i):
        return zone_high(self.O[i], self.H[i], self.L[i], self.C[i])

    def zl(self, i):
        return zone_low(self.O[i], self.H[i], self.L[i], self.C[i])

    def red(self, i):
        return self.C[i] < self.O[i]

    def green(self, i):
        return self.C[i] > self.O[i]

    def run(self, seed=30):
        H, L, C = self.H, self.L, self.C
        n = len(C)
        # seed trend from first `seed` bars
        if C[seed] >= C[0]:
            trend = "bull"
            inv_i = int(np.argmin(L[:seed]))
            inv = L[inv_i]
        else:
            trend = "bear"
            inv_i = int(np.argmax(H[:seed]))
            inv = H[inv_i]
        leg_start = seed          # start of current impulse leg (where to search the extreme)
        conf_i = None             # index of confirmed high (bull) / low (bear) waiting to be broken
        lvl1_i = None             # level 1 candle index
        lvl2_i = inv_i            # level 2 candle index (last support/resistance)
        after_choch = None        # dict while in the window after a CHOCH (for dual CHOCH)
        self.state = None

        for i in range(seed + 1, n):
            if trend == "bull":
                # --- CHOCH: 2 consecutive closes below last support, first red
                if C[i] < inv and C[i - 1] < inv and self.red(i - 1):
                    l3_i = leg_start + int(np.argmax(H[leg_start:i + 1]))
                    is_dual = after_choch is not None and after_choch["from"] == "bear"
                    ev = dict(kind="DUAL_CHOCH" if is_dual else "CHOCH", dir="bear", i=i, time=str(self.t[i]),
                              level1=None if lvl1_i is None else dict(i=lvl1_i, zone=self.zh(lvl1_i), name="A+ (QML)"),
                              level2=dict(i=lvl2_i, zone=self.zl(lvl2_i), name="SBR"),
                              level3=dict(i=l3_i, zone=self.zh(l3_i), name="DT"))
                    self.events.append(ev)
                    after_choch = dict(from_="bull", **{"from": "bull"}, i=i)
                    trend = "bear"
                    inv_i, inv = l3_i, H[l3_i]          # last resistance = double top (level 3)
                    lvl2_i, lvl1_i = l3_i, lvl2_i
                    leg_start = i - 1
                    conf_i = None
                    continue
                if conf_i is None:
                    # 2-candle retracement confirms the high
                    if i - 1 >= leg_start and self.red(i - 1) and self.red(i) and C[i] < L[i - 1]:
                        conf_i = leg_start + int(np.argmax(H[leg_start:i + 1]))
                else:
                    if C[i] > H[conf_i]:
                        low_i = conf_i + 1 + int(np.argmin(L[conf_i + 1:i + 1]))
                        lvl1_i, lvl2_i = conf_i, low_i
                        inv_i, inv = low_i, L[low_i]
                        self.events.append(dict(kind="BOS", dir="bull", i=i, time=str(self.t[i]),
                                                level1=dict(i=lvl1_i, zone=self.zh(lvl1_i), name="TJL1"),
                                                level2=dict(i=lvl2_i, zone=self.zl(lvl2_i), name="TJL2 (A+)")))
                        after_choch = None
                        leg_start = low_i
                        conf_i = None
            else:
                if C[i] > inv and C[i - 1] > inv and self.green(i - 1):
                    l3_i = leg_start + int(np.argmin(L[leg_start:i + 1]))
                    is_dual = after_choch is not None and after_choch["from"] == "bull"
                    ev = dict(kind="DUAL_CHOCH" if is_dual else "CHOCH", dir="bull", i=i, time=str(self.t[i]),
                              level1=None if lvl1_i is None else dict(i=lvl1_i, zone=self.zl(lvl1_i), name="A+ (QML)"),
                              level2=dict(i=lvl2_i, zone=self.zh(lvl2_i), name="RBS"),
                              level3=dict(i=l3_i, zone=self.zl(l3_i), name="DB"))
                    self.events.append(ev)
                    after_choch = {"from": "bear", "i": i}
                    trend = "bull"
                    inv_i, inv = l3_i, L[l3_i]
                    lvl2_i, lvl1_i = l3_i, lvl2_i
                    leg_start = i - 1
                    conf_i = None
                    continue
                if conf_i is None:
                    if i - 1 >= leg_start and self.green(i - 1) and self.green(i) and C[i] > H[i - 1]:
                        conf_i = leg_start + int(np.argmin(L[leg_start:i + 1]))
                else:
                    if C[i] < L[conf_i]:
                        high_i = conf_i + 1 + int(np.argmax(H[conf_i + 1:i + 1]))
                        lvl1_i, lvl2_i = conf_i, high_i
                        inv_i, inv = high_i, H[high_i]
                        self.events.append(dict(kind="BOS", dir="bear", i=i, time=str(self.t[i]),
                                                level1=dict(i=lvl1_i, zone=self.zl(lvl1_i), name="TJL1"),
                                                level2=dict(i=lvl2_i, zone=self.zh(lvl2_i), name="TJL2 (A+)")))
                        after_choch = None
                        leg_start = high_i
                        conf_i = None
        self.state = dict(trend=trend, last_invalidation=float(inv), inv_i=int(inv_i), inv_time=str(self.t[inv_i]),
                          pending_confirmed=None if conf_i is None else dict(i=conf_i, time=str(self.t[conf_i]),
                                                                              price=float(H[conf_i] if trend == "bull" else L[conf_i])),
                          leg_start=int(leg_start))
        return self

    # ---------- ISS: 5 counter-trend waves inside the last impulse, same TF ----------
    def pivots(self, a, b, k=2):
        H, L = self.H, self.L
        piv = []
        for j in range(max(a, k), min(b, len(H) - k)):
            if H[j] == max(H[j - k:j + k + 1]):
                piv.append(("H", j, H[j]))
            if L[j] == min(L[j - k:j + k + 1]):
                piv.append(("L", j, L[j]))
        # alternate, keep extremes
        out = []
        for p in sorted(piv, key=lambda x: x[1]):
            if out and out[-1][0] == p[0]:
                if (p[0] == "H" and p[2] > out[-1][2]) or (p[0] == "L" and p[2] < out[-1][2]):
                    out[-1] = p
            else:
                out.append(p)
        return out

    def find_iss(self):
        """Scan every BOS leg: from level 3 (extreme of the impulse) look for 5 counter waves before a CHOCH."""
        res = []
        evs = self.events
        for k, ev in enumerate(evs):
            if ev["kind"] != "BOS":
                continue
            end = evs[k + 1]["i"] if k + 1 < len(evs) else len(self.C)
            start = ev["level2"]["i"]
            piv = self.pivots(start, end)
            if ev["dir"] == "bull":
                # level 3 = highest pivot high; waves after it: L1 H2 L3 H4 L5 with lower lows / lower highs
                highs = [p for p in piv if p[0] == "H"]
                if not highs:
                    continue
                top = max(highs, key=lambda p: p[2])
                seq = [p for p in piv if p[1] > top[1]]
                lvl2 = self.L[ev["level2"]["i"]]
                for s in range(0, max(0, len(seq) - 4)):
                    w = seq[s:s + 5]
                    if [p[0] for p in w] != ["L", "H", "L", "H", "L"]:
                        continue
                    w1, w2, w3, w4, w5 = w
                    if w2[2] < top[2] and w3[2] < w1[2] and w4[2] < w2[2] and w4[2] > w3[2] and w5[2] < w3[2] and w5[2] > lvl2:
                        # wave 5 low confirmed by a 2 green candle retracement (2nd closes above 1st's high)
                        conf = next((j for j in range(w5[1] + 1, min(w5[1] + 12, len(self.C)))
                                     if self.green(j - 1) and self.green(j) and self.C[j] > self.H[j - 1]), None)
                        if conf is None:
                            continue
                        res.append(dict(kind="ISS", dir="bear", bos_i=ev["i"], level3=dict(i=top[1], price=float(top[2])),
                                        waves=[dict(n=n + 1, i=p[1], time=str(self.t[p[1]]), price=float(p[2])) for n, p in enumerate(w)],
                                        confirm_i=conf, confirm_time=str(self.t[conf]),
                                        sell_zones=dict(w3=zone_low(self.O[w3[1]], self.H[w3[1]], self.L[w3[1]], self.C[w3[1]]),
                                                        w4=self.zh(w4[1]))))
                        break
            else:
                lows = [p for p in piv if p[0] == "L"]
                if not lows:
                    continue
                bot = min(lows, key=lambda p: p[2])
                seq = [p for p in piv if p[1] > bot[1]]
                lvl2 = self.H[ev["level2"]["i"]]
                for s in range(0, max(0, len(seq) - 4)):
                    w = seq[s:s + 5]
                    if [p[0] for p in w] != ["H", "L", "H", "L", "H"]:
                        continue
                    w1, w2, w3, w4, w5 = w
                    if w2[2] > bot[2] and w3[2] > w1[2] and w4[2] > w2[2] and w4[2] < w3[2] and w5[2] > w3[2] and w5[2] < lvl2:
                        # wave 5 high confirmed by a 2 red candle retracement (2nd closes below 1st's low)
                        conf = next((j for j in range(w5[1] + 1, min(w5[1] + 12, len(self.C)))
                                     if self.red(j - 1) and self.red(j) and self.C[j] < self.L[j - 1]), None)
                        if conf is None:
                            continue
                        res.append(dict(kind="ISS", dir="bull", bos_i=ev["i"], level3=dict(i=bot[1], price=float(bot[2])),
                                        waves=[dict(n=n + 1, i=p[1], time=str(self.t[p[1]]), price=float(p[2])) for n, p in enumerate(w)],
                                        confirm_i=conf, confirm_time=str(self.t[conf]),
                                        buy_zones=dict(w3=self.zh(w3[1]), w4=self.zl(w4[1]))))
                        break
        self.iss = res
        return res

    # ---------- practice evaluation of TJL entries ----------
    def eval_tjl(self, rr=2.0):
        """For each BOS: first touch of TJL1 then TJL2 zone before CHOCH. Entry at zone edge, SL beyond level 2
        zone (wick) with a small buffer, TP at rr*risk. Outcome by bar walk (SL first if both in one bar)."""
        H, L = self.H, self.L
        atr = pd.Series(H - L).rolling(14).mean().bfill().values
        out = []
        evs = self.events
        for k, ev in enumerate(evs):
            if ev["kind"] != "BOS":
                continue
            stop_scan = evs[k + 1]["i"] if k + 1 < len(evs) else len(H)
            for key in ("level1", "level2"):
                zb, zt = ev[key]["zone"]
                lv2b, lv2t = ev["level2"]["zone"]
                buf = 0.1 * atr[ev["i"]]
                if ev["dir"] == "bull":
                    entry = zt
                    sl = lv2b - buf
                else:
                    entry = zb
                    sl = lv2t + buf
                risk = abs(entry - sl)
                if risk <= 0:
                    continue
                tp = entry + rr * risk if ev["dir"] == "bull" else entry - rr * risk
                filled = None
                for j in range(ev["i"] + 1, len(H)):
                    if j >= stop_scan and filled is None:
                        break
                    if filled is None:
                        if (ev["dir"] == "bull" and L[j] <= entry) or (ev["dir"] == "bear" and H[j] >= entry):
                            filled = j
                            # same-bar stop?
                            if (ev["dir"] == "bull" and L[j] <= sl) or (ev["dir"] == "bear" and H[j] >= sl):
                                out.append(dict(bos=ev["time"], dir=ev["dir"], zone=ev[key]["name"], entry=entry, sl=sl, tp=tp,
                                                fill=str(self.t[j]), result="loss", exit=str(self.t[j])))
                                break
                        continue
                    hit_sl = (L[j] <= sl) if ev["dir"] == "bull" else (H[j] >= sl)
                    hit_tp = (H[j] >= tp) if ev["dir"] == "bull" else (L[j] <= tp)
                    if hit_sl or hit_tp:
                        out.append(dict(bos=ev["time"], dir=ev["dir"], zone=ev[key]["name"], entry=entry, sl=sl, tp=tp,
                                        fill=str(self.t[filled]), result="loss" if hit_sl else "win", exit=str(self.t[j])))
                        break
                else:
                    if filled is not None:
                        out.append(dict(bos=ev["time"], dir=ev["dir"], zone=ev[key]["name"], entry=entry, sl=sl, tp=tp,
                                        fill=str(self.t[filled]), result="open", exit=None))
        self.tjl_trades = out
        return out


def plot(eng, path, last=260, title=""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    df = eng.df
    n = len(df)
    a = max(0, n - last)
    fig, ax = plt.subplots(figsize=(18, 8), dpi=90)
    for j in range(a, n):
        o, h, l, c = eng.O[j], eng.H[j], eng.L[j], eng.C[j]
        col = "#26a69a" if c >= o else "#ef5350"
        ax.plot([j, j], [l, h], color=col, lw=0.8)
        ax.add_patch(Rectangle((j - 0.35, min(o, c)), 0.7, max(abs(c - o), 1e-9), color=col))
    for ev in eng.events:
        if ev["i"] < a:
            continue
        col = {"BOS": "#1565c0", "CHOCH": "#e65100", "DUAL_CHOCH": "#6a1b9a"}[ev["kind"]]
        y = eng.C[ev["i"]]
        ax.annotate(f"{ev['kind']} {ev['dir']}", (ev["i"], y), fontsize=8, color=col,
                    xytext=(0, 18 if ev["dir"] == "bull" else -22), textcoords="offset points", ha="center",
                    arrowprops=dict(arrowstyle="-", color=col, lw=0.6))
        for key in ("level1", "level2", "level3"):
            lv = ev.get(key)
            if not lv or lv["i"] < a:
                continue
            zb, zt = lv["zone"]
            ax.add_patch(Rectangle((lv["i"], zb), ev["i"] + 40 - lv["i"], max(zt - zb, 1e-9), alpha=0.25,
                                   color="#2e7d32" if ev["dir"] == "bull" else "#c62828"))
            ax.text(ev["i"] + 40, (zb + zt) / 2, lv["name"], fontsize=7, va="center")
    for iss in getattr(eng, "iss", []):
        if iss["waves"][0]["i"] < a:
            continue
        xs = [iss["level3"]["i"]] + [w["i"] for w in iss["waves"]]
        ys = [iss["level3"]["price"]] + [w["price"] for w in iss["waves"]]
        ax.plot(xs, ys, color="#000", lw=1, ls="--")
        for w in iss["waves"]:
            ax.text(w["i"], w["price"], str(w["n"]), fontsize=9, fontweight="bold")
        ax.text(iss["confirm_i"], ys[-1], f"ISS {iss['dir']}", fontsize=9, color="#000")
    ax.set_xlim(a - 2, n + 45)
    ticks = list(range(a, n, max(1, (n - a) // 12)))
    ax.set_xticks(ticks)
    ax.set_xticklabels([df.index[j].strftime("%m-%d %H:%M") for j in ticks], rotation=30, fontsize=8)
    ax.set_title(title)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(path)


def main():
    sym = sys.argv[1]
    interval = sys.argv[2] if len(sys.argv) > 2 else "1h"
    period = sys.argv[3] if len(sys.argv) > 3 else "60d"
    out_png = sys.argv[4] if len(sys.argv) > 4 else None
    df = load(sym, interval, period)
    eng = Engine(df).run()
    eng.find_iss()
    trades = eng.eval_tjl()
    fmt = lambda x: round(float(x), 5)
    print(f"=== {sym} {interval} bars={len(df)} {df.index[0]} -> {df.index[-1]}  last close={fmt(df['Close'].iloc[-1])}")
    for ev in eng.events[-12:]:
        parts = [f"{ev['time'][:16]} {ev['kind']:<10} {ev['dir']}"]
        for key in ("level1", "level2", "level3"):
            lv = ev.get(key)
            if lv:
                parts.append(f"{lv['name']}=[{fmt(lv['zone'][0])},{fmt(lv['zone'][1])}]@{str(df.index[lv['i']])[:16]}")
        print("  " + " | ".join(parts))
    print("  STATE:", json.dumps(eng.state))
    for iss in eng.iss[-4:]:
        z = iss.get("sell_zones") or iss.get("buy_zones")
        print(f"  ISS {iss['dir']} confirmed {iss['confirm_time'][:16]} lvl3={fmt(iss['level3']['price'])} waves=" +
              ",".join(f"{w['n']}:{fmt(w['price'])}" for w in iss["waves"]) +
              f" zones w3=[{fmt(z['w3'][0])},{fmt(z['w3'][1])}] w4=[{fmt(z['w4'][0])},{fmt(z['w4'][1])}]")
    wins = sum(t["result"] == "win" for t in trades)
    losses = sum(t["result"] == "loss" for t in trades)
    by = {}
    for t in trades:
        b = by.setdefault(t["zone"], [0, 0])
        if t["result"] == "win":
            b[0] += 1
        elif t["result"] == "loss":
            b[1] += 1
    print(f"  TJL practice (2R): {wins}W/{losses}L  by zone: {by}  open={sum(t['result']=='open' for t in trades)}")
    if out_png:
        plot(eng, out_png, title=f"{sym} {interval} â€” TopG structure (BOS/TJL, CHOCH, Dual CHOCH, ISS)")
        print("  chart:", out_png)


if __name__ == "__main__":
    main()
