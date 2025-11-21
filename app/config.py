"""
프로젝트 설정 파일
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# 프로젝트 루트 디렉토리
PROJECT_ROOT = Path(__file__).parent.parent

# 데이터 디렉토리
DATA_DIR = PROJECT_ROOT / "data"
INPUT_DIR = DATA_DIR / "input"
TEMP_DIR = DATA_DIR / "temp"
OUTPUT_DIR = DATA_DIR / "output"
META_DIR = DATA_DIR / "meta"

# 임시 파일 디렉토리
SLIDES_IMG_DIR = TEMP_DIR / "slides_img"
AUDIO_DIR = TEMP_DIR / "audio"
OVERLAY_DIR = TEMP_DIR / "overlay"
CLIPS_DIR = TEMP_DIR / "clips"

# API 설정
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# LLM 설정
DEFAULT_LLM_MODEL = "claude-3-5-sonnet-20241022"  # 또는 "claude-3-5-sonnet-latest"
LLM_TEMPERATURE = 0.7
LLM_MAX_TOKENS = 4096

# TTS 설정
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "openai")  # "openai" or "elevenlabs"
TTS_VOICE = os.getenv("TTS_VOICE", "alloy")  # OpenAI TTS voice
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

# 비디오 설정
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30
VIDEO_CODEC = "libx264"
AUDIO_CODEC = "aac"

# FFmpeg 설정
FFMPEG_PRESET = "medium"  # ultrafast, fast, medium, slow
FFMPEG_CRF = 23  # 품질 설정 (0-51, 낮을수록 고품질)

# 디버그 모드
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
