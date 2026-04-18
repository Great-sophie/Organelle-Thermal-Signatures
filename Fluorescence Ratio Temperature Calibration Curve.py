import cv2
import matplotlib.pyplot as plt
import numpy as np
import glob
import os
from scipy import stats

# -----------------------
# 配置：修改为你的数据文件夹路径
# -----------------------
root_path = r"H:\Tirf imaging\Mito temperature\474\0808-474-Mito-3\cal"

# 匹配所有 “温度-525-组号.tif” 文件
imp = glob.glob(os.path.join(root_path, "*-525-*.tif"))

# 用于按温度分组存储所有 ratio 计算结果
data_by_temp = {}

for filepath in imp:
    print(f"Processing: {filepath}")
    base = os.path.basename(filepath)             # 例如 "30.0-525-1.tif"
    name_no_ext = os.path.splitext(base)[0]       # "30.0-525-1"
    parts = name_no_ext.split('-')                # ['30.0', '525', '1']
    # 检查是否符合 “温度-525-组号” 三段式命名
    if len(parts) != 3 or parts[1] != '525':
        print(f"跳过 非预期命名文件: {base}")
        continue

    # 解析温度和组号
    temp_str = parts[0]
    group_id = parts[2]
    try:
        temp_val = float(temp_str)  # 温度值
    except ValueError as e:
        print(f"文件名解析错误 {base}: {e}")
        continue

    # 读取 525 波段图像
    im525 = cv2.imread(filepath, -1)
    if im525 is None:
        print(f"加载失败: {base}")
        continue
    im525 = im525.astype(np.float32) + 1.0

    # 构造并读取对应的 545 波段图像（温度-545-组号.tif）
    fname545 = f"{temp_str}-545-{group_id}.tif"
    path545  = os.path.join(root_path, fname545)
    im545 = cv2.imread(path545, -1)
    if im545 is None:
        print(f"加载失败: {fname545}")
        continue
    im545 = im545.astype(np.float32) + 1.0

    # ----------------------------------------
    # 图像对齐 & 预处理（与原代码相同）
    # ----------------------------------------
    im525_gray = cv2.normalize(im525, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    im545_gray = cv2.normalize(im545, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    orb = cv2.ORB_create(nfeatures=50000)
    kp1, des1 = orb.detectAndCompute(im525_gray, None)
    kp2, des2 = orb.detectAndCompute(im545_gray, None)
    if des1 is None or des2 is None:
        print(f"特征检测失败: {base}")
        continue

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = bf.match(des1, des2)
    if len(matches) < 4:
        print(f"匹配点不足: {base}")
        continue
    matches = sorted(matches, key=lambda x: x.distance)[:50]

    src_pts = np.float32([kp1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
    M, inliers = cv2.estimateAffinePartial2D(dst_pts, src_pts, method=cv2.RANSAC)
    if M is None:
        print(f"估计变换失败: {base}")
        continue

    rows, cols = im525.shape
    im545_aligned = cv2.warpAffine(im545, M, (cols, rows), flags=cv2.INTER_LINEAR)

    # -------------------------------
    # 计算 ratio 图并取 mask 后的负值均值
    # -------------------------------
    ratio = np.log(im525 / im545_aligned)
    mask = (im525 - im525.min()) / (im525.max() - im525.min()) * 255
    mask = np.where(mask >80, 1, 0)
    ratio *= mask

    mean_value = np.mean(ratio[(ratio < 0) & (~np.isnan(ratio))])
    data_by_temp.setdefault(temp_val, []).append(mean_value)

# -------------------------------
# 计算每个温度的平均 ratio
# -------------------------------
averaged_data = {t: np.mean(v) for t, v in data_by_temp.items()}

print("\n每个温度的平均测量数据：")
for t in sorted(averaged_data):
    print(f"  温度 {t:.1f} ℃: 平均 ratio = {averaged_data[t]:.6f}")

# ===============================
# 拟合 & 绘图
# ===============================
temps_sorted = sorted(averaged_data.keys())
x_all = np.array([1000.0 / (T + 273.15) for T in temps_sorted])
y_all = np.array([averaged_data[T] for T in temps_sorted])

plt.figure(figsize=(4, 8))
plt.scatter(x_all, y_all, label='Averaged Data')
plt.xlabel('1000 / (T + 273.15)')
plt.ylabel('Mean log(525/545)')
plt.title('各温度下的平均 Ratio')
plt.legend()
plt.tight_layout()
plt.show()

# ---------------------------------
# 去除 NaN 并拟合
# ---------------------------------
valid = ~np.isnan(y_all)
x = x_all[valid]
y = y_all[valid]

print("\n剔除 NaN 后的数据点：")
for T, val in zip(np.array(temps_sorted)[valid], y):
    print(f"  温度 {T:.1f} ℃: {val:.6f}")

if len(x) > 1:
    slope, intercept, *_ = stats.linregress(x, y)
    intercept_fixed = np.mean(y) + np.mean(x)

    plt.figure(figsize=(4, 8))
    plt.scatter(x, y, label='Filtered Data')
    plt.plot(x, slope * x + intercept, label=f'Best Fit: y={slope:.2f}x+{intercept:.2f}')
    plt.plot(x, -1*x + intercept_fixed, label=f'Fixed Slope: y=-1*x+{intercept_fixed:.2f}')
    plt.xlabel('1000 / (T + 273.15)')
    plt.ylabel('Mean log(525/545)')
    plt.title('拟合对比')
    plt.legend()
    plt.tight_layout()
    plt.show()
else:
    print("剔除 NaN 后数据点不足，无法拟合。")
