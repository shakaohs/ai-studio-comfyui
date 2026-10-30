# AI Studio（Infinite-Canvas）Zeabur 部署包

版本：`2026.08.28`　打包时间：2026-10-30
本目录是**可直接部署的独立工程**，已剔除本地素材（1.7 GB 生成图）、内置 Python 运行时（75 MB）、
`.bak` 备份文件与历史记录，仅保留运行所需代码与静态页面。

---

## 1. 包里有什么

| 路径 | 作用 | 说明 |
|---|---|---|
| `main.py` | 应用主体（FastAPI，约 930 KB） | 未做任何业务改动 |
| `server.py` | **容器启动入口** | 读取 `PORT`；可选 HTTP Basic 访问保护 |
| `entrypoint.sh` | 启动脚本 | 建目录、首次挂卷回填种子、history 落盘 |
| `static/` | 全部前端页面（17 个 html） | 已剔除 `.bak` 版本 |
| `workflows/` | ComfyUI 工作流 JSON | 构图/出图依赖这些模板 |
| `data/` | 空资产库 + 提示词库 + 项目表 | 干净的初始状态 |
| `_h3_video.py` / `_krea_quad.py` | H3 视频、四视图工作流构造器 | 纯 JSON 构造，无重依赖 |
| `_faithful_enhance.py` | 保真增强（解析式锐化） | 需 opencv，已在依赖内 |
| `Dockerfile` | `python:3.10-slim` + ffmpeg | 与本机 3.10.11 对齐 |
| `requirements.txt` | 依赖清单 | 版本与本机开发环境一致 |

---

## 2. 部署前必须知道的一件事

这个应用原本是**本机工作台**：出图走本地 ComfyUI（`127.0.0.1:8188`），部分能力调用本机 CLI
（即梦 `dreamina`、Codex、Gemini CLI）。Zeabur 上没有 GPU、没有这些 CLI。

**结论：网页界面、画布、素材库、提示词库、API 供应商管理、保真增强可正常使用；
真正的出图/出视频必须接云端供应商**（在 `设置 → API 供应商` 里配置 RunningHub / 火山方舟 /
APIMart / OpenAI 兼容接口，这几类都是纯 HTTP 调用，云端可用）。

| 能力 | Zeabur 上是否可用 | 条件 |
|---|---|---|
| 页面、画布、素材库、提示词库 | ✅ | 无 |
| 保真增强（解析式） | ✅ | 依赖已装 |
| RunningHub / 火山 / APIMart / OpenAI 兼容 出图 | ✅ | 在界面填 API Key |
| 本地 ComfyUI 出图/出视频 | ⚠️ | 需把 `COMFYUI_INSTANCES` 指向一台公网可达的 ComfyUI |
| 即梦 CLI / Codex CLI / Gemini CLI 供应商 | ❌ | 需要本机 CLI 与登录态，云端无法提供 |
| 视频抽帧、封面合成 | ✅ | 镜像内已装 ffmpeg |

---

## 3. 部署步骤（GitHub 方式，推荐）

```bash
# 1) 在本目录初始化仓库
cd AIStudio-Zeabur
git init
git add .
git commit -m "AI Studio deploy bundle"

# 2) 推到你的 GitHub 私有仓库（示例）
git remote add origin https://github.com/<你的账号>/ai-studio.git
git branch -M main
git push -u origin main
```

然后到 Zeabur 控制台：

1. **Create Project → Deploy New Service → GitHub**，选中该仓库。
2. 构建方式会自动识别为 **Dockerfile**，无需手动填写启动命令。
3. **Networking**：为该服务 `Generate Domain`，容器端口填 `3000`（`server.py` 会同时兼容平台注入的 `PORT`）。
4. **Volumes**：挂两个卷，否则每次重新部署都会丢数据：
   - 挂载路径 `/app/assets`（生成图、素材库文件，会持续增长，建议 ≥ 5 GB）
   - 挂载路径 `/app/data`（画布、会话、资产库索引、history）
5. **Variables**：按下面第 4 节填写。

> 如果暂时不想上 GitHub，也可以在本地装 Zeabur CLI（`npm i -g zeabur`）后在该目录执行
> `zeabur deploy`，具体参数以 Zeabur 官方文档为准。

---

## 4. 环境变量

| 变量 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `AISTUDIO_USER` | 建议 | 空 | 访问保护用户名 |
| `AISTUDIO_PASS` | 建议 | 空 | 访问保护密码；**两者同时填写才生效** |
| `TZ` | 建议 | Asia/Shanghai | 时间显示 |
| `COMFYUI_INSTANCES` | 按需 | `127.0.0.1:8188` | 公网 ComfyUI 地址，多台用逗号分隔 |
| `COMFY_INPUT_DIR` | 按需 | 本地 D 盘路径 | 仅本地 ComfyUI 模式使用 |
| `COMFY_VENV_PYTHON` | 按需 | 本地 venv 路径 | 指向带 cv2 的 Python |
| `FAITHFUL_ENHANCE_PYTHON` | 按需 | 同上 | 保真增强用的解释器；容器内可直接填 `python` |
| `COMFYUI_HISTORY_TIMEOUT` | 否 | 1800 | 长任务轮询上限（秒） |

**安全提醒（重要）**：本项目**没有内置登录体系**。一旦生成公网域名，任何人都能打开并消耗你的 API 额度。
务必设置 `AISTUDIO_USER` / `AISTUDIO_PASS`，或只在本地/内网访问。

---

## 5. 本地验证（可选）

本机有 Python 3.10 时可直接跑一遍，确认包没问题：

```bash
cd AIStudio-Zeabur
PORT=3000 python server.py
# 打开 http://127.0.0.1:3000/
```

---

## 6. 已知限制与排查

- **首次启动慢**：`startup_event` 会整理资产库（对空库很快，导入上千张图时首次会慢几十秒）。
- **素材体积**：`/app/assets` 会随出图持续增长，建议给卷留足空间，并定期在「素材管理」里清理。
- **出图 502 / 一直排队**：先看 `COMFYUI_INSTANCES` 是否可达；用云端供应商时检查 Key 与额度。
- **依赖装不上**：若某个 `==` 版本在 Linux 上没有 wheel，把该行改成 `>=` 重新部署。
- **更新代码**：改动 `main.py` 后重新 push，Zeabur 会自动重建；`data` / `assets` 在卷上，不受影响。

---

## 7. 从本机到云端的差异清单

| 本机（Windows 工作台） | Zeabur 容器 |
|---|---|
| `D:\Infinite-Canvas` 绝对路径 | `/app`，代码用 `BASE_DIR` 自适应，无需改路径 |
| 内置 `python\python.exe` | 镜像内 `python3.10` |
| ComfyUI 桌面版 + GPU | 无；需远端 ComfyUI 或云 API |
| 即梦/Codex/Gemini CLI | 无；相关供应商入口会报"未找到 CLI" |
| `D:\AI-Work\交付成品` 等本地交付目录 | 不适用；产物落在 `/app/assets/output`（已挂卷） |
