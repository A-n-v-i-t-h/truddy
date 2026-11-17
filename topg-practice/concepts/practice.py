"""TopG concept-by-concept practice across timeframes.

Concepts (scope stops at Dual CHOCH):
  01 Structure marking   02 TJL1/TJL2   03 CHOCH   04 Dual CHOCH   05 ISS (5-wave CHOCH)

Data: Dukascopy bid candles (UTC), shown in IST. Pairs are ones not on the user's watchlist.
Every rule below is taken from the course PDFs / lecture transcripts (see ../TopG_strategy_notes.md).

Usage: python practice.py DATA_DIR OUT_DIR
"""
import os
import sys
import glob
import math
import json
import numpy as np
import pandas as pd

PAIRS = ["audusd", "usdcad", "nzdusd", "eurjpy", "usdchf", "gbpjpy"]
TFS = ["m15", "h1", "h4", "d1"]
LTF = {"d1": "h1", "h4": "m15", "h1": "m5", "m15": "m1"}      # confirmation timeframe
HTF = {"m15": "h1", "h1": "h4", "h4": "d1", "d1": None}       # trend-context timeframe
TF_NAME = {"m1": "M1", "m5": "M5", "m15": "M15", "h1": "H1", "h4": "H4", "d1": "D1"}
RR = 3.0           # course examples target ~1:3
WINDOW = 150       # bars a setup stays valid
CONFIRM_BARS = 6   # base bars allowed to find a confirmation after the first touch
IST = "Asia/Kolkata"


# ----------------------------------------------------------------------------- data
def load(data_dir, pair, tf):
    f = sorted(glob.glob(os.path.join(data_dir, f"{pair}-{tf}-bid-*.csv")))
    if not f:
        return None
    d = pd.read_csv(f[-1])
    d.index = pd.to_datetime(d["timestamp"], unit="ms", utc=True)
    d = d[["open", "high", "low", "close"]].astype(float)
    d = d[d["high"] > d["low"]]
    return d


def atr(df, n=14):
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    return pd.Series(tr).rolling(n, min_periods=1).mean().values


def pip(pair):
    return 0.01 if pair.endswith("jpy") else 0.0001


# ----------------------------------------------------------------------------- zones
def zone_high(o, h, l, c):           # mark top wick + 1% of the body
    return (max(o, c) - 0.01 * abs(c - o), h)


def zone_low(o, h, l, c):            # mark bottom wick + 1% of the body
    return (l, min(o, c) + 0.01 * abs(c - o))


# ----------------------------------------------------------------------------- structure engine
class Structure:
    """Course rules:
    bullish: 2 consecutive red candles, 2nd closes below 1st's low -> HIGH confirmed (top of the move).
             a candle CLOSES above that high -> LOW confirmed (lowest point after the high) = BOS.
             no new 2-candle retracement is looked for until the confirmed high is broken.
    bearish: mirror.
    CHOCH:   2 consecutive closes beyond last support/resistance, first candle in the new colour.
    Dual:    a CHOCH right after a CHOCH (before the new trend made its own BOS)."""

    def __init__(self, df):
        self.df = df
        self.O, self.H, self.L, self.C = (df[k].values for k in ("open", "high", "low", "close"))
        self.n = len(df)

    def zh(self, i):
        return zone_high(self.O[i], self.H[i], self.L[i], self.C[i])

    def zl(self, i):
        return zone_low(self.O[i], self.H[i], self.L[i], self.C[i])

    def red(self, i):
        return self.C[i] < self.O[i]

    def green(self, i):
        return self.C[i] > self.O[i]

    def run(self, seed=20):
        O, H, L, C, n = self.O, self.H, self.L, self.C, self.n
        self.events, self.swings = [], []
        self.trend = np.zeros(n, dtype=int)
        seed = min(seed, n - 2)
        if C[seed] >= C[0]:
            trend, inv_i = 1, int(np.argmin(L[:seed + 1]))
        else:
            trend, inv_i = -1, int(np.argmax(H[:seed + 1]))
        leg_start, conf_i, lvl1_i, lvl2_i, after = seed, None, None, inv_i, None
        self.trend[:seed + 1] = trend
        for i in range(seed + 1, n):
            if trend == 1:
                inv = L[inv_i]
                if C[i] < inv and C[i - 1] < inv and self.red(i - 1):
                    l3 = leg_start + int(np.argmax(H[leg_start:i + 1]))
                    kind = "DUAL_CHOCH" if after == -1 else "CHOCH"
                    self.events.append(dict(kind=kind, dir=-1, i=i, lvl1=lvl1_i, lvl2=lvl2_i, lvl3=l3))
                    after, trend = 1, -1
                    lvl1_i, lvl2_i, inv_i = lvl2_i, l3, l3
                    leg_start, conf_i = i - 1, None
                elif conf_i is None:
                    if i - 1 >= leg_start and self.red(i - 1) and self.red(i) and C[i] < L[i - 1]:
                        conf_i = leg_start + int(np.argmax(H[leg_start:i + 1]))
                        self.swings.append(dict(t="H", i=conf_i, at=i))
                elif C[i] > H[conf_i]:
                    lo = conf_i + 1 + int(np.argmin(L[conf_i + 1:i + 1])) if i > conf_i + 1 else conf_i
                    self.swings.append(dict(t="L", i=lo, at=i))
                    self.events.append(dict(kind="BOS", dir=1, i=i, lvl1=conf_i, lvl2=lo))
                    lvl1_i, lvl2_i, inv_i = conf_i, lo, lo
                    after, leg_start, conf_i = None, lo, None
            else:
                inv = H[inv_i]
                if C[i] > inv and C[i - 1] > inv and self.green(i - 1):
                    l3 = leg_start + int(np.argmin(L[leg_start:i + 1]))
                    kind = "DUAL_CHOCH" if after == 1 else "CHOCH"
                    self.events.append(dict(kind=kind, dir=1, i=i, lvl1=lvl1_i, lvl2=lvl2_i, lvl3=l3))
                    after, trend = -1, 1
                    lvl1_i, lvl2_i, inv_i = lvl2_i, l3, l3
                    leg_start, conf_i = i - 1, None
                elif conf_i is None:
                    if i - 1 >= leg_start and self.green(i - 1) and self.green(i) and C[i] > H[i - 1]:
                        conf_i = leg_start + int(np.argmin(L[leg_start:i + 1]))
                        self.swings.append(dict(t="L", i=conf_i, at=i))
                elif C[i] < L[conf_i]:
                    hi = conf_i + 1 + int(np.argmax(H[conf_i + 1:i + 1])) if i > conf_i + 1 else conf_i
                    self.swings.append(dict(t="H", i=hi, at=i))
                    self.events.append(dict(kind="BOS", dir=-1, i=i, lvl1=conf_i, lvl2=hi))
                    lvl1_i, lvl2_i, inv_i = conf_i, hi, hi
                    after, leg_start, conf_i = None, hi, None
            self.trend[i] = trend
        self.last = dict(trend=trend, inv_i=inv_i, conf_i=conf_i, leg_start=leg_start)
        return self

    def trend_at(self, ts):
        k = self.df.index.searchsorted(ts, side="right") - 1
        return int(self.trend[k]) if k >= 0 else 0

    # internal waves with the same 2-candle rule (used by ISS)
    def waves(self, a, b, first):
        """Alternating confirmed swings from bar a (an extreme) to b. first='L' means the first swing to
        confirm is a low (we are moving down from a high). Each swing is confirmed by a 2-candle
        retracement in the opposite colour with the 2nd candle closing beyond the 1st's extreme."""
        H, L, C = self.H, self.L, self.C
        out, look, last = [], first, a
        ext_i = None
        for i in range(a + 1, min(b, self.n)):
            if look == "L":
                if ext_i is None or L[i] < L[ext_i]:
                    ext_i = i
                if i - 1 > last and ext_i < i - 1 and self.green(i - 1) and self.green(i) and C[i] > H[i - 1]:
                    out.append(("L", ext_i, i))
                    look = "H"
                    ext_i = ext_i + 1 + int(np.argmax(H[ext_i + 1:i + 1]))
                    last = i
            else:
                if ext_i is None or H[i] > H[ext_i]:
                    ext_i = i
                if i - 1 > last and ext_i < i - 1 and self.red(i - 1) and self.red(i) and C[i] < L[i - 1]:
                    out.append(("H", ext_i, i))
                    look = "L"
                    ext_i = ext_i + 1 + int(np.argmin(L[ext_i + 1:i + 1]))
                    last = i
        return out


# ----------------------------------------------------------------------------- trade simulation
def simulate(H, L, start, direction, entry, sl, tp, end):
    """Bars from `start` (the bar after entry). Stop first if both hit in one bar. Returns result, exit idx, MFE in R."""
    risk = abs(entry - sl)
    mfe = 0.0
    for j in range(start, min(end, len(H))):
        if direction == 1:
            if L[j] <= sl:
                return "loss", j, mfe
            mfe = max(mfe, (H[j] - entry) / risk)
            if H[j] >= tp:
                return "win", j, mfe
        else:
            if H[j] >= sl:
                return "loss", j, mfe
            mfe = max(mfe, (entry - L[j]) / risk)
            if L[j] <= tp:
                return "win", j, mfe
    return "open", None, mfe


def engulf(ltf, k, direction):
    o, c = ltf["open"].values, ltf["close"].values
    if k < 1:
        return False
    if direction == 1:
        return c[k - 1] < o[k - 1] and c[k] > o[k] and c[k] >= o[k - 1] and o[k] <= c[k - 1]
    return c[k - 1] > o[k - 1] and c[k] < o[k] and c[k] <= o[k - 1] and o[k] >= c[k - 1]


def trade_zone(st, ltf, a, direction, zone, inval_price, start_i, end_i, buf, rr=RR, raw_sl=None):
    """Two entry methods on one zone.
    raw: limit at the zone's near edge, SL beyond the far edge (or raw_sl) +/- buffer.
    confirmed: after price touches the zone, first engulfing candle on the lower TF (within CONFIRM_BARS base
               bars, low/high still at the zone), market entry at its close, SL beyond the swing made during
               the touch +/- buffer.
    Setup is cancelled once a base candle CLOSES beyond inval_price before entry."""
    H, L, C, idx = st.H, st.L, st.C, st.df.index
    zb, zt = zone
    near = zt if direction == 1 else zb
    far = zb if direction == 1 else zt
    out = {}
    # first touch
    touch = None
    for j in range(start_i, min(end_i, st.n)):
        if (direction == 1 and C[j] < inval_price) or (direction == -1 and C[j] > inval_price):
            break
        if (direction == 1 and L[j] <= near) or (direction == -1 and H[j] >= near):
            touch = j
            break
    if touch is None:
        return None
    # raw
    sl = (raw_sl if raw_sl is not None else far) - direction * buf
    risk = abs(near - sl)
    if risk > 0:
        tp = near + direction * rr * risk
        same_bar_stop = (direction == 1 and L[touch] <= sl) or (direction == -1 and H[touch] >= sl)
        if same_bar_stop:
            res, ex, mfe = "loss", touch, 0.0
        else:
            res, ex, mfe = simulate(H, L, touch + 1, direction, near, sl, tp, touch + WINDOW)
        out["raw"] = dict(entry=near, sl=sl, tp=tp, fill_i=touch, exit_i=ex, result=res, mfe=round(mfe, 2),
                          risk_pips=None)
    # confirmed
    if ltf is not None and len(ltf):
        base_atr = buf * 10                      # buf is 0.1 ATR
        t0 = idx[touch]
        t_end = idx[min(touch + CONFIRM_BARS, st.n - 1)]
        if t0 >= ltf.index[0]:
            k0 = max(1, ltf.index.searchsorted(t0))
            k1 = ltf.index.searchsorted(t_end, side="right")
            lo, hi = ltf["low"].values, ltf["high"].values
            lc = ltf["close"].values
            ext = None                           # swing made while price is at the zone
            for k in range(k0, min(k1, len(ltf))):
                if direction == 1:
                    ext = lo[k] if ext is None else min(ext, lo[k])
                else:
                    ext = hi[k] if ext is None else max(ext, hi[k])
                if (direction == 1 and lc[k] < inval_price) or (direction == -1 and lc[k] > inval_price):
                    break
                at_zone = (direction == 1 and min(lo[k], lo[k - 1]) <= zt + buf) or \
                          (direction == -1 and max(hi[k], hi[k - 1]) >= zb - buf)
                if at_zone and engulf(ltf, k, direction):
                    entry = lc[k]
                    # SL beyond the zone itself (course: "SL on this zone") or the touch swing, whichever is further
                    far_pt = min(ext, far) if direction == 1 else max(ext, far)
                    sl = far_pt - direction * buf
                    if abs(entry - sl) < 0.3 * base_atr:    # floor: no stops tighter than 0.3 base ATR
                        sl = entry - direction * 0.3 * base_atr
                    risk = abs(entry - sl)
                    tp = entry + direction * rr * risk
                    t_cap = idx[min(touch + WINDOW, st.n - 1)]
                    k_end = ltf.index.searchsorted(t_cap, side="right")
                    res, ex_k, mfe = simulate(hi, lo, k + 1, direction, entry, sl, tp, k_end)
                    ex_i = None if ex_k is None else min(st.n - 1, idx.searchsorted(ltf.index[ex_k], side="right") - 1)
                    fill_i = min(st.n - 1, idx.searchsorted(ltf.index[k], side="right") - 1)
                    out["confirmed"] = dict(entry=entry, sl=sl, tp=tp, fill_i=fill_i, exit_i=ex_i, result=res,
                                            mfe=round(mfe, 2), ltf_time=str(ltf.index[k].tz_convert(IST)))
                    break
    return out


# ----------------------------------------------------------------------------- plotting
def plot_setup(st, path, title, a, b, zones=(), lines=(), labels=(), trades=(), note=""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    a, b = max(0, a), min(st.n, b)
    fig, ax = plt.subplots(figsize=(13, 6.2), dpi=85)
    width = 0.7
    for j in range(a, b):
        o, h, l, c = st.O[j], st.H[j], st.L[j], st.C[j]
        col = "#26a69a" if c >= o else "#ef5350"
        ax.plot([j, j], [l, h], color=col, lw=0.8, zorder=2)
        ax.add_patch(Rectangle((j - width / 2, min(o, c)), width, max(abs(c - o), 1e-12), color=col, zorder=3))
    for (i0, (zb, zt), name, col) in zones:
        x0 = max(i0, a)
        ax.add_patch(Rectangle((x0, zb), b - x0 + 3, max(zt - zb, 1e-12), alpha=0.22, color=col, zorder=1))
        ax.text(b + 3, (zb + zt) / 2, name, fontsize=8, va="center", color=col)
    for (i0, y, name, col, ls) in lines:
        ax.hlines(y, max(i0, a), b + 2, colors=col, linestyles=ls, lw=1)
        ax.text(b + 3, y, name, fontsize=7, va="center", color=col)
    for (i, y, txt, col, dy) in labels:
        if a <= i < b:
            ax.annotate(txt, (i, y), xytext=(0, dy), textcoords="offset points", ha="center", fontsize=8,
                        color=col, fontweight="bold")
    for t in trades:
        if t.get("fill_i") is not None and a <= t["fill_i"] < b:
            ax.plot(t["fill_i"], t["entry"], marker="o", color="#000", ms=5, zorder=5)
        if t.get("exit_i") is not None and a <= t["exit_i"] < b:
            ax.plot(t["exit_i"], t["tp"] if t["result"] == "win" else t["sl"], marker="x",
                    color="#1b5e20" if t["result"] == "win" else "#b71c1c", ms=8, mew=2, zorder=5)
    idx = st.df.index.tz_convert(IST)
    step = max(1, (b - a) // 10)
    ticks = list(range(a, b, step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([idx[j].strftime("%d %b %H:%M") for j in ticks], rotation=25, fontsize=7)
    ax.set_xlim(a - 1, b + 22)
    ax.set_title(title, fontsize=10)
    if note:
        ax.text(0.01, 0.01, note, transform=ax.transAxes, fontsize=8, va="bottom",
                bbox=dict(facecolor="white", alpha=0.85, edgecolor="#999"))
    ax.grid(alpha=0.15)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def fmt_p(x, pair):
    return f"{x:.3f}" if pair.endswith("jpy") else f"{x:.5f}"


def t_ist(st, i):
    return "" if i is None else st.df.index[i].tz_convert(IST).strftime("%Y-%m-%d %H:%M")


# ----------------------------------------------------------------------------- concepts
def concept_structure(ctx, out):
    """01: confirmed highs/lows + BOS/CHOCH, last 140 bars per pair/TF."""
    rows = []
    os.makedirs(out, exist_ok=True)
    for (pair, tf), st in ctx["st"].items():
        a = st.n - 140
        labels, lines = [], []
        for s in st.swings:
            if s["i"] >= a:
                y = st.H[s["i"]] if s["t"] == "H" else st.L[s["i"]]
                labels.append((s["i"], y, "CH" if s["t"] == "H" else "CL", "#0d47a1", 8 if s["t"] == "H" else -14))
        for e in st.events:
            if e["i"] >= a:
                txt = {"BOS": "BOS", "CHOCH": "CHOCH", "DUAL_CHOCH": "DUAL"}[e["kind"]]
                col = {"BOS": "#2e7d32", "CHOCH": "#e65100", "DUAL_CHOCH": "#6a1b9a"}[e["kind"]]
                y = st.H[e["i"]] if e["dir"] == 1 else st.L[e["i"]]
                labels.append((e["i"], y, txt, col, 16 if e["dir"] == 1 else -24))
        lst = st.last
        trend = "BULLISH" if lst["trend"] == 1 else "BEARISH"
        inv = st.L[lst["inv_i"]] if lst["trend"] == 1 else st.H[lst["inv_i"]]
        lines.append((lst["inv_i"], inv, f"last {'support' if lst['trend'] == 1 else 'resistance'} {fmt_p(inv, pair)}",
                      "#b71c1c", "--"))
        if lst["conf_i"] is not None:
            y = st.H[lst["conf_i"]] if lst["trend"] == 1 else st.L[lst["conf_i"]]
            lines.append((lst["conf_i"], y, f"confirmed {'high' if lst['trend'] == 1 else 'low'} {fmt_p(y, pair)} (BOS trigger)",
                          "#0d47a1", ":"))
        fn = f"{pair.upper()}_{TF_NAME[tf]}.png"
        plot_setup(st, os.path.join(out, fn), f"{pair.upper()} {TF_NAME[tf]} — structure marking (CH/CL = confirmed high/low)",
                   a, st.n, lines=lines, labels=labels,
                   note=f"Current structure: {trend}. CH confirmed by 2-candle retracement; CL confirmed by 1 candle close above CH (mirror for bearish).")
        n_bos = sum(e["kind"] == "BOS" for e in st.events)
        n_ch = sum(e["kind"] in ("CHOCH", "DUAL_CHOCH") for e in st.events)
        rows.append(dict(pair=pair.upper(), tf=TF_NAME[tf], bars=st.n, from_=t_ist(st, 0)[:10], trend_now=trend,
                         last_inv=fmt_p(inv, pair), BOS=n_bos, CHOCH=n_ch,
                         bos_per_choch=round(n_bos / max(1, n_ch), 2), chart=fn))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(out, "structure_summary.csv"), index=False)
    return df


def run_zone_trades(ctx, concept, setups_fn):
    rows = []
    for (pair, tf), st in ctx["st"].items():
        ltf = ctx["data"].get((pair, LTF[tf]))
        htf_st = ctx["st"].get((pair, HTF[tf])) if HTF[tf] else None
        a_ = atr(st.df)
        for s in setups_fn(st, pair, tf):
            buf = 0.1 * a_[s["i"]]
            res = trade_zone(st, ltf, a_, s["dir"], s["zone"], s["inval"], s["start"], s["start"] + WINDOW, buf,
                             raw_sl=s.get("raw_sl"))
            if not res:
                continue
            htf_tr = htf_st.trend_at(st.df.index[s["i"]]) if htf_st else 0
            for method, t in res.items():
                rows.append(dict(concept=concept, pair=pair.upper(), tf=TF_NAME[tf], setup=s["name"],
                                 dir="buy" if s["dir"] == 1 else "sell", setup_time=t_ist(st, s["i"]),
                                 method=method, entry_time=t_ist(st, t["fill_i"]), entry=fmt_p(t["entry"], pair),
                                 sl=fmt_p(t["sl"], pair), tp=fmt_p(t["tp"], pair),
                                 risk_pips=round(abs(t["entry"] - t["sl"]) / pip(pair), 1),
                                 result=t["result"], exit_time=t_ist(st, t["exit_i"]), mfe_R=t["mfe"],
                                 htf_trend={1: "bull", -1: "bear", 0: "n/a"}[htf_tr],
                                 with_htf=("n/a" if htf_tr == 0 else ("yes" if htf_tr == s["dir"] else "no")),
                                 extra=s.get("extra", ""),
                                 _key=(pair, tf), _s=s, _t=t))
    return rows


def stats_table(rows, by):
    df = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in rows])
    if df.empty:
        return df, df
    closed = df[df.result.isin(["win", "loss"])]
    g = closed.groupby(by)
    tab = pd.DataFrame({
        "trades": g.size(),
        "wins": g.apply(lambda x: (x.result == "win").sum()),
        "losses": g.apply(lambda x: (x.result == "loss").sum()),
    })
    tab["win%"] = (100 * tab.wins / tab.trades).round(1)
    tab["net_R"] = (tab.wins * RR - tab.losses).round(1)
    tab["R/trade"] = (tab.net_R / tab.trades).round(2)
    # reach-rates from MFE (how often price got to 1R/2R before stop or end)
    g2 = df.groupby(by)
    tab["hit1R%"] = (100 * g2.apply(lambda x: (x.mfe_R >= 1).mean())).round(1)
    tab["hit2R%"] = (100 * g2.apply(lambda x: (x.mfe_R >= 2).mean())).round(1)
    return df, tab.reset_index()


def save_examples(ctx, rows, out, title_fn, zones_fn, per_tf=4):
    os.makedirs(os.path.join(out, "examples"), exist_ok=True)
    made = []
    conf = [r for r in rows if r["method"] == "confirmed" and r["result"] in ("win", "loss")]
    for tf in TFS:
        sel = [r for r in conf if r["tf"] == TF_NAME[tf]]
        sel = sorted(sel, key=lambda r: r["setup_time"], reverse=True)
        picks, seen_setups = [], set()
        # latest win and latest loss for each zone type first, then fill up to per_tf
        for name in sorted({r["setup"] for r in sel}):
            for res in ("win", "loss"):
                r = next((x for x in sel if x["setup"] == name and x["result"] == res), None)
                if r and len(picks) < per_tf:
                    picks.append(r)
        for r in sel:
            if len(picks) >= per_tf:
                break
            if r not in picks:
                picks.append(r)
        for r in picks:
            pair, tfk = r["_key"]
            st = ctx["st"][(pair, tfk)]
            s, t = r["_s"], r["_t"]
            a = min(s.get("from", s["i"]), s["i"]) - 25
            b = (t["exit_i"] if t["exit_i"] is not None else t["fill_i"]) + 20
            b = min(max(b, s["i"] + 30), a + 220)
            fn = f"{TF_NAME[tfk]}_{pair.upper()}_{r['setup_time'][:10]}_{s['name'].replace(' ', '').replace('/', '-').replace('+', 'plus')}_{r['result']}.png"
            note = (f"{r['dir'].upper()} {s['name']} | entry {r['entry']} ({r['entry_time']} IST, LTF engulf {TF_NAME[LTF[tfk]]})\n"
                    f"SL {r['sl']}  TP {r['tp']} (1:{RR:g})  risk {r['risk_pips']} pips  -> {r['result'].upper()}"
                    f"  | HTF trend {r['htf_trend']} (with HTF: {r['with_htf']})")
            lines = [(t["fill_i"], t["entry"], "entry", "#000", "-"), (t["fill_i"], t["sl"], "SL", "#b71c1c", "--"),
                     (t["fill_i"], t["tp"], "TP", "#1b5e20", "--")]
            plot_setup(st, os.path.join(out, "examples", fn), title_fn(r), a, b, zones=zones_fn(st, s),
                       lines=lines, labels=s.get("labels", []), trades=[t], note=note)
            made.append((r, fn))
    return made


# --- 02 TJL
def tjl_setups(st, pair, tf):
    a_ = atr(st.df)
    for k, e in enumerate(st.events):
        if e["kind"] != "BOS":
            continue
        d = e["dir"]
        z1 = st.zh(e["lvl1"]) if d == 1 else st.zl(e["lvl1"])
        z2 = st.zl(e["lvl2"]) if d == 1 else st.zh(e["lvl2"])
        lvl2_price = st.L[e["lvl2"]] if d == 1 else st.H[e["lvl2"]]
        impulse = abs(st.C[e["i"]] - lvl2_price) / max(a_[e["i"]], 1e-12)
        labels = [(e["lvl1"], st.H[e["lvl1"]] if d == 1 else st.L[e["lvl1"]], "1", "#0d47a1", 8 if d == 1 else -14),
                  (e["lvl2"], lvl2_price, "2", "#0d47a1", -14 if d == 1 else 8),
                  (e["i"], st.C[e["i"]], "BOS", "#2e7d32", 14 if d == 1 else -20)]
        base = dict(i=e["i"], dir=d, start=e["i"] + 1, inval=lvl2_price, from_=e["lvl2"], labels=labels,
                    z1=z1, z2=z2)
        strong = impulse >= 2.5
        yield dict(base, name="TJL1", zone=z1, raw_sl=z2[0] if d == 1 else z2[1],
                   extra=f"impulse {impulse:.1f} ATR ({'strong' if strong else 'weak'})", **{"from": e["lvl2"]})
        yield dict(base, name="TJL2 A+", zone=z2, extra=f"impulse {impulse:.1f} ATR", **{"from": e["lvl2"]})


def tjl_zones(st, s):
    d = s["dir"]
    col = "#2e7d32" if d == 1 else "#c62828"
    return [(s["labels"][0][0], s["z1"], "TJL1", col), (s["labels"][1][0], s["z2"], "TJL2 A+", col)]


# --- 03 CHOCH  (and 04 Dual CHOCH uses the same event list)
def choch_setups_factory(kinds):
    def gen(st, pair, tf):
        for e in st.events:
            if e["kind"] not in kinds or e["lvl1"] is None:
                continue
            d = e["dir"]
            l1, l2, l3 = e["lvl1"], e["lvl2"], e["lvl3"]
            if d == -1:   # bearish CHOCH: sell from SBR (lvl2 low), A+ (lvl1 high), DT (lvl3 high)
                zs = {"SBR": st.zl(l2), "A+ (QML)": st.zh(l1), "DT": st.zh(l3)}
                inval = st.H[l3]
            else:
                zs = {"RBS": st.zh(l2), "A+ (QML)": st.zl(l1), "DB": st.zl(l3)}
                inval = st.L[l3]
            labels = [(l1, st.H[l1] if d == -1 else st.L[l1], "1", "#0d47a1", 8 if d == -1 else -14),
                      (l2, st.L[l2] if d == -1 else st.H[l2], "2", "#0d47a1", -14 if d == -1 else 8),
                      (l3, st.H[l3] if d == -1 else st.L[l3], "3", "#0d47a1", 8 if d == -1 else -14),
                      (e["i"], st.C[e["i"]], "DUAL CHOCH" if e["kind"] == "DUAL_CHOCH" else "CHOCH", "#e65100",
                       -22 if d == -1 else 16)]
            for name, z in zs.items():
                # A+ sits between SBR and DT: tighter stop just beyond the zone (course: "A+ offers less stoploss")
                yield dict(i=e["i"], dir=d, start=e["i"] + 1, inval=inval if name not in ("DT", "DB") else
                           (st.H[l3] + 1e9 if d == -1 else st.L[l3] - 1e9),
                           name=name, zone=z, labels=labels, zs=zs, kind=e["kind"], **{"from": min(l1, l2, l3)})
    return gen


def choch_zones(st, s):
    col = "#c62828" if s["dir"] == -1 else "#2e7d32"
    lab = s["labels"]
    pos = {"SBR": lab[1][0], "RBS": lab[1][0], "A+ (QML)": lab[0][0], "DT": lab[2][0], "DB": lab[2][0]}
    return [(pos[k], z, k, col if k == s["name"] else "#757575") for k, z in s["zs"].items()]


# --- 04 Dual CHOCH: trade the resumed trend from the new 4th level and the broken DT/DB
def dual_setups(st, pair, tf):
    for e in st.events:
        if e["kind"] != "DUAL_CHOCH":
            continue
        d = e["dir"]
        l4 = e["lvl3"]                       # reversal extreme = new level 4
        if d == -1:
            z4 = st.zh(l4)
            # broken double bottom (the old level 3 of the previous CHOCH) = lvl2 of this event
            zb = st.zl(e["lvl2"])
        else:
            z4 = st.zl(l4)
            zb = st.zh(e["lvl2"])
        labels = [(l4, st.H[l4] if d == -1 else st.L[l4], "4", "#6a1b9a", 8 if d == -1 else -14),
                  (e["lvl2"], st.L[e["lvl2"]] if d == -1 else st.H[e["lvl2"]], "DB" if d == -1 else "DT", "#0d47a1",
                   -14 if d == -1 else 8),
                  (e["i"], st.C[e["i"]], "DUAL CHOCH", "#6a1b9a", -22 if d == -1 else 16)]
        inval = st.H[l4] if d == -1 else st.L[l4]
        zs = {"level 4": z4, "broken DB" if d == -1 else "broken DT": zb}
        for name, z in zs.items():
            yield dict(i=e["i"], dir=d, start=e["i"] + 1, inval=inval if name != "level 4" else
                       (inval + 1e9 if d == -1 else inval - 1e9), name=name, zone=z,
                       labels=labels, zs=zs, **{"from": min(l4, e["lvl2"])})


def dual_zones(st, s):
    col = "#6a1b9a"
    return [(s["labels"][0][0] if k == "level 4" else s["labels"][1][0], z, k, col if k == s["name"] else "#757575")
            for k, z in s["zs"].items()]


# --- 05 ISS
def iss_setups(st, pair, tf):
    evs = st.events
    for k, e in enumerate(evs):
        if e["kind"] != "BOS":
            continue
        end = evs[k + 1]["i"] if k + 1 < len(evs) else st.n
        d = e["dir"]
        lvl2 = e["lvl2"]
        if d == 1:
            # level 3 = high of the last bullish impulse before 5 waves down start; wave 5 must stay above level 2
            seg_hi = e["i"] + int(np.argmax(st.H[e["i"]:end])) if end > e["i"] else e["i"]
            w = st.waves(seg_hi, end, "L")
            lvl2p = st.L[lvl2]
            if len(w) >= 5:
                w1, w2, w3, w4, w5 = w[:5]
                ok = (w3[1] and st.L[w3[1]] < st.L[w1[1]] and st.H[w4[1]] < st.H[w2[1]] and st.L[w5[1]] < st.L[w3[1]]
                      and st.L[w5[1]] > lvl2p and st.H[w2[1]] < st.H[seg_hi])
                # no close below level 2 and no close above level 3 before wave 5 is confirmed
                if ok and st.C[seg_hi:w5[2] + 1].min() > lvl2p and st.C[seg_hi + 1:w5[2] + 1].max() <= st.H[seg_hi]:
                    pts = [w1, w2, w3, w4, w5]
                    zs = {"wave 3": st.zl(w3[1]), "wave 4": st.zh(w4[1])}
                    labels = [(seg_hi, st.H[seg_hi], "L3", "#0d47a1", 8), (lvl2, lvl2p, "L2", "#0d47a1", -14)] + \
                             [(p[1], st.L[p[1]] if p[0] == "L" else st.H[p[1]], str(n + 1), "#000",
                               -14 if p[0] == "L" else 8) for n, p in enumerate(pts)]
                    for name, z in zs.items():
                        yield dict(i=w5[2], dir=-1, start=w5[2] + 1, inval=st.H[seg_hi], name=name, zone=z, zs=zs,
                                   labels=labels, **{"from": lvl2})
        else:
            seg_lo = e["i"] + int(np.argmin(st.L[e["i"]:end])) if end > e["i"] else e["i"]
            w = st.waves(seg_lo, end, "H")
            lvl2p = st.H[lvl2]
            if len(w) >= 5:
                w1, w2, w3, w4, w5 = w[:5]
                ok = (st.H[w3[1]] > st.H[w1[1]] and st.L[w4[1]] > st.L[w2[1]] and st.H[w5[1]] > st.H[w3[1]]
                      and st.H[w5[1]] < lvl2p and st.L[w2[1]] > st.L[seg_lo])
                if ok and st.C[seg_lo:w5[2] + 1].max() < lvl2p and st.C[seg_lo + 1:w5[2] + 1].min() >= st.L[seg_lo]:
                    pts = [w1, w2, w3, w4, w5]
                    zs = {"wave 3": st.zh(w3[1]), "wave 4": st.zl(w4[1])}
                    labels = [(seg_lo, st.L[seg_lo], "L3", "#0d47a1", -14), (lvl2, lvl2p, "L2", "#0d47a1", 8)] + \
                             [(p[1], st.L[p[1]] if p[0] == "L" else st.H[p[1]], str(n + 1), "#000",
                               -14 if p[0] == "L" else 8) for n, p in enumerate(pts)]
                    for name, z in zs.items():
                        yield dict(i=w5[2], dir=1, start=w5[2] + 1, inval=st.L[seg_lo], name=name, zone=z, zs=zs,
                                   labels=labels, **{"from": lvl2})


def iss_zones(st, s):
    col = "#c62828" if s["dir"] == -1 else "#2e7d32"
    return [(s["labels"][2 + (2 if k == "wave 3" else 3)][0], z, k, col) for k, z in s["zs"].items()]


# ----------------------------------------------------------------------------- reporting
def md_table(df):
    if df is None or df.empty:
        return "_no closed trades_\n"
    cols = list(df.columns)
    out = "| " + " | ".join(str(c) for c in cols) + " |\n|" + "|".join("---" for _ in cols) + "|\n"
    for _, r in df.iterrows():
        out += "| " + " | ".join(str(r[c]) for c in cols) + " |\n"
    return out


def write_concept(out, title, rules, rows, made, extra_md=""):
    df, by_tf = stats_table(rows, ["tf", "method"])
    _, by_setup = stats_table(rows, ["tf", "setup", "method"])
    _, by_htf = stats_table(rows, ["tf", "with_htf", "method"])
    df.to_csv(os.path.join(out, "trades.csv"), index=False)
    md = f"# {title}\n\n## Rules practised\n{rules}\n\n"
    md += ("## How it was tested\n"
           f"- Pairs: {', '.join(p.upper() for p in PAIRS)} (none on your watchlist). Data: Dukascopy bid, times in IST.\n"
           f"- Each setup is traded two ways: **raw** = limit order at the zone edge, SL beyond the zone (+0.1 ATR); "
           f"**confirmed** = wait for price to touch the zone, then the first engulfing candle on the lower timeframe "
           f"(D1→H1, H4→M15, H1→M5, M15→M1), market entry at its close, SL beyond the touch swing (+0.1 ATR).\n"
           f"- Target 1:{RR:g} (course examples ~1:3). A setup is cancelled if a candle closes through its invalidation "
           f"level before entry. `hit1R%`/`hit2R%` = how often price reached 1R/2R before the stop (useful if you'd book earlier).\n"
           f"- Break-even win rate at 1:{RR:g} is {100 / (RR + 1):.0f}%.\n\n")
    md += "## Results by timeframe\n" + md_table(by_tf) + "\n"
    md += "## Results by zone\n" + md_table(by_setup) + "\n"
    md += "## With vs against the higher-timeframe trend\n" + md_table(by_htf) + "\n"
    md += extra_md
    md += "## Example charts (confirmed entries; most recent wins and losses per timeframe)\n"
    for r, fn in made:
        md += f"### {r['tf']} {r['pair']} — {r['setup']} {r['dir']} — {r['result'].upper()}\n"
        md += (f"Setup {r['setup_time']} IST · entry {r['entry']} at {r['entry_time']} · SL {r['sl']} · TP {r['tp']} · "
               f"risk {r['risk_pips']} pips · HTF trend {r['htf_trend']}\n\n![](examples/{fn})\n\n")
    md += "\nFull trade log: `trades.csv` (one row per setup × entry method).\n"
    with open(os.path.join(out, "README.md"), "w", encoding="utf-8") as f:
        f.write(md)
    return by_tf


def main():
    data_dir, out_root = sys.argv[1], sys.argv[2]
    os.makedirs(out_root, exist_ok=True)
    data, sts = {}, {}
    for p in PAIRS:
        for tf in ["m1", "m5", "m15", "h1", "h4", "d1"]:
            d = load(data_dir, p, tf)
            if d is not None:
                data[(p, tf)] = d
    for p in PAIRS:
        for tf in TFS:
            if (p, tf) in data:
                sts[(p, tf)] = Structure(data[(p, tf)]).run()
    ctx = dict(data=data, st=sts)
    summary = {}

    # 01
    out = os.path.join(out_root, "01_structure_marking")
    sdf = concept_structure(ctx, out)
    md = ("# 01 — Structure marking (confirmed highs/lows, BOS, CHOCH)\n\n## Rules practised\n"
          "- Buying waves = impulse, selling waves = correction (bullish); never trade the retracement.\n"
          "- **High confirmed** after a 2-candle retracement: 2 consecutive red candles, 2nd body closes below the 1st's low.\n"
          "- **Low confirmed** when 1 candle CLOSES above that confirmed high (= BOS). In bullish structure the high is confirmed first.\n"
          "- No new 2-candle retracement is looked for until the previous high is broken. Bearish = mirror.\n"
          "- Confirmed low = last support (level 2); a 2-candle close below it = CHOCH.\n\n"
          "## Current structure per pair and timeframe\n" + md_table(sdf.drop(columns=["chart"])) +
          "\n`BOS/CHOCH` = continuation vs reversal count — higher means cleaner trending structure on that timeframe.\n\n")
    for tf in TFS:
        md += f"## {TF_NAME[tf]}\n"
        for p in PAIRS:
            md += f"### {p.upper()} {TF_NAME[tf]}\n![]({p.upper()}_{TF_NAME[tf]}.png)\n\n"
    with open(os.path.join(out, "README.md"), "w", encoding="utf-8") as f:
        f.write(md)
    summary["01 Structure"] = sdf

    # 02 TJL
    out = os.path.join(out_root, "02_TJL1_TJL2")
    os.makedirs(out, exist_ok=True)
    rows = run_zone_trades(ctx, "TJL", tjl_setups)
    made = save_examples(ctx, rows, out, lambda r: f"{r['tf']} {r['pair']} — {r['setup']} ({r['dir']}) after BOS {r['setup_time']} IST",
                         tjl_zones)
    strong = [r for r in rows if r["setup"] == "TJL1" and "strong" in r["extra"]]
    weak = [r for r in rows if r["setup"] == "TJL1" and "weak" in r["extra"]]
    _, t_strong = stats_table(strong, ["tf", "method"])
    _, t_weak = stats_table(weak, ["tf", "method"])
    extra = ("## Course filter: TJL1 only after a strong impulse (BOS leg ≥ 2.5 ATR)\n### Strong impulse\n" + md_table(t_strong) +
             "\n### Weak impulse (course says skip TJL1, use TJL2)\n" + md_table(t_weak) + "\n")
    summary["02 TJL"] = write_concept(out, "02 — Trend Joining Levels (TJL1 / TJL2 A+)",
                                      "- After every BOS: **TJL1** = zone at level 1 (the broken confirmed high/low), "
                                      "**TJL2 (A+)** = zone at level 2 (last support/resistance).\n"
                                      "- Buy pullbacks into TJL1/TJL2 in bullish structure, sell in bearish. Zone = wick + 1% of body.\n"
                                      "- Trade TJL1 only after a strong impulse; otherwise wait for TJL2.\n"
                                      "- Invalidation: close beyond level 2 (that is a CHOCH).", rows, made, extra)

    # 03 CHOCH
    out = os.path.join(out_root, "03_CHOCH")
    os.makedirs(out, exist_ok=True)
    rows = run_zone_trades(ctx, "CHOCH", choch_setups_factory(("CHOCH",)))
    made = save_examples(ctx, rows, out, lambda r: f"{r['tf']} {r['pair']} — {r['setup']} {r['dir']} after CHOCH {r['setup_time']} IST",
                         choch_zones)
    summary["03 CHOCH"] = write_concept(out, "03 — Change of Character (CHOCH)",
                                        "- **Bearish CHOCH**: 2 consecutive candles CLOSE below the last support (level 2); first must be red, "
                                        "second any colour. **Bullish** = mirror above last resistance.\n"
                                        "- Then trade the opposite way from 3 levels: **SBR/RBS** (level 2), **A+ / QML** (level 1, best: smallest stop), "
                                        "**DT/DB** (level 3).\n- SBR/A+ setups are cancelled if price closes beyond DT/DB first (that would be a Dual CHOCH).",
                                        rows, made)

    # 04 Dual CHOCH
    out = os.path.join(out_root, "04_Dual_CHOCH")
    os.makedirs(out, exist_ok=True)
    rows = run_zone_trades(ctx, "DUAL", dual_setups)
    made = save_examples(ctx, rows, out, lambda r: f"{r['tf']} {r['pair']} — {r['setup']} {r['dir']} after DUAL CHOCH {r['setup_time']} IST",
                         dual_zones)
    # how often a CHOCH turned into a Dual CHOCH
    rate_rows = []
    for (p, tf), st in sts.items():
        n_ch = sum(e["kind"] == "CHOCH" for e in st.events)
        n_d = sum(e["kind"] == "DUAL_CHOCH" for e in st.events)
        rate_rows.append(dict(tf=TF_NAME[tf], pair=p.upper(), choch=n_ch, dual=n_d))
    rr_df = pd.DataFrame(rate_rows).groupby("tf")[["choch", "dual"]].sum()
    rr_df["dual% of CHOCH"] = (100 * rr_df.dual / rr_df.choch.clip(lower=1)).round(1)
    extra = "## How often a CHOCH failed into a Dual CHOCH\n" + md_table(rr_df.reset_index()) + "\n"
    summary["04 Dual CHOCH"] = write_concept(out, "04 — Dual CHOCH",
                                             "- After a normal CHOCH, price reverses from an exact zone and CLOSES back beyond level 3 "
                                             "(double top / double bottom) with 2 candles → the original trend resumes.\n"
                                             "- Mark the reversal extreme as the **new 4th level**; trade the resumed trend from level 4 "
                                             "and from the broken DT/DB.", rows, made, extra)

    # 05 ISS
    out = os.path.join(out_root, "05_ISS")
    os.makedirs(out, exist_ok=True)
    rows = run_zone_trades(ctx, "ISS", iss_setups)
    made = save_examples(ctx, rows, out, lambda r: f"{r['tf']} {r['pair']} — ISS {r['setup']} {r['dir']} (wave 5 confirmed {r['setup_time']} IST)",
                         iss_zones)
    summary["05 ISS"] = write_concept(out, "05 — Internal Structure Shift (5-wave CHOCH)",
                                      "- Inside the **last impulse** (level 2 → level 3), 5 waves form **against the trend** on the **same timeframe**, "
                                      "each wave confirmed with the 2-candle retracement rule.\n"
                                      "- Wave 5 must be confirmed by its own 2-candle retracement and must NOT close beyond level 2 "
                                      "(that would be a normal CHOCH).\n- Trade from the **wave 3** and **wave 4** zones (wick + 1% body). "
                                      "Course: works best on H1 and M15; never trade against the trend.", rows, made)

    # index
    md = ("# TopG practice — one concept at a time across timeframes\n\n"
          f"Generated by `practice.py`. Pairs: {', '.join(p.upper() for p in PAIRS)}; timeframes: M15, H1, H4, D1.\n"
          "Data ranges: D1 from Nov 2024, H4 from Nov 2025, H1 from May 2026, M15 from mid-Aug 2026 (confirmations need M1/M5/M15/H1 data, "
          "available from mid-Aug 2026 for M1/M5).\n\n"
          "| # | Concept | Folder |\n|---|---|---|\n"
          "| 01 | Structure marking | [01_structure_marking](01_structure_marking/README.md) |\n"
          "| 02 | TJL1 / TJL2 A+ | [02_TJL1_TJL2](02_TJL1_TJL2/README.md) |\n"
          "| 03 | CHOCH (SBR/RBS, A+, DT/DB) | [03_CHOCH](03_CHOCH/README.md) |\n"
          "| 04 | Dual CHOCH | [04_Dual_CHOCH](04_Dual_CHOCH/README.md) |\n"
          "| 05 | ISS / 5-wave CHOCH | [05_ISS](05_ISS/README.md) |\n\n")
    for k in ("02 TJL", "03 CHOCH", "04 Dual CHOCH", "05 ISS"):
        md += f"## {k} — by timeframe\n" + md_table(summary[k]) + "\n"
    with open(os.path.join(out_root, "README.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)


if __name__ == "__main__":
    main()
