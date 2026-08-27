"""Settings router for managing API keys."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.security import CurrentPrincipal, require_roles
from database import get_db
from services.audit_service import record_audit
from services.secret_service import get_secret_setting, set_secret_setting

router = APIRouter(
    prefix="/api/settings",
    tags=["settings"],
    dependencies=[Depends(require_roles("system_admin", "org_admin"))],
)


class SettingsOut(BaseModel):
    deepseek_api_key: str = ""
    baidu_ocr_api_key: str = ""
    baidu_ocr_secret_key: str = ""


class SettingsUpdate(BaseModel):
    deepseek_api_key: str = ""
    baidu_ocr_api_key: str = ""
    baidu_ocr_secret_key: str = ""


@router.get("", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db)):
    """Get current API key settings (masked)."""
    deepseek = get_secret_setting(db, "deepseek_api_key")
    baidu_ak = get_secret_setting(db, "baidu_ocr_api_key")
    baidu_sk = get_secret_setting(db, "baidu_ocr_secret_key")

    import os

    if not deepseek:
        deepseek = os.getenv("DEEPSEEK_API_KEY", "")
    if not baidu_ak:
        baidu_ak = os.getenv("BAIDU_OCR_API_KEY", "")
    if not baidu_sk:
        baidu_sk = os.getenv("BAIDU_OCR_SECRET_KEY", "")

    def mask(s):
        if len(s) <= 10:
            return s[:3] + "***" if len(s) > 3 else "***"
        return s[:6] + "****" + s[-4:]

    return SettingsOut(
        deepseek_api_key=mask(deepseek) if deepseek else "",
        baidu_ocr_api_key=mask(baidu_ak) if baidu_ak else "",
        baidu_ocr_secret_key=mask(baidu_sk) if baidu_sk else "",
    )


@router.put("")
def update_settings(
    data: SettingsUpdate,
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_roles("system_admin", "org_admin")),
):
    """Update API keys. Only non-empty values are saved."""
    updated = []
    if data.deepseek_api_key.strip():
        set_secret_setting(db, "deepseek_api_key", data.deepseek_api_key.strip())
        updated.append("deepseek_api_key")
    if data.baidu_ocr_api_key.strip():
        set_secret_setting(db, "baidu_ocr_api_key", data.baidu_ocr_api_key.strip())
        updated.append("baidu_ocr_api_key")
    if data.baidu_ocr_secret_key.strip():
        set_secret_setting(db, "baidu_ocr_secret_key", data.baidu_ocr_secret_key.strip())
        updated.append("baidu_ocr_secret_key")
    if updated:
        record_audit(
            db,
            "settings.provider_credentials_updated",
            organization_id=principal.organization_id,
            user_id=principal.user_id,
            resource_type="provider_settings",
            details={"keys": updated},
        )
        db.commit()
    return {"message": f"已更新 {len(updated)} 项设置", "updated": updated}
