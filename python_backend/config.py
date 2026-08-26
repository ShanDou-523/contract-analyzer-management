"""Application configuration."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
    USER_DATA_DIR = Path(os.getenv("APPDATA", os.path.expanduser("~"))) / "ContractAnalyzer"
else:
    BASE_DIR = Path(__file__).parent
    USER_DATA_DIR = BASE_DIR

USER_DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR = USER_DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
DB_PATH = USER_DATA_DIR / "contract_analyzer.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

SERVER_HOST = "127.0.0.1"
SERVER_PORT = int(os.getenv("CONTRACT_ANALYZER_PORT", "5768"))

OCR_DPI = 300
OCR_CONFIDENCE_THRESHOLD = 0.5
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_PDF_PAGES = 200

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_TIMEOUT_SECONDS = 120
DEEPSEEK_TEMPERATURE = 0.3
