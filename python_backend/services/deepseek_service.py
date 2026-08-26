"""DeepSeek API service for contract analysis."""

import json
import os
import re
from pathlib import Path
from typing import Optional

from openai import OpenAI

from config import (
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    DEEPSEEK_TIMEOUT_SECONDS,
    DEEPSEEK_TEMPERATURE,
)
from services.analysis_template_service import decode_fields


def _get_deepseek_key() -> str:
    """Get DeepSeek API key from DB first, fallback to env."""
    from database import SessionLocal
    from models.document import Setting

    db = SessionLocal()
    try:
        key = Setting.get(db, "deepseek_api_key") or os.getenv("DEEPSEEK_API_KEY", "")
        return key
    finally:
        db.close()


PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
PROMPT_REASONABILITY_CHECK = "reasonability_check.txt"


def _load_prompt(filename: str) -> str:
    """Load a system prompt from file."""
    prompt_path = PROMPTS_DIR / filename
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8").strip()
    fallbacks = {
        PROMPT_REASONABILITY_CHECK: "合同中的内容和数字是否存在不合理之处",
    }
    return fallbacks.get(filename, "")


def _parse_json_object(text: str) -> dict:
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text or "")
    candidate = (fenced.group(1) if fenced else text or "").strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError("AI返回内容不是合法JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("AI返回的JSON根节点必须是对象")
    return value


def _display_value(value) -> str:
    if value is None or value == "":
        return "未提及"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _build_extraction_prompt(template, fields: list[dict]) -> str:
    output_example = {field["key"]: "" for field in fields}
    field_rules = "\n".join(
        f'- {field["key"]}（{field["label"]}）：{field.get("instruction") or "按合同原文准确提取"}'
        for field in fields
    )
    return f"""你是合同信息抽取专家。请根据合同原文完成“{template.name}”方案的信息提取。

分析重点：
{template.analysis_focus or "准确提取合同中的关键事实，不推测原文没有的信息。"}

字段要求：
{field_rules}

请严格按照以下JSON格式输出，只能使用给定的英文键，不要增加字段，不要输出解释或Markdown：
{json.dumps(output_example, ensure_ascii=False, indent=2)}

规则：
1. 每个字段都必须输出。
2. 同一字段包含多项内容时，用清晰的中文短句合并表达。
3. 合同中没有明确记载时填写“未提及”。
4. 不得根据常识补写合同中不存在的内容。"""


def _normalize_extraction(text: str, fields: list[dict]) -> str:
    parsed = _parse_json_object(text)
    normalized = {}
    for field in fields:
        value = parsed.get(field["key"], parsed.get(field["label"]))
        normalized[field["key"]] = _display_value(value)
    return json.dumps(normalized, ensure_ascii=False)


def _build_review_prompt(template) -> str:
    base_prompt = _load_prompt(PROMPT_REASONABILITY_CHECK)
    return f"""{base_prompt}

## 本次分析方案

方案名称：{template.name}
总体分析重点：{template.analysis_focus or "检查合同关键条款的完整性、一致性和履约风险。"}
附加审查要求：{template.review_instructions or "无"}

请将上述方案要求与通用审查规则一并执行。"""


def _normalize_review(text: str) -> str:
    parsed = _parse_json_object(text)
    issues = parsed.get("数据问题", [])
    reasonability = parsed.get("内容合理性", [])
    if not isinstance(issues, list) or not isinstance(reasonability, list):
        raise ValueError("AI返回的审查结果结构不正确")
    normalized = {
        "数据问题": issues,
        "内容合理性": reasonability,
        "总结": _display_value(parsed.get("总结")),
    }
    return json.dumps(normalized, ensure_ascii=False)


class DeepSeekService:
    """Service for calling DeepSeek API."""

    def __init__(self):
        self._client = None

    def _get_client(self) -> OpenAI:
        """Lazy initialize OpenAI client pointing to DeepSeek."""
        if self._client is None:
            api_key = _get_deepseek_key()
            if not api_key:
                raise RuntimeError("未配置DeepSeek API密钥。请在设置中配置 DEEPSEEK_API_KEY")
            self._client = OpenAI(
                api_key=api_key,
                base_url=DEEPSEEK_BASE_URL,
                timeout=DEEPSEEK_TIMEOUT_SECONDS,
            )
        return self._client

    def _call_api(self, system_prompt: str, user_content: str) -> dict:
        """Call DeepSeek API and return response."""
        client = self._get_client()
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=DEEPSEEK_TEMPERATURE,
        )
        return {
            "response_text": response.choices[0].message.content or "",
            "tokens_used": response.usage.total_tokens if response.usage else None,
        }

    def analyze_document(self, document, template) -> list[dict]:
        """
        Run both analyses on a document.

        Args:
            document: Document ORM object with ocr_text populated.

        Returns:
            List of result dicts with prompt_type, prompt_text, response_text, tokens_used.
        """
        if not document.ocr_text:
            raise ValueError("文档没有OCR文本，请先进行OCR识别")

        ocr_text = document.ocr_text
        max_chars = 60_000
        if len(ocr_text) > max_chars:
            ocr_text = ocr_text[:max_chars] + "\n\n[文本过长已截断...]"

        fields = [field for field in decode_fields(template) if field.get("enabled", True)]
        if not fields:
            raise ValueError("分析方案没有启用的输出字段")

        prompt1 = _build_extraction_prompt(template, fields)
        r1 = self._call_api(prompt1, ocr_text)
        results = [
            {
                "prompt_type": "attribute_extraction",
                "prompt_text": prompt1,
                "response_text": _normalize_extraction(r1["response_text"], fields),
                "tokens_used": r1["tokens_used"],
            }
        ]

        if template.review_enabled:
            prompt2 = _build_review_prompt(template)
            r2 = self._call_api(prompt2, ocr_text)
            results.append(
                {
                    "prompt_type": "reasonability_check",
                    "prompt_text": prompt2,
                    "response_text": _normalize_review(r2["response_text"]),
                    "tokens_used": r2["tokens_used"],
                }
            )
        return results


_deepseek_service: Optional[DeepSeekService] = None


def get_deepseek_service() -> DeepSeekService:
    global _deepseek_service
    if _deepseek_service is None:
        _deepseek_service = DeepSeekService()
    return _deepseek_service
