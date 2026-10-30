"""MiniMax H3 参考生视频：把 ComfyUI 里那张「MiniMax H3 」画布工作流翻成 API 图。

来源工作流：D:\\Comfy-Desktop\\ComfyUI-Installs\\h3\\ComfyUI\\user\\default\\workflows\\MiniMax H3 .json
（100 节点画布版，靠 Set/Get 串线；这里把 Set/Get 全部解开，只保留真正参与运算的节点）

链路（与画布一致）：
    UNETLoader(b25-49)
      → LoRA dmad 0.8 → LoRA MysticXXX 0.35
      → ModelAttentionBackend(comfy kitchen attention)
      → BlockSparseAttention(sol-attn, tau=1.3, 0.2~1.0, min_tokens=12288)
      → MiniMaxH3SigmaShift(shift_video=12, shift_audio=3)
      → MiniMaxChunkFeedForward(chunks=2, seq_threshold=4096)
      → ModelPreviewOverrideKJ(预览，可关)
      → BasicScheduler(simple, steps=总步数) / SelfLiftH3Sampler

    CLIPLoader(qwen3vl 32B ultra) + VAELoader(视频/音频)
      → MiniMaxH3ReferenceToVideo(参考图 N 张 + 提示词 + 宽高 + 帧数)
      → positive → SelfLift；ConditioningZeroOut → negative
      → SelfLiftH3Sampler 出 AV latent → VAEDecode(视频) / VAEDecodeAudio(音频)
      → VHS_VideoCombine(24fps, h264-mp4)

一采 / 二采：
    BasicScheduler.steps 是**总步数**（NFE）。
    SelfLiftH3Sampler.transition_step 是其中**低分辨率阶段**的步数（一采）。
    于是 二采（高分辨率阶段）= steps - transition_step。
    用户画布里是 12 总步 / 8 一采 → 二采 4 步。
"""

import math

# ---- 固定模型（与画布工作流一致，不吃界面参数）--------------------------------
UNET = "minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors"
CLIP = "qwen3vl_32b_minimax_h3_ultra_uncensored_heretic_int8_convrot.safetensors"
VAE_VIDEO = "minimax_h3_video_vae_int8_convrot.safetensors"
VAE_AUDIO = "minimax_h3_audio_vae_fp32.safetensors"
LORA_DMAD = "minimax_h3_dmad_full_dareties_v4_step600_comfy_fro.safetensors"
LORA_MYSTIC = "MysticXXX_MMH3-V1.safetensors"
TINY_VAE = "taeh3.safetensors"

FPS = 24
MAX_REFS = 9                 # H3 节点支持 9 张参考图
LEN_STEP = 17                # 帧数必须 5 + 17k（124 / 141 / … / 345 / 362）
LEN_MIN, LEN_MAX = 124, 362  # 官方 tooltip 的训练区间（≈5.2s ~ 15.1s）
DEFAULT_DURATION = 14
DEFAULT_ASPECT = "9:16 (Portrait Widescreen)"

ASPECTS = [
    "1:1 (Square)",
    "2:3 (Portrait Photo)",
    "3:2 (Photo)",
    "3:4 (Portrait Standard)",
    "4:3 (Standard)",
    "9:16 (Portrait Widescreen)",
    "16:9 (Widescreen)",
    "21:9 (Ultrawide)",
]
UPSCALERS = ["h3_upscaler_lms_v0.1.safetensors", "1h3_upscaler_lms_v0.1_fp32.safetensors"]


def length_for(seconds: float) -> int:
    """秒 → H3 帧数。必须是 5 + 17k，否则 H3 节点会拒绝/表现异常。"""
    n = max(1, int(round(float(seconds) * FPS)))
    n += (5 - n % LEN_STEP) % LEN_STEP
    return max(5, n)


def duration_of(length: int) -> float:
    return round(int(length) / FPS, 3)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def build_graph(prompt: str,
                refs=None,
                duration: float = DEFAULT_DURATION,
                aspect: str = DEFAULT_ASPECT,
                megapixels: float = 1.0,
                multiple: int = 32,
                steps: int = 12,
                first_steps: int = 8,
                lowres_scale: float = 0.6,
                cfg: float = 1.0,
                seed: int = 0,
                lora_dmad: float = 0.8,
                lora_mystic: float = 0.35,
                tiling: bool = False,
                upscaler: str = UPSCALERS[0],
                fps: int = FPS,
                crf: int = 19,
                preview: bool = True,
                prefix: str = "canvas/H3_"):
    """返回可直接 POST 给 ComfyUI /prompt 的 API 图（dict）。"""
    refs = [r for r in (refs or []) if r][:MAX_REFS]

    steps = int(clamp(int(steps), 2, 100))
    first_steps = int(clamp(int(first_steps), 1, steps))
    second_steps = steps - first_steps

    length = length_for(duration)

    g = {
        "192": {"class_type": "UNETLoader",
                "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "53": {"class_type": "LoraLoaderModelOnly",
               "inputs": {"model": ["192", 0], "lora_name": LORA_DMAD,
                          "strength_model": round(float(lora_dmad), 3)}},
        "400": {"class_type": "LoraLoaderModelOnly",
                "inputs": {"model": ["53", 0], "lora_name": LORA_MYSTIC,
                           "strength_model": round(float(lora_mystic), 3)}},
        "331": {"class_type": "ModelAttentionBackend",
                "inputs": {"model": ["400", 0], "attention": "comfy kitchen attention"}},
        "332": {"class_type": "BlockSparseAttention",
                "inputs": {"model": ["331", 0], "selection": "sol-attn",
                           "selection.tau": 1.3, "start_percent": 0.2, "end_percent": 1.0,
                           "dense_blocks": "", "min_tokens": 12288, "extra_tokens": 256,
                           "sink_conditioning": "exact_kv_and_rows", "verbose": False}},
        "333": {"class_type": "MiniMaxH3SigmaShift",
                "inputs": {"model": ["332", 0], "shift_video": 12.0, "shift_audio": 3.0}},
        "401": {"class_type": "MiniMaxChunkFeedForward",
                "inputs": {"model": ["333", 0], "chunks": 2, "seq_threshold": 4096}},
        "36": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_VIDEO}},
        "37": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_AUDIO}},
        "38": {"class_type": "CLIPLoader",
               "inputs": {"clip_name": CLIP, "type": "minimax", "device": "default"}},
        "255": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "261": {"class_type": "BasicScheduler",
                "inputs": {"model": ["329", 0], "scheduler": "simple",
                           "steps": steps, "denoise": 1.0}},
        "252": {"class_type": "ResolutionSelector",
                "inputs": {"aspect_ratio": aspect,
                           "megapixels": round(float(megapixels), 3),
                           "multiple": int(clamp(int(multiple), 8, 128))}},
    }

    # 预览节点只影响采样时的实时画面，不影响成品；关掉可少一次 taeh3 解码
    model_out = ["401", 0]
    if preview:
        g["329"] = {"class_type": "ModelPreviewOverrideKJ",
                    "inputs": {"model": ["401", 0], "vae": ["36", 0],
                               "max_resolution": 1024, "jpeg_quality": 80,
                               "suppress_default_preview": True,
                               "preview_frames": 1, "preview_fps": 12,
                               "tiny_vae": TINY_VAE, "preview": ""}}
        model_out = ["329", 0]

    # BasicScheduler 的 model 只是取采样签名，必须跟着预览开关走（否则关预览时连到不存在的 329）
    g["261"]["inputs"]["model"] = model_out

    # 参考图：每张一个 LoadImage，槽位号从 851 起，接 ref_images.ref_image_N
    ref_inputs = {}
    for i, name in enumerate(refs):
        nid = str(851 + i)
        g[nid] = {"class_type": "LoadImage", "inputs": {"image": name, "upload": "image"}}
        ref_inputs["ref_images.ref_image_%d" % i] = [nid, 0]

    h3 = {
        "clip": ["38", 0],
        "vae": ["36", 0],
        "audio_vae": ["37", 0],
        "prompt": prompt or "",
        "width": ["252", 0],
        "height": ["252", 1],
        "length": length,
        "ref_image_size": "match",
    }
    h3.update(ref_inputs)
    g["265"] = {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": h3}
    g["328"] = {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["265", 0]}}
    g["397"] = {"class_type": "SelfLiftH3Sampler",
                "inputs": {"model": model_out, "positive": ["265", 0], "negative": ["328", 0],
                           "vae": ["36", 0], "latent_image": ["265", 1],
                           "sampler": ["255", 0], "sigmas": ["261", 0],
                           "seed": int(seed), "cfg": round(float(cfg), 3),
                           "transition_step": first_steps,
                           "lowres_scale": round(float(lowres_scale), 3),
                           "rho": 0.0, "w_min": 0.5, "w_max": 1.0,
                           "upscaler_model": upscaler,
                           "highres_tiling": bool(tiling),
                           "upscaler_unload": True}}
    g["253"] = {"class_type": "VAEDecode",
                "inputs": {"samples": ["397", 0], "vae": ["36", 0]}}
    g["254"] = {"class_type": "VAEDecodeAudio",
                "inputs": {"samples": ["397", 0], "vae": ["37", 0]}}
    g["364"] = {"class_type": "VHS_VideoCombine",
                "inputs": {"images": ["253", 0], "audio": ["254", 0],
                           "frame_rate": int(fps), "loop_count": 0,
                           "filename_prefix": prefix,
                           "format": "video/h264-mp4", "pingpong": False,
                           "save_output": True, "pix_fmt": "yuv420p",
                           "crf": int(crf), "save_metadata": True,
                           "trim_to_audio": False}}
    return g


def describe(duration, steps, first_steps, megapixels, aspect):
    """给前端/日志用的可读摘要。"""
    length = length_for(duration)
    return {
        "length": length,
        "seconds": duration_of(length),
        "steps": int(steps),
        "first_steps": int(first_steps),
        "second_steps": int(steps) - int(first_steps),
        "megapixels": megapixels,
        "aspect": aspect,
    }
