"""Krea2 四视图（角色设定表）：把 ComfyUI 里新装的「▶四视图.json」画布工作流翻成 API 图。

来源工作流：
    D:\\Comfy-Desktop\\ComfyUI-Installs\\h3\\ComfyUI\\user\\default\\workflows\\▶四视图.json
（15 节点画布版；本文件节点编号与画布 node id 完全一致，方便对着画布排查）

链路（与画布逐节点一致）：
    25 UNETLoader(krea2_turbo_fp8_scaled)
      → 16 LoraLoaderModelOnly(Krea2-四视图QuadView_krea2_v1, strength=1)
      → 23 Krea2EditModelPatch(source_latent=20, vae=9, source_image=18,
                               ref_boost=1, ref_boost_a=1, fit_mode="fit")
    21 CLIPLoader(qwen3vl_4b, type=krea2)
      → 24 Krea2EditGroundedEncode(prompt=四视图指令, image=18, grounding_px=0)   正向
      → 22 Krea2EditGroundedEncode(prompt="",        image=18, grounding_px=768) 负向（CFG 也要接地）
    17 LoadImage(参考图) → 18 ImageResizeKJv2(1024×1536, lanczos, resize) → 20 VAEEncode
      → 7 EmptySD3LatentImage(1536×1024) ← 这是**输出**画布，与参考图预处理尺寸是两回事
    14 KSampler(euler / simple / steps=10 / cfg=1 / denoise=1)
      → 11 VAEDecode → 5 SaveImage

两个关键点（改了会明显影响结果，界面上要标出来）：
    1) 23 同时接了 vae + source_image，所以走的是 pixel path（fit_mode="fit"）：
       参考图按**目标分辨率**在像素空间重新 fit 再编码，因此 18 的预处理尺寸对成图影响很小，
       它主要决定「喂给模型的参考像素预算」。默认沿用画布原值 1024×1536。
    2) ref_boost 是"参考保真度"旋钮（乘到 target→reference attention）：
       1.0 = 关；>1 更贴参考（脸更像，但姿势/构图更死）；<1 更松。
"""

# ---- 固定模型（与画布工作流一致，不吃界面参数）--------------------------------
UNET = "krea2_turbo_fp8_scaled.safetensors"
CLIP = "qwen3vl_4b_fp8_scaled.safetensors"
CLIP_TYPE = "krea2"
VAE = "qwen_image_vae.safetensors"
LORA = "Krea2-四视图QuadView_krea2_v1.safetensors"

# ---- 默认值：全部取自画布工作流原值 -------------------------------------------
DEFAULT_W, DEFAULT_H = 1536, 1024      # 节点 7 EmptySD3LatentImage
DEFAULT_REF_W, DEFAULT_REF_H = 1024, 1536  # 节点 18 ImageResizeKJv2
DEFAULT_STEPS = 10                     # 节点 14
DEFAULT_CFG = 1.0
DEFAULT_SAMPLER = "euler"
DEFAULT_SCHEDULER = "simple"
DEFAULT_DENOISE = 1.0
DEFAULT_LORA = 1.0                     # 节点 16
DEFAULT_REF_BOOST = 1.0                # 节点 23
DEFAULT_REF_BOOST_A = 1.0
DEFAULT_FIT_MODE = "fit"
DEFAULT_GROUND_POS = 0                 # 节点 24 grounding_px（0 = 原生分辨率）
DEFAULT_GROUND_NEG = 768               # 节点 22 grounding_px

DEFAULT_PROMPT = (
    "Convert the character in the image to a Character Sheet showing a face close-up, "
    "front full body, side full body and back full body views"
)

SAMPLERS = ["euler", "euler_ancestral", "heun", "dpmpp_2m", "dpmpp_2m_sde", "dpmpp_sde",
            "res_multistep", "lcm", "ddim", "uni_pc"]
SCHEDULERS = ["simple", "normal", "sgm_uniform", "karras", "exponential", "beta", "ddim_uniform"]
FIT_MODES = ["fit", "crop (legacy)"]

# 画幅预设（宽, 高, 说明）。Krea2 走 8x 下采样，边长取 16 的倍数最稳。
PRESETS = [
    {"key": "3:2 横版", "w": 1536, "h": 1024, "note": "画布原值，四格并排最常用"},
    {"key": "2:3 竖版", "w": 1024, "h": 1536, "note": "四格上下叠"},
    {"key": "1:1 方图", "w": 1024, "h": 1024, "note": "2×2 田字格"},
    {"key": "16:9 宽屏", "w": 1536, "h": 864, "note": "更宽的多视角排布"},
    {"key": "9:16 竖屏", "w": 864, "h": 1536, "note": "手机竖屏画布"},
    {"key": "4:3", "w": 1280, "h": 960, "note": "偏方一点"},
    {"key": "2K 3:2", "w": 2048, "h": 1360, "note": "12GB 显存会慢，且可能 OOM"},
]


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _align(v, step=16):
    """对齐到 step 的倍数（Krea2 潜空间 8x，取 16 更保险）。"""
    return max(step, int(round(int(v) / float(step))) * step)


def build_graph(image: str,
                prompt: str = DEFAULT_PROMPT,
                width: int = DEFAULT_W,
                height: int = DEFAULT_H,
                ref_width: int = DEFAULT_REF_W,
                ref_height: int = DEFAULT_REF_H,
                steps: int = DEFAULT_STEPS,
                cfg: float = DEFAULT_CFG,
                sampler: str = DEFAULT_SAMPLER,
                scheduler: str = DEFAULT_SCHEDULER,
                denoise: float = DEFAULT_DENOISE,
                seed: int = 0,
                lora_strength: float = DEFAULT_LORA,
                ref_boost: float = DEFAULT_REF_BOOST,
                ref_boost_a: float = DEFAULT_REF_BOOST_A,
                fit_mode: str = DEFAULT_FIT_MODE,
                ground_pos: int = DEFAULT_GROUND_POS,
                ground_neg: int = DEFAULT_GROUND_NEG,
                system_prompt: str = "",
                prefix: str = "canvas/QuadView"):
    """返回可直接 POST 给 ComfyUI /prompt 的 API 图（dict）。节点号 = 画布 node id。"""
    if not image:
        raise ValueError("缺少参考图")

    # 空提示词会让模型失去版式约束（实测会退化成挤成一排的灰白双胞胎），回落默认句
    if not (prompt or "").strip():
        prompt = DEFAULT_PROMPT

    width, height = _align(width), _align(height)
    ref_width, ref_height = _align(ref_width), _align(ref_height)
    steps = int(clamp(int(steps), 1, 80))
    cfg = round(float(clamp(float(cfg), 0.0, 20.0)), 3)
    denoise = round(float(clamp(float(denoise), 0.0, 1.0)), 3)
    fit_mode = fit_mode if fit_mode in FIT_MODES else DEFAULT_FIT_MODE

    # 正向 encode：画布原值是「给了 prompt 且 grounding_px=0」
    pos = {"clip": ["21", 0], "image": ["18", 0], "prompt": prompt or "",
           "grounding_px": int(clamp(int(ground_pos), 0, 4096))}
    if system_prompt:
        pos["system_prompt"] = system_prompt

    return {
        # --- 模型链 ---
        "25": {"class_type": "UNETLoader",
               "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "16": {"class_type": "LoraLoaderModelOnly",
               "inputs": {"model": ["25", 0], "lora_name": LORA,
                          "strength_model": round(float(lora_strength), 3)}},
        # --- 文本/视觉编码 ---
        "21": {"class_type": "CLIPLoader",
               "inputs": {"clip_name": CLIP, "type": CLIP_TYPE, "device": "default"}},
        # --- 参考图与参考潜变量 ---
        "17": {"class_type": "LoadImage", "inputs": {"image": image, "upload": "image"}},
        "18": {"class_type": "ImageResizeKJv2",
               "inputs": {"image": ["17", 0], "width": ref_width, "height": ref_height,
                          "upscale_method": "lanczos", "keep_proportion": "resize",
                          "pad_color": "0, 0, 0", "crop_position": "center",
                          "divisible_by": 2, "device": "cpu"}},
        "9": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "20": {"class_type": "VAEEncode", "inputs": {"pixels": ["18", 0], "vae": ["9", 0]}},
        # --- 参考保真补丁（pixel path：vae + source_image 都接）---
        "23": {"class_type": "Krea2EditModelPatch",
               "inputs": {"model": ["16", 0], "source_latent": ["20", 0],
                          "vae": ["9", 0], "source_image": ["18", 0],
                          "ref_boost": round(float(ref_boost), 3),
                          "ref_boost_a": round(float(ref_boost_a), 3),
                          "fit_mode": fit_mode}},
        # --- 双接地编码：正向带指令，负向空指令但同样接地（CFG 训练口径）---
        "24": {"class_type": "Krea2EditGroundedEncode", "inputs": pos},
        "22": {"class_type": "Krea2EditGroundedEncode",
               "inputs": {"clip": ["21", 0], "image": ["18", 0], "prompt": "",
                          "grounding_px": int(clamp(int(ground_neg), 0, 4096))}},
        # --- 输出画布（与参考图预处理尺寸无关）---
        "7": {"class_type": "EmptySD3LatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        # --- 采样 ---
        "14": {"class_type": "KSampler",
               "inputs": {"model": ["23", 0], "positive": ["24", 0], "negative": ["22", 0],
                          "latent_image": ["7", 0], "seed": int(seed), "steps": steps,
                          "cfg": cfg, "sampler_name": sampler, "scheduler": scheduler,
                          "denoise": denoise}},
        "11": {"class_type": "VAEDecode", "inputs": {"samples": ["14", 0], "vae": ["9", 0]}},
        "5": {"class_type": "SaveImage", "inputs": {"images": ["11", 0],
                                                    "filename_prefix": prefix}},
    }


def describe(width, height, steps, cfg, ref_boost, lora_strength, prompt=""):
    """给前端/日志用的可读摘要。"""
    return {
        "width": _align(width),
        "height": _align(height),
        "megapixels": round(_align(width) * _align(height) / 1048576.0, 2),
        "steps": int(steps),
        "cfg": round(float(cfg), 3),
        "ref_boost": round(float(ref_boost), 3),
        "lora": round(float(lora_strength), 3),
        "prompt_chars": len(prompt or ""),
    }
