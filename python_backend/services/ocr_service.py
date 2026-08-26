"""Baidu OCR API service for PDF text extraction."""

import io
import os
import base64
from typing import Optional

import fitz
import requests
from PIL import Image

from config import UPLOAD_DIR, OCR_DPI, MAX_PDF_PAGES

BAIDU_TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
BAIDU_OCR_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic"


def _get_baidu_keys():
    """Get Baidu OCR keys from DB, fallback to env."""
    from database import SessionLocal
    from services.secret_service import get_secret_setting

    db = SessionLocal()
    try:
        ak = get_secret_setting(db, "baidu_ocr_api_key") or os.getenv("BAIDU_OCR_API_KEY", "")
        sk = get_secret_setting(db, "baidu_ocr_secret_key") or os.getenv("BAIDU_OCR_SECRET_KEY", "")
        return ak, sk
    finally:
        db.close()


class OcrService:
    """OCR service using Baidu OCR REST API."""

    def __init__(self):
        self._token = None

    def _get_token(self) -> str:
        if self._token is None:
            ak, sk = _get_baidu_keys()
            if not ak or not sk:
                raise RuntimeError("未配置百度OCR凭据，请在设置中配置 API Key 和 Secret Key")
            params = {
                "grant_type": "client_credentials",
                "client_id": ak,
                "client_secret": sk,
            }
            resp = requests.get(BAIDU_TOKEN_URL, params=params, timeout=10)
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"获取百度OCR令牌失败: {data.get('error_description', data)}")
            self._token = data["access_token"]
        return self._token

    def _image_to_text(self, img: Image.Image) -> list[dict]:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        token = self._get_token()
        url = f"{BAIDU_OCR_URL}?access_token={token}"
        result = requests.post(
            url,
            data={"image": img_base64, "language_type": "CHN_ENG"},
            timeout=30,
        ).json()

        if "error_code" in result:
            self._token = None
            token = self._get_token()
            url = f"{BAIDU_OCR_URL}?access_token={token}"
            result = requests.post(
                url,
                data={"image": img_base64, "language_type": "CHN_ENG"},
                timeout=30,
            ).json()
        if "error_code" in result:
            raise RuntimeError(
                f"百度OCR API错误 ({result.get('error_code')}): {result.get('error_msg')}"
            )
        return [
            {"text": item.get("words", ""), "confidence": 1.0}
            for item in result.get("words_result", [])
        ]

    def extract_text_from_pdf(self, stored_filename: str) -> dict:
        pdf_path = UPLOAD_DIR / stored_filename
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")

        try:
            doc = fitz.open(str(pdf_path))
        except Exception as e:
            raise RuntimeError(f"PDF文件打开失败（文件可能已损坏或加密）: {str(e)}")

        page_count = len(doc)
        if page_count > MAX_PDF_PAGES:
            doc.close()
            raise RuntimeError(f"PDF页数({page_count})超过上限({MAX_PDF_PAGES})")

        pages_detail = []
        all_text_lines = []
        try:
            for page_num in range(page_count):
                page = doc[page_num]
                zoom = OCR_DPI / 72.0
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                page_lines = self._image_to_text(img)
                for line in page_lines:
                    all_text_lines.append(line["text"])
                pages_detail.append(
                    {
                        "page": page_num + 1,
                        "text": "\n".join([line["text"] for line in page_lines]),
                        "line_count": len(page_lines),
                        "avg_confidence": 1.0,
                        "lines": page_lines,
                    }
                )
        finally:
            doc.close()

        return {
            "full_text": "\n".join(all_text_lines),
            "page_count": page_count,
            "pages": pages_detail,
        }


_ocr_service: Optional[OcrService] = None


def get_ocr_service() -> OcrService:
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = OcrService()
    return _ocr_service
