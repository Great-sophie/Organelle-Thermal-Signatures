# -*- coding: utf-8 -*-
"""
Created on Tue Jan 13 22:02:31 2026

@author: sophi
"""
# -*- coding: utf-8 -*-
"""
Fig6B (optimized) script for your 3-row header Excel table
- Cleaner y-axis (2°C ticks) + "Organelle temperature"
- Reduce significance brackets (keep key comparisons only)
- Add n annotation per cell line (paired cells with all 3 organelles)
- Optional 37°C reference dashed line
- No organelle-connecting lines, no RM-ANOVA text, no 'ns' brackets/lines
"""

import os
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

# =========================================================
# 0) YOU ONLY EDIT HERE
# =========================================================
DATA_PATH = r"E:\TIRF imaging\organelle temperature.xlsx"
SHEET_NAME = 0
OUT_FIG = os.path.splitext(DATA_PATH)[0] + "_Fig6B_optimized.tiff"

CELL_ORDER = ["BT474(Her2+)", "MCF-7(Her2-)", "MDA-MB-231(TNBC)"]
ORG_ORDER = ["Mito", "ER", "Golgi"]

COLORS = {"Mito": "#C00000", "ER": "#7030A0", "Golgi": "#FFC000"}
OFFSETS = {"Mito": -0.25, "ER": 0.00, "Golgi": 0.25}

DOT_SIZE = 18
JITTER = 0.06
SAVE_DPI = 600

# --- NEW: y-axis + reference line settings ---
Y_TICK_STEP = 2.0             # 2 °C ticks
ADD_37C_REF = True            # add 37°C reference dashed line
REF_TEMP = 37.0
REF_COLOR = "#B0B0B0"
REF_LW = 1.2
REF_LS = "--"

# --- NEW: stats bracket simplification ---
# Keep only key within-cell-line comparisons
KEEP_PAIRS = [("Mito", "Golgi"), ("Mito", "ER")]   # order matters for stacking
# If you also want ER vs Golgi, set True:
INCLUDE_ER_VS_GOLGI = False

# =========================================================
# Matplotlib style
# =========================================================
plt.rcParams["font.family"] = "Times New Roman"
plt.rcParams["axes.linewidth"] = 2.2
plt.rcParams["xtick.major.width"] = 2.0
plt.rcParams["ytick.major.width"] = 2.0


# =========================================================
# Helpers: normalize labels
# =========================================================
def _clean(s: str) -> str:
    return re.sub(r"\s+", "", str(s).strip().lower())

def norm_cell(x) -> str:
    s0 = _clean(x)
    if s0.startswith("bt474") or "bt-474" in s0:
        return "BT474(Her2+)"
    if s0.startswith("mcf7") or s0.startswith("mcf-7") or "mcf7" in s0:
        return "MCF-7(Her2-)"
    if "231" in s0 and ("mda" in s0 or "mb" in s0 or "mdamb" in s0):
        return "MDA-MB-231(TNBC)"
    return str(x).strip()

def norm_organelle(x) -> str:
    s = _clean(x)
    if s in ["mito", "mt", "mitochondria", "mitochondrion", "mitochondrial"] or "mito" in s:
        return "Mito"
    if s in ["er", "endoplasmicreticulum", "endoplasmicreticular"] or "endoplasmic" in s or s.endswith("reticulum"):
        return "ER"
    if s in ["golgi", "ga", "golgiapparatus", "golgibody", "golgicomplex"] or "golgi" in s:
        return "Golgi"
    return str(x).strip()

def norm_time(x) -> str:
    s = _clean(x)
    if s in ["0min", "0m", "0"]:
        return "0min"
    if s in ["1min", "1m", "1"]:
        return "1min"
    if s in ["2min", "2m", "2"]:
        return "2min"
    return str(x).strip()


# =========================================================
# 1) Read table (3 header rows) -> long
# =========================================================
def read_table(path, sheet=0) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext in [".xlsx", ".xls"]:
        df_raw = pd.read_excel(path, sheet_name=sheet, header=None)
    elif ext == ".csv":
        df_raw = pd.read_csv(path, header=None)
    else:
        raise ValueError("Only .xlsx/.xls/.csv supported.")

    first_col = df_raw.iloc[:, 0].astype(str).str.strip().str.lower()

    def find_row(keyword: str):
        hits = np.where(first_col.str.contains(keyword))[0]
        return int(hits[0]) if len(hits) else None

    r_cell = find_row("cell")
    r_org = find_row("organelle")
    r_time = find_row("time")
    if r_cell is None or r_org is None or r_time is None:
        raise RuntimeError("Cannot find header rows: cell / organelle / time.")

    hdr_cells = df_raw.iloc[r_cell, 1:].astype(str).str.strip()
    hdr_orgs  = df_raw.iloc[r_org, 1:].astype(str).str.strip()
    hdr_time  = df_raw.iloc[r_time, 1:].astype(str).str.strip()

    hdr_cells = hdr_cells.replace({"": np.nan, "nan": np.nan}).ffill().apply(norm_cell)
    hdr_orgs  = hdr_orgs.apply(norm_organelle)
    hdr_time  = hdr_time.apply(norm_time)

    data_start = r_time + 1
    df_data = df_raw.iloc[data_start:, :].copy()

    row_labels = df_data.iloc[:, 0].astype(str).str.strip()
    val = df_data.iloc[:, 1:].copy()

    keep = row_labels.str.lower().str.contains("temperature")
    if keep.sum() == 0:
        raise RuntimeError("No rows containing 'temperature' were found in the first column.")

    rep_names = row_labels[keep].reset_index(drop=True)
    val = val[keep].reset_index(drop=True)
    val = val.apply(pd.to_numeric, errors="coerce")

    cols = [f"{c}|{o}|{t}" for c, o, t in zip(hdr_cells, hdr_orgs, hdr_time)]
    val.columns = cols

    df_long = val.copy()
    df_long["Replicate"] = rep_names
    df_long = df_long.melt(id_vars=["Replicate"], var_name="key", value_name="TempC").dropna()
    df_long[["Cell", "Organelle", "Time"]] = df_long["key"].str.split("|", expand=True)
    df_long.drop(columns=["key"], inplace=True)

    df_long["Cell"] = df_long["Cell"].apply(norm_cell)
    df_long["Organelle"] = df_long["Organelle"].apply(norm_organelle)
    df_long["Time"] = df_long["Time"].apply(norm_time)

    df_long = df_long[df_long["Cell"].isin(CELL_ORDER)]
    df_long = df_long[df_long["Organelle"].isin(ORG_ORDER)]
    df_long = df_long[df_long["Time"].isin(["0min", "1min", "2min"])]

    return df_long.reset_index(drop=True)


# =========================================================
# 2) Pool 0/1/2 min per replicate (cell)
# =========================================================
def pool_0to2min(df_long: pd.DataFrame) -> pd.DataFrame:
    pooled = (
        df_long
        .groupby(["Cell", "Organelle", "Replicate"], as_index=False)["TempC"]
        .mean()
        .rename(columns={"TempC": "TempC_pooled"})
    )
    return pooled


# =========================================================
# 3) Stats: paired t-tests + Holm correction (step-down)
# =========================================================
def stars(p: float) -> str:
    if p < 1e-4: return "****"
    if p < 1e-3: return "***"
    if p < 1e-2: return "**"
    if p < 5e-2: return "*"
    return "ns"

def holm_adjust(pvals):
    pvals = np.asarray(pvals, dtype=float)
    m = pvals.size
    order = np.argsort(pvals)
    adj_sorted = np.empty(m, dtype=float)
    running_max = 0.0
    for rank, idx in enumerate(order):
        factor = m - rank
        running_max = max(running_max, pvals[idx] * factor)
        adj_sorted[rank] = running_max
    adj = np.empty(m, dtype=float)
    for rank, idx in enumerate(order):
        adj[idx] = min(1.0, adj_sorted[rank])
    return adj.tolist()

def paired_posthoc_holm(df_cell: pd.DataFrame):
    """
    Returns Holm-adjusted p-values for selected pairs, based on paired cells
    that have complete data for all organelles (paired design).
    """
    if df_cell is None or len(df_cell) == 0:
        return {}, 0

    wide = df_cell.pivot_table(index="Replicate", columns="Organelle", values="TempC_pooled")
    if wide is None or wide.shape[0] == 0:
        return {}, 0

    if any(o not in wide.columns for o in ORG_ORDER):
        return {}, 0

    wide = wide.dropna(subset=ORG_ORDER)  # complete paired cells
    n_paired = int(wide.shape[0])
    if n_paired < 2:
        return {}, n_paired

    pairs_all = [("Mito", "ER"), ("ER", "Golgi"), ("Mito", "Golgi")]
    raw_ps = []
    for a, b in pairs_all:
        _, p = stats.ttest_rel(wide[a], wide[b])
        raw_ps.append(float(p))

    adj_ps = holm_adjust(raw_ps)
    pmap = {pairs_all[i]: adj_ps[i] for i in range(len(pairs_all))}
    return pmap, n_paired


# =========================================================
# 4) Plot helpers
# =========================================================
def add_bracket(ax, x1, x2, y, h, text):
    ax.plot([x1, x1, x2, x2], [y, y + h, y + h, y], lw=2.0, c="black", clip_on=False)
    ax.text((x1 + x2) / 2, y + h, text, ha="center", va="bottom", fontsize=11)

def nice_limits_and_ticks(y_min, y_max, step=2.0):
    lo = np.floor(y_min / step) * step
    hi = np.ceil(y_max / step) * step
    if hi - lo < 6:
        hi = lo + 6
    ticks = np.arange(lo, hi + 0.001, step)
    return float(lo), float(hi), ticks

def plot_final(pooled: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(10.8, 4.6), dpi=200)
    x_base = np.arange(len(CELL_ORDER))
    rng = np.random.default_rng(20251230)

    # --- y-limits & ticks (2°C step) ---
    y_all = pooled["TempC_pooled"].values
    y_min_raw = float(np.nanmin(y_all) - 0.8)
    y_max_raw = float(np.nanmax(y_all) + 1.2)
    y_min, y_max, y_ticks = nice_limits_and_ticks(y_min_raw, y_max_raw, step=Y_TICK_STEP)
    ax.set_ylim(y_min, y_max)
    ax.set_yticks(y_ticks)

    # --- optional 37°C reference line ---
    if ADD_37C_REF:
        ax.axhline(REF_TEMP, color=REF_COLOR, lw=REF_LW, ls=REF_LS, zorder=0)

    yr = y_max - y_min
    h = 0.012 * yr
    gap = 0.055 * yr

    # --- draw points + mean±SEM, plus simplified stats ---
    for i, cell in enumerate(CELL_ORDER):
        df_cell = pooled[pooled["Cell"] == cell].copy()

        # scatter + mean±SEM
        local_vals_for_top = []
        for org in ORG_ORDER:
            vals = df_cell.loc[df_cell["Organelle"] == org, "TempC_pooled"].dropna().values
            x0 = x_base[i] + OFFSETS[org]
            jitter = rng.uniform(-JITTER, JITTER, size=len(vals))

            ax.scatter(np.full(len(vals), x0) + jitter, vals,
                       s=DOT_SIZE, color=COLORS[org], edgecolor="none",
                       alpha=0.95, zorder=2)

            if len(vals) > 0:
                mean = float(np.mean(vals))
                sem = float(np.std(vals, ddof=1) / np.sqrt(len(vals))) if len(vals) > 1 else 0.0
                ax.errorbar(x0, mean, yerr=sem, fmt="o",
                            color="black", elinewidth=2.0, capsize=5,
                            markersize=5, zorder=3)
                local_vals_for_top.append(mean + sem)

        # stats (only significant after Holm) + n annotation based on paired cells
        pair_p, n_paired = paired_posthoc_holm(df_cell)

        # n label under each cell line (paired cells with all 3 organelles)
        ax.text(
            x_base[i], -0.16, f"n = {n_paired} cells",
            transform=ax.get_xaxis_transform(),
            ha="center", va="top", fontsize=11
        )

        # brackets: only keep key pairs
        pairs_to_draw = list(KEEP_PAIRS)
        if INCLUDE_ER_VS_GOLGI:
            pairs_to_draw.append(("ER", "Golgi"))

        # local top for brackets (cleaner than global stacking)
        if len(local_vals_for_top) > 0:
            bracket_top = min(y_max - 0.12 * yr, max(local_vals_for_top) + 0.55)
        else:
            bracket_top = y_max - 0.20 * yr

        k_draw = 0
        for (a, b) in pairs_to_draw:
            if (a, b) not in pair_p:
                continue
            p = pair_p[(a, b)]
            if p >= 0.05:
                continue
            s = stars(p)
            x1 = x_base[i] + OFFSETS[a]
            x2 = x_base[i] + OFFSETS[b]
            add_bracket(ax, x1, x2, bracket_top - k_draw * gap, h, s)
            k_draw += 1

    # axes labels
    ax.set_xticks(x_base)
    ax.set_xticklabels(CELL_ORDER, fontsize=13)
    ax.set_ylabel("Organelle temperature (°C)", fontsize=13)

    # legend
    handles = [
        plt.Line2D([0], [0], marker="o", color="none",
                   markerfacecolor=COLORS[o], markeredgecolor="none", markersize=7)
        for o in ORG_ORDER
    ]
    ax.legend(handles, ORG_ORDER, frameon=False, fontsize=12, loc="upper right")

    # spines + ticks
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color("black")
        spine.set_linewidth(2.2)

    ax.tick_params(axis="both", labelsize=12, length=5)
    ax.set_xlim(-0.7, len(CELL_ORDER) - 0.3)

    return fig


# =========================================================
# 5) Main
# =========================================================
def main():
    df_long = read_table(DATA_PATH, sheet=SHEET_NAME)
    if len(df_long) == 0:
        raise RuntimeError("df_long is empty after filtering. Check your header labels and CELL_ORDER mapping.")

    pooled = pool_0to2min(df_long)

    print("QC | Cell unique:", pooled["Cell"].unique())
    print("QC | Organelle unique:", pooled["Organelle"].unique())
    print("QC | Replicate counts:")
    print(pooled.groupby(["Cell", "Organelle"])["Replicate"].nunique())

    fig = plot_final(pooled)
    fig.savefig(OUT_FIG, dpi=SAVE_DPI, bbox_inches="tight")
    plt.close(fig)
    print("Saved:", OUT_FIG)

if __name__ == "__main__":
    main()

