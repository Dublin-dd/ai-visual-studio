import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BACKEND_DIR / "data"))).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
GENERATED_DIR = DATA_DIR / "generated"
for _d in (DATA_DIR, UPLOAD_DIR, GENERATED_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# 图像生成服务
IMAGE_API_BASE_URL = os.getenv("IMAGE_API_BASE_URL", "https://api.siliconflow.cn/v1").rstrip("/")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "Tongyi-MAI/Z-Image-Turbo")
IMAGE_MODEL_HQ = os.getenv("IMAGE_MODEL_HQ", "Qwen/Qwen-Image")
IMAGE_MODEL_DRAFT = os.getenv("IMAGE_MODEL_DRAFT", "Tongyi-MAI/Z-Image-Turbo")
IMAGE_API_KEY = os.getenv("IMAGE_API_KEY", "")
IMAGE_TIMEOUT_SECONDS = float(os.getenv("IMAGE_TIMEOUT_SECONDS", "120"))
IMAGE_COST_PER_IMAGE = float(os.getenv("IMAGE_COST_PER_IMAGE", "0.3"))

# 图片编辑（图生图 / 抠图 / 多 SKU）
EDIT_MODEL = os.getenv("EDIT_MODEL", "Qwen/Qwen-Image-Edit-2509")
EDIT_TIMEOUT_SECONDS = float(os.getenv("EDIT_TIMEOUT_SECONDS", "300"))
CUTOUT_WHITE_THRESHOLD = int(os.getenv("CUTOUT_WHITE_THRESHOLD", "245"))
CUTOUT_FEATHER = int(os.getenv("CUTOUT_FEATHER", "10"))
MAX_SKU_VARIANTS = int(os.getenv("MAX_SKU_VARIANTS", "4"))

# 编辑前清理旧水印（避免多重水印重影；不删除平台新打的合规标识）
WATERMARK_CLEAN_ENABLED = os.getenv("WATERMARK_CLEAN_ENABLED", "1") != "0"
WATERMARK_X_RATIO = float(os.getenv("WATERMARK_X_RATIO", "0.74"))
WATERMARK_Y_RATIO = float(os.getenv("WATERMARK_Y_RATIO", "0.90"))
WATERMARK_MAX_STDDEV = float(os.getenv("WATERMARK_MAX_STDDEV", "12.0"))

# 文本模型（分镜脚本）：沿用 SiliconFlow 同一把 Key
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V3.2")
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
LLM_COST_PER_CALL = float(os.getenv("LLM_COST_PER_CALL", "0.02"))
MAX_SHOTS = int(os.getenv("MAX_SHOTS", "30"))

# 视频生成（SiliconFlow Wan2.2，异步任务：submit + status 轮询）
VIDEO_MODEL_I2V = os.getenv("VIDEO_MODEL_I2V", "Wan-AI/Wan2.2-I2V-A14B")
VIDEO_MODEL_T2V = os.getenv("VIDEO_MODEL_T2V", "Wan-AI/Wan2.2-T2V-A14B")
VIDEO_POLL_INTERVAL = float(os.getenv("VIDEO_POLL_INTERVAL", "5"))
VIDEO_MAX_WAIT_SECONDS = float(os.getenv("VIDEO_MAX_WAIT_SECONDS", "900"))
VIDEO_TIMEOUT_SECONDS = float(os.getenv("VIDEO_TIMEOUT_SECONDS", "120"))
VIDEO_STATUS_TIMEOUT_SECONDS = float(os.getenv("VIDEO_STATUS_TIMEOUT_SECONDS", "60"))
VIDEO_COST_PER_CLIP = float(os.getenv("VIDEO_COST_PER_CLIP", "1.0"))
MAX_VIDEOS_PER_BATCH = int(os.getenv("MAX_VIDEOS_PER_BATCH", "20"))
VIDEO_DIR = DATA_DIR / "videos"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

# 语音合成（TTS）：沿用 SiliconFlow 同一把 Key
TTS_MODEL = os.getenv("TTS_MODEL", "FunAudioLLM/CosyVoice2-0.5B")
TTS_VOICE = os.getenv("TTS_VOICE", "FunAudioLLM/CosyVoice2-0.5B:alex")
TTS_TIMEOUT_SECONDS = float(os.getenv("TTS_TIMEOUT_SECONDS", "120"))
TTS_COST_PER_CALL = float(os.getenv("TTS_COST_PER_CALL", "0.01"))
TTS_SPEED = float(os.getenv("TTS_SPEED", "1.0"))
AUDIO_DIR = DATA_DIR / "audio"
BGM_DIR = DATA_DIR / "bgm"
FINAL_DIR = DATA_DIR / "final"
for _d in (AUDIO_DIR, BGM_DIR, FINAL_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# 成片合成
FFMPEG_BIN = os.getenv("FFMPEG_BIN", "")
BGM_DEFAULT_VOLUME = float(os.getenv("BGM_DEFAULT_VOLUME", "0.25"))
SUBTITLE_FONT = os.getenv("SUBTITLE_FONT", "PingFang SC")
SUBTITLE_FONT_SIZE = int(os.getenv("SUBTITLE_FONT_SIZE", "46"))
MAX_BGM_BYTES = int(os.getenv("MAX_BGM_BYTES", str(20 * 1024 * 1024)))

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'app.db'}")

# 成本护栏
DAILY_TASK_LIMIT = int(os.getenv("DAILY_TASK_LIMIT", "200"))
MAX_IMAGES_PER_TASK = int(os.getenv("MAX_IMAGES_PER_TASK", "4"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
ALLOWED_UPLOAD_MIME = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_UPLOAD_FORMAT = {"JPEG", "PNG", "WEBP"}

# 图像处理
EXPORT_DIR = DATA_DIR / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_SCALE = int(os.getenv("EXPORT_SCALE", "2"))
BOARD_WIDTH = int(os.getenv("BOARD_WIDTH", "1000"))
BOARD_HEIGHT = int(os.getenv("BOARD_HEIGHT", "720"))
MAX_LAYERS_PER_PROJECT = int(os.getenv("MAX_LAYERS_PER_PROJECT", "200"))

# 本阶段固定归属，为上线登录预留（手册第九节第 2 条）
DEFAULT_OWNER_ID = os.getenv("DEFAULT_OWNER_ID", "local-user")

# 任务 worker：过渡档单实例、单 worker 串行
WORKER_ENABLED = os.getenv("WORKER_ENABLED", "1") != "0"
WORKER_POLL_SECONDS = float(os.getenv("WORKER_POLL_SECONDS", "1.0"))
