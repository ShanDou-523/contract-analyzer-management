"""Persistence helpers and built-in contract analysis templates."""

import json
import uuid

from models.document import AnalysisTemplate


MAINTENANCE_FIELDS = [
    {"key": "contract_name", "label": "合同名称", "instruction": "提取合同标题或正式名称"},
    {"key": "contract_no", "label": "合同编号", "instruction": "提取合同中明确记载的编号"},
    {"key": "contract_type", "label": "合同类型", "instruction": "判断属于清洗、维修、维保、设备安装或混合合同"},
    {"key": "parties", "label": "合同主体", "instruction": "提取甲方、乙方名称，并明确对应角色"},
    {"key": "project_info", "label": "项目信息", "instruction": "提取项目名称和项目地点"},
    {"key": "service_scope", "label": "服务范围", "instruction": "提取服务对象、主要工作内容以及设备或系统范围"},
    {"key": "contract_period", "label": "合同期限", "instruction": "提取开始日期、结束日期或施工工期"},
    {"key": "contract_amount", "label": "合同金额", "instruction": "提取总金额、计价方式、是否含税及税率"},
    {"key": "payment_terms", "label": "付款条款", "instruction": "提取付款比例、付款节点、付款期限和发票要求"},
    {"key": "acceptance_terms", "label": "验收条款", "instruction": "提取验收标准、验收条件和验收资料"},
    {"key": "warranty_terms", "label": "质保与售后", "instruction": "提取质保期限、起算时间和售后响应要求"},
    {"key": "risk_terms", "label": "风险条款", "instruction": "提取保证金、主要违约责任、解除条件和争议管辖"},
]

LEASE_FIELDS = [
    {"key": "store_name", "label": "店名", "instruction": "提取店铺或项目名称"},
    {"key": "lease_term", "label": "租赁期", "instruction": "提取约定的租赁期限"},
    {"key": "party_a", "label": "甲方", "instruction": "提取甲方完整名称"},
    {"key": "party_b", "label": "乙方", "instruction": "提取乙方完整名称"},
    {"key": "rent_payment_time", "label": "租金支付时间", "instruction": "提取租金支付节点和期限"},
    {"key": "rent_payment_amount", "label": "租金支付金额", "instruction": "提取租金金额和支付周期"},
    {"key": "area", "label": "面积", "instruction": "提取租赁面积"},
    {"key": "lease_date", "label": "租赁时间", "instruction": "提取租赁起止日期"},
    {"key": "deposit", "label": "押金或保证金", "instruction": "提取押金或保证金金额"},
    {"key": "deposit_return_conditions", "label": "押金返还条件", "instruction": "提取押金返还条件和期限"},
    {"key": "termination_penalty", "label": "解除违约金", "instruction": "提取解除合同相关违约金"},
    {"key": "property_fee", "label": "物业费", "instruction": "提取物业费标准和支付方式"},
]


def _with_ids(fields: list[dict]) -> list[dict]:
    return [
        {"id": str(uuid.uuid4()), "enabled": True, **field}
        for field in fields
    ]


BUILTIN_TEMPLATES = [
    {
        "name": "维保合同",
        "description": "适用于清洗、维修、维保、设备安装及混合服务合同。",
        "analysis_focus": "重点识别服务范围、履约期限、费用支付、验收、质保售后及双方风险责任。",
        "fields": MAINTENANCE_FIELDS,
        "review_enabled": True,
        "review_instructions": (
            "逐项检查服务范围是否明确，工期或服务期限是否一致；核对合同金额、税费、付款比例和付款节点；"
            "检查验收标准与程序是否可执行，质保起算时间和售后响应时限是否明确；"
            "重点识别保证金、违约责任、解除条件、免责条款和争议管辖是否失衡或缺失。"
        ),
        "is_default": True,
    },
    {
        "name": "租赁合同（旧版兼容）",
        "description": "保留原系统的租赁合同字段和金额核验方向。",
        "analysis_focus": "重点提取租赁主体、租期、租金、面积、押金、物业费和违约责任。",
        "fields": LEASE_FIELDS,
        "review_enabled": True,
        "review_instructions": (
            "必须重新计算月租金乘以支付周期，并与标注金额比较；检查押金、物业费和违约金计算；"
            "金额存在任何不一致时标记为严重。"
        ),
        "is_default": False,
    },
]


def encode_fields(fields: list[dict]) -> str:
    return json.dumps(fields, ensure_ascii=False)


def decode_fields(template: AnalysisTemplate) -> list[dict]:
    try:
        fields = json.loads(template.fields_json)
        return fields if isinstance(fields, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def ensure_builtin_templates(db) -> None:
    if db.query(AnalysisTemplate).count() > 0:
        if not db.query(AnalysisTemplate).filter(AnalysisTemplate.is_default.is_(True)).first():
            first = db.query(AnalysisTemplate).order_by(AnalysisTemplate.created_at.asc()).first()
            if first:
                first.is_default = True
                db.commit()
        return

    for item in BUILTIN_TEMPLATES:
        db.add(
            AnalysisTemplate(
                name=item["name"],
                description=item["description"],
                analysis_focus=item["analysis_focus"],
                fields_json=encode_fields(_with_ids(item["fields"])),
                review_enabled=item["review_enabled"],
                review_instructions=item["review_instructions"],
                version=1,
                is_default=item["is_default"],
            )
        )
    db.commit()


def get_template_for_analysis(db, template_id: str | None) -> AnalysisTemplate | None:
    if template_id:
        return db.query(AnalysisTemplate).filter(AnalysisTemplate.id == template_id).first()
    return (
        db.query(AnalysisTemplate).filter(AnalysisTemplate.is_default.is_(True)).first()
        or db.query(AnalysisTemplate).order_by(AnalysisTemplate.created_at.asc()).first()
    )
