"""保真增强（不走生成式模型）。

设计目标：只做「解析式」的清晰度提升，不做任何重绘。
- 不做扩散/超分模型的重新合成，因此不会磨皮、不会改脸、不会换风格；
- 皱纹、褶皱、毛孔、发丝全部沿用原图像素，只提升其局部对比；
- 放大只做重采样 + 细节重建，不生成新内容。

人像友好（2026-10-29 起）：
- 最细尺度（σ=0.9）权重下调，主力转到 σ=2 的中尺度——结构更清楚、砂砾感更少；
- 皮肤区细节按 skin_protect 打折（默认 0.55），脸不会比头发/衣服更硬；
- 默认强度定为 detail 0.20 / clarity 0.04（2026-10-29 15:47 用户从四档对比中亲自选定），
  比 0.30/0.06 再柔一档，仍是解析式提升、不磨皮。

用法：
  python _faithful_enhance.py --in A.png --out B.png --detail 0.2 --clarity 0.04 [--skin-protect 0.55] [--short-edge 4096]
"""
import argparse
import os

import cv2
import numpy as np


def imread_unicode(path, flags=cv2.IMREAD_COLOR):
    data = np.fromfile(path, dtype=np.uint8)
    if data.size == 0:
        raise SystemExit("读不到文件：%s" % path)
    img = cv2.imdecode(data, flags)
    if img is None:
        raise SystemExit("不是有效图片：%s" % path)
    return img


def imwrite_unicode(path, img):
    ext = os.path.splitext(path)[1] or ".png"
    ok, buf = cv2.imencode(ext, img)
    if not ok:
        raise SystemExit("编码失败：%s" % path)
    buf.tofile(path)


def resize_short_edge(img, short_edge):
    h, w = img.shape[:2]
    cur = min(h, w)
    if short_edge <= 0 or cur == short_edge:
        return img, 1.0
    scale = short_edge / float(cur)
    interp = cv2.INTER_LANCZOS4 if scale > 1 else cv2.INTER_AREA
    return cv2.resize(img, (max(1, int(round(w * scale))), max(1, int(round(h * scale)))), interpolation=interp), scale


def detail_bands(f, sigmas):
    """多尺度细节层：细节 = 图像 - 高斯模糊，逐尺度累加。"""
    acc = np.zeros_like(f)
    for sigma, weight in sigmas:
        acc += (f - cv2.GaussianBlur(f, (0, 0), sigma)) * weight
    return acc


def skin_weight(img):
    """皮肤区权重图（0-1，羽化）：YCrCb 肤色范围 + 形态学清理 + 高斯羽化。

    只用于把细节提升在皮肤上打折，避免人脸比头发/衣料更“硬”；
    羽化半径给足，胡子/头发边界不会出现一条明显的软硬分界。
    """
    ycc = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
    cr, cb = ycc[:, :, 1], ycc[:, :, 2]
    m = ((cr > 133) & (cr < 180) & (cb > 72) & (cb < 132)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    m = cv2.GaussianBlur(m, (0, 0), 7)
    return (m.astype(np.float32) / 255.0)[:, :, None]


def faithful_enhance(img, detail=0.20, clarity=0.04, edge_protect=0.10,
                     highlight_protect=0.75, skin_protect=0.55):
    f = img.astype(np.float32) / 255.0

    # 1) 多尺度细节提升（主力在中尺度，最细粒度刻意压住 → 少砂砾感）
    d = detail_bands(f, [(0.9, 0.80), (2.0, 0.75), (4.0, 0.35)])

    # 2) 边缘保护：强边不额外叠加，避免白边/光晕（光晕是“油腻感”的主要来源之一）
    hp1 = f - cv2.GaussianBlur(f, (0, 0), 0.9)
    mag = np.abs(hp1).max(axis=2, keepdims=True)
    prot = 1.0 / (1.0 + (mag / max(1e-4, edge_protect)) ** 2)

    # 3) 高光保护：接近死白的区域不再加强，避免皮肤发亮发油
    hi = np.clip((f.max(axis=2, keepdims=True) - 0.80) / 0.20, 0.0, 1.0)
    gain = prot * (1.0 - highlight_protect * hi)

    # 3.5) 皮肤区打折：人像的“锐化感”九成来自皮肤被加硬
    sp = max(0.0, min(1.0, float(skin_protect)))
    if sp < 1.0:
        gain = gain * (1.0 - (1.0 - sp) * skin_weight(img))

    f = f + d * float(detail) * gain

    # 4) 局部对比（中低频），让骨相、衣料起伏更立体；强度刻意压低，避免脏灰
    if clarity > 0:
        low = cv2.GaussianBlur(f, (0, 0), 14)
        f = f + (f - low) * float(clarity) * 0.45

    return np.clip(f * 255.0, 0, 255).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", dest="dst", required=True)
    ap.add_argument("--detail", type=float, default=0.20, help="细节强度 0-2")
    ap.add_argument("--clarity", type=float, default=0.04, help="局部对比 0-1")
    ap.add_argument("--skin-protect", dest="skin_protect", type=float, default=0.55,
                    help="皮肤区细节保留比例 0-1，1=不区分皮肤")
    ap.add_argument("--short-edge", type=int, default=0, help="输出短边像素，0=保持原尺寸")
    args = ap.parse_args()

    src = args.src.replace("/", os.sep)
    img = imread_unicode(src)
    h0, w0 = img.shape[:2]

    out, scale = resize_short_edge(img, args.short_edge)
    out = faithful_enhance(out, detail=args.detail, clarity=args.clarity,
                           skin_protect=args.skin_protect)

    os.makedirs(os.path.dirname(args.dst.replace("/", os.sep)) or ".", exist_ok=True)
    imwrite_unicode(args.dst.replace("/", os.sep), out)
    print("OK %dx%d -> %dx%d scale=%.3f" % (w0, h0, out.shape[1], out.shape[0], scale))


if __name__ == "__main__":
    main()
