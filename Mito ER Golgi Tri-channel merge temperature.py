# -*- coding: utf-8 -*-
"""
Warm-tilt pipeline to reproduce ~45 °C result:
- 545->525 ORB+RANSAC; apply same affine to 488
- Local min-max of (525+1) within 488 ROI -> u8
- Adaptive 525-u8 threshold: search P80..P90, choose minimal IQR (warm bias)
- Enable 545 upper-cap at P85 (remove very bright 545 to raise ratio)
- Symmetric IQR trimming (K=1.5) on ratio<0
- No background subtraction (warmer)
Outputs: masks, ratio/temperature maps, overlay, summary
"""

import os, cv2, numpy as np, matplotlib.pyplot as plt, tifffile
from scipy.ndimage import binary_opening, binary_closing, gaussian_filter

# ====================== PATHS ======================
im525_path = r"H:\Tirf imaging\Mito temperature\MCF-7\0719-mcf-7-1\live te\525-4.tif"
im545_path = r"H:\Tirf imaging\Mito temperature\MCF-7\0719-mcf-7-1\live te\545-4.tif"
im488_path = r"H:\Tirf imaging\Mito temperature\MCF-7\0719-mcf-7-1\live te\642.tif"
outdir     = r"H:\Tirf imaging\Mito temperature\MCF-7\0719-mcf-7-1\live te\results-4"
os.makedirs(outdir, exist_ok=True)

# ====================== CALIBRATION (LN) ======================
# ratio = ln((525+1)/(545+1)) = k * (1000/(T+273.15)) + b
k, b = -0.99, 2.05
TEMP_VMIN, TEMP_VMAX = 20, 50
EPS_INT = 1.0
EPS_MM  = 1e-12

# ====================== OPTIONS (WARM-BIASED) ======================
# 背景扣除：明确关闭（暖）
DO_BG_SUB     = True       # ★ 之前未定义，这里明确关闭
BG_QUANTILE   = 0.001       # 只是占位，不会用到

# 642 掩膜
SMOOTH_BEFORE_MASK = True
SMOOTH_SIGMA       = 0.8
REMOVE_SATURATED   = True
DILATE_R           = 1

# ROI 清理（尽量不吃掉暖尾）
ERODE_R = 0                # ★ 由 1→0

# 自适应 525-u8 阈值（暖偏置：高分位）
P_RANGE_PRIMARY   = [95]           # ★ 收窄到 P90（更暖、更稳定）
N_MIN_PRIMARY     = 60_000
P_RANGE_FALLBACK  = [70,75]       # 兜底
N_MIN_FALLBACK    = 10_000

# 545 上限护栏（关键）
USE_545_CAP   = True
CAP_545_PERC  = 95            # ★ 取 P85 复现你之前暖结果

# 545 下限护栏关闭（避免拉冷）
USE_545_LOW   = True
LOW_545_PERC  = 20

# 对称 IQR 修剪
DO_IQR_TRIM = True
IQR_K       = 1.5

# ====================== HELPERS ======================
def to_u8_for_features(img16):
    img = cv2.normalize(img16, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    return clahe.apply(img)

def estimate_affine_and_warp(mov_img16, mov_kp, mov_des, ref_kp, ref_des, ref_shape):
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    raw = bf.knnMatch(mov_des, ref_des, k=2)
    good = [m for m,n in raw if m.distance < 0.7*n.distance]
    if len(good) < 6:
        raise RuntimeError("Not enough matches for RANSAC.")
    src = np.float32([mov_kp[m.queryIdx].pt for m in good]).reshape(-1,1,2)
    dst = np.float32([ref_kp[m.trainIdx].pt for m in good]).reshape(-1,1,2)
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                                         ransacReprojThreshold=2.0, maxIters=5000)
    if M is None:
        raise RuntimeError("RANSAC failed.")
    warped = cv2.warpAffine(mov_img16, M, (ref_shape[1], ref_shape[0]),
                            flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    return M, int(inl.sum()) if inl is not None else 0, len(good), warped

def gen_mask(img16, remove_saturated=True, smooth=True, sigma=0.8, dilate_r=0):
    img = img16.astype(np.float32)
    if smooth:
        img = gaussian_filter(img, sigma=sigma)
    img8 = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    img8 = cv2.GaussianBlur(img8, (3,3), 0)
    _, th = cv2.threshold(img8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask = (th > 0).astype(np.uint8)
    mask = binary_opening(mask, structure=np.ones((3,3))).astype(np.uint8)
    mask = binary_closing(mask, structure=np.ones((3,3))).astype(np.uint8)
    if remove_saturated:
        sat = (img16 >= np.iinfo(img16.dtype).max - 1).astype(np.uint8)
        mask[sat == 1] = 0
    if dilate_r > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*dilate_r+1, 2*dilate_r+1))
        mask = cv2.dilate(mask, k, iterations=1)
    return mask

def robust_percentiles(arr, qs):
    v = arr[np.isfinite(arr)]
    return np.nanpercentile(v, qs) if v.size else [np.nan]*len(qs)

def pick_u8_threshold_min_iqr(mm525_local, mask488, im525_f, im545_f, p_range, N_min):
    best = None
    tau_best = p_best = None
    n_best = 0; iqr_best = np.inf
    for p in p_range:
        tau = float(np.nanpercentile(mm525_local[mask488==1], p))
        mfinal = ((mask488==1) & (mm525_local > tau)).astype(np.uint8)
        n_pix = int(mfinal.sum())
        if n_pix < N_min:
            continue
        ratio = np.where(mfinal==1, np.log(im525_f / im545_f), np.nan)
        neg = (ratio < 0) & (~np.isnan(ratio))
        if not np.any(neg):
            continue
        q1, q3 = np.nanpercentile(ratio[neg], [25, 75])
        iqr = float(q3 - q1)
        cand = (iqr, -n_pix, p, tau)
        if (best is None) or (cand < best):
            best = cand
            iqr_best, n_best, p_best, tau_best = iqr, n_pix, p, tau
    return tau_best, p_best, n_best, iqr_best

def stats_block(arr):
    v = arr[np.isfinite(arr)]
    if v.size == 0: return (np.nan, np.nan, np.nan, np.nan)
    mean = float(np.nanmean(v)); std = float(np.nanstd(v))
    med  = float(np.nanmedian(v))
    q25, q75 = np.nanpercentile(v, [25, 75])
    iqr = float(q75 - q25)
    return mean, std, med, iqr

# ====================== READ ======================
im525_raw = cv2.imread(im525_path, -1)
im545_raw = cv2.imread(im545_path, -1)
im488_raw = cv2.imread(im488_path, -1)
if im525_raw is None or im545_raw is None or im488_raw is None:
    raise FileNotFoundError("Failed to read one or more input images.")

# ====================== REGISTER: 545 -> 525; reuse M for 488 ======================
orb = cv2.ORB_create(nfeatures=50000, fastThreshold=5, edgeThreshold=15)
ref8 = to_u8_for_features(im525_raw); kp1, des1 = orb.detectAndCompute(ref8, None)
mov8_545 = to_u8_for_features(im545_raw); kp2, des2 = orb.detectAndCompute(mov8_545, None)
if des1 is None or des2 is None:
    raise RuntimeError("Feature extraction failed for 525/545.")
M545, inl545, m545, im545_aln = estimate_affine_and_warp(im545_raw, kp2, des2, kp1, des1, im525_raw.shape)
im488_aln = cv2.warpAffine(im488_raw, M545, (im525_raw.shape[1], im525_raw.shape[0]),
                           flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)

tifffile.imwrite(os.path.join(outdir, "545_aligned.tiff"), im545_aln.astype(im545_raw.dtype))
tifffile.imwrite(os.path.join(outdir, "488_aligned_via_M545.tiff"), im488_aln.astype(im488_raw.dtype))

# ====================== 488 MASK ======================
mask488 = gen_mask(im488_aln, remove_saturated=REMOVE_SATURATED,
                   smooth=SMOOTH_BEFORE_MASK, sigma=SMOOTH_SIGMA, dilate_r=DILATE_R)
pix_mask488 = int(mask488.sum())
plt.figure(figsize=(5,5)); plt.imshow(mask488, cmap='gray'); plt.axis('off')
plt.tight_layout(); plt.savefig(os.path.join(outdir, "mask_488.png"), dpi=300); plt.close()

# ====================== BACKGROUND (OFF for warm) ======================
if DO_BG_SUB:
    im525_corr = im525_raw.astype(np.float32) - np.percentile(im525_raw, BG_QUANTILE)
    im545_corr = im545_aln.astype(np.float32) - np.percentile(im545_aln, BG_QUANTILE)
    im525_corr[im525_corr < 0] = 0; im545_corr[im545_corr < 0] = 0
else:
    im525_corr = im525_raw.astype(np.float32)
    im545_corr = im545_aln.astype(np.float32)

im525_f = im525_corr.astype(np.float32) + EPS_INT
im545_f = im545_corr.astype(np.float32) + EPS_INT

# ====================== LOCAL MIN-MAX OF 525 WITHIN 488 ROI ======================
vals_525_in_488 = im525_f[mask488 == 1]
lo = float(np.nanmin(vals_525_in_488)) if vals_525_in_488.size else float(np.nanmin(im525_f))
hi = float(np.nanmax(vals_525_in_488)) if vals_525_in_488.size else float(np.nanmax(im525_f))
mm525_local = (im525_f - lo) / (hi - lo + EPS_MM) * 255.0

q10, q25, q50, q75, q90 = robust_percentiles(mm525_local[mask488==1], [10,25,50,75,90])
print(f"mm525(u8) in 488 ROI: P10={q10:.1f}, P25={q25:.1f}, P50={q50:.1f}, P75={q75:.1f}, P90={q90:.1f}")

# ====================== ADAPTIVE THRESHOLD (MIN IQR, WARM BIAS) ======================
tau_u8, p_chosen, n_best, iqr_best = pick_u8_threshold_min_iqr(
    mm525_local, mask488, im525_f, im545_f, p_range=P_RANGE_PRIMARY, N_min=N_MIN_PRIMARY
)
if tau_u8 is None:
    tau_u8, p_chosen, n_best, iqr_best = pick_u8_threshold_min_iqr(
        mm525_local, mask488, im525_f, im545_f, p_range=P_RANGE_FALLBACK, N_min=N_MIN_FALLBACK
    )
if tau_u8 is None:
    p_chosen = 85
    tau_u8 = float(np.nanpercentile(mm525_local[mask488==1], p_chosen))
    n_best, iqr_best = 0, np.nan

mask525_u8 = (mm525_local > tau_u8).astype(np.uint8)
mask_final = ((mask488 == 1) & (mask525_u8 == 1)).astype(np.uint8)

# erosion
if ERODE_R > 0:
    k_ = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*ERODE_R+1, 2*ERODE_R+1))
    mask_final = cv2.erode(mask_final, k_, iterations=1).astype(np.uint8)

pix_final = int(mask_final.sum())
print(f"[AUTO ROI] picked P{p_chosen} -> tau_u8={tau_u8:.1f}, final pixels={pix_final}, iqr(candidate)={iqr_best}")

# 545 upper cap (warm)
cap545 = np.nan
if USE_545_CAP and pix_final > 0:
    vals_545_in_roi = im545_f[mask_final == 1]
    if vals_545_in_roi.size:
        cap545 = float(np.nanpercentile(vals_545_in_roi, CAP_545_PERC))
        mask_final = ((mask_final == 1) & (im545_f <= cap545)).astype(np.uint8)
        pix_final = int(mask_final.sum())
        print(f"[ROI+cap] 545 <= P{CAP_545_PERC} (={cap545:.2f}) | final pixels={pix_final}")

# ====================== RATIO & TEMPERATURE (ratio<0) ======================
ratio_all = np.log(im525_f / im545_f)  # ln((525+1)/(545+1))
ratio = np.where(mask_final == 1, ratio_all, np.nan)

neg = (ratio < 0) & (~np.isnan(ratio))
if DO_IQR_TRIM and np.any(neg):
    vals = ratio[neg]
    q1, q3 = np.nanpercentile(vals, [25, 75])
    iqr = q3 - q1
    lo_iqr, hi_iqr = q1 - IQR_K*iqr, q3 + IQR_K*iqr
    keep = neg & (ratio >= lo_iqr) & (ratio <= hi_iqr)
else:
    keep = neg

x = (ratio - b) / k
temp = np.full_like(ratio, np.nan, dtype=np.float32)
vt = keep & np.isfinite(x) & (x != 0)
temp[vt] = 1000.0 / x[vt] - 273.15

# ====================== STATS ======================
def stats_block(arr):
    v = arr[np.isfinite(arr)]
    if v.size == 0: return (np.nan, np.nan, np.nan, np.nan)
    mean = float(np.nanmean(v)); std = float(np.nanstd(v))
    med  = float(np.nanmedian(v))
    q25, q75 = np.nanpercentile(v, [25, 75])
    iqr = float(q75 - q25)
    return mean, std, med, iqr

mr_mean, mr_std, mr_med, mr_iqr = stats_block(ratio[keep])
t_mean,  t_std,  t_med,  t_iqr  = stats_block(temp[vt])

print(f"[545->525] LoweGood(545)={m545}, Inliers(545)={inl545}")
print(f"Mean ln((525+1)/(545+1)) = {mr_mean:.4f} ± {mr_std:.4f} (median={mr_med:.4f}, IQR={mr_iqr:.4f})")
print(f"Mean Temperature (C)      = {t_mean:.2f} ± {t_std:.2f} (median={t_med:.2f}, IQR={t_iqr:.2f})")
print(f"Kept pixels (after IQR)   = {int(np.nansum(keep))}")

# ====================== SAVE VISUALS ======================
plt.figure(figsize=(6,6)); plt.imshow(mask_final, cmap='gray'); plt.axis('off'); plt.tight_layout()
plt.savefig(os.path.join(outdir, "mask_final.png"), dpi=300); plt.close()

plt.figure(figsize=(6,6))
plt.imshow(ratio, cmap='nipy_spectral')
plt.colorbar(label='ln((525+1)/(545+1))')
plt.title('Ratio in final ROI (symmetric IQR in stats)')
plt.axis('off'); plt.tight_layout()
plt.savefig(os.path.join(outdir, "ratio_ln525_545_in_final_roi.png"), dpi=300)
plt.close()

plt.figure(figsize=(6,6))
plt.imshow(temp, cmap='jet', vmin=TEMP_VMIN, vmax=TEMP_VMAX)
plt.colorbar(label='Temperature (°C)')
plt.title('Temperature in final ROI (symmetric IQR)')
plt.axis('off'); plt.tight_layout()
plt.savefig(os.path.join(outdir, "temperature_in_final_roi.png"), dpi=300)
plt.close()

# overlay on 488 gray
plt.figure(figsize=(6,6))
plt.imshow(cv2.normalize(im488_aln, None, 0, 255, cv2.NORM_MINMAX), cmap='gray')
plt.imshow(temp, cmap='jet', vmin=TEMP_VMIN, vmax=TEMP_VMAX, alpha=0.6)
plt.axis('off'); plt.tight_layout()
plt.savefig(os.path.join(outdir, "temperature_overlay_on_488.png"), dpi=300)
plt.close()

# ====================== SAVE MATRICES & SUMMARY ======================
tifffile.imwrite(os.path.join(outdir, "ratio_ln525_545_in_final_roi.tiff"), ratio.astype(np.float32))
tifffile.imwrite(os.path.join(outdir, "temperature_in_final_roi.tiff"),    temp.astype(np.float32))

with open(os.path.join(outdir, "summary_45C_repro.txt"), "w", encoding="utf-8") as f:
    f.write(
f"""Registration
------------
545 -> 525: LoweGood={m545}, Inliers(545)={inl545}
488 uses M545 (no ORB on 488)

ROI (local 525 min-max within 488)
----------------------------------
mask488 pixels         : {pix_mask488}
picked percentile (u8) : P{p_chosen}
tau_u8 value           : {tau_u8:.4f}
final pixels           : {int(np.nansum(mask_final))}
mm525(u8) in 488 ROI   : P10={q10:.2f}, P25={q25:.2f}, P50={q50:.2f}, P75={q75:.2f}, P90={q90:.2f}
erode radius           : {ERODE_R}
545 cap enabled        : {USE_545_CAP}
545 cap percentile     : {CAP_545_PERC if USE_545_CAP else 'N/A'}
BG_SUB                 : {DO_BG_SUB}

Calibration-consistent
----------------------
ratio def              : ln((I525+1)/(I545+1))
stats domain           : final ROI AND ratio < 0
IQR trimming           : {DO_IQR_TRIM} (K={IQR_K})
temperature            : T = 1000 / ((ratio - b)/k) - 273.15
k, b                   : {k:.6f}, {b:.6f}

Results
-------
mean ln ratio          : {mr_mean:.6f} ± {mr_std:.6f} (median={mr_med:.6f}, IQR={mr_iqr:.6f})
mean temperature (C)   : {t_mean:.2f} ± {t_std:.2f} (median={t_med:.2f}, IQR={t_iqr:.2f})
kept pixels (IQR)      : {int(np.nansum(keep))}
""")

print("Done:", outdir)
