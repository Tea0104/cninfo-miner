"""
全局配置文件。修改此文件即可更换搜索关键词、日期范围和 API 密钥。
"""

import os
from pathlib import Path

# ── 项目路径 ──────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# ── 巨潮资讯网搜索参数 ──────────────────────────────
SEARCH_KEYWORD = "独立董事+辞职"   # 搜索关键词
START_DATE = "2016-01-01"         # 开始日期
END_DATE = "2018-12-31"           # 结束日期

# ── LLM API 配置（DeepSeek 或兼容接口）─────────────────
API_URL = os.environ.get("LLM_API_URL", "https://api.deepseek.com")
API_KEY = os.environ.get("LLM_API_KEY", "你的API密钥")
MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")

# ── 其他 ─────────────────────────────────────────────
REQUEST_INTERVAL = 1.0          # 请求间隔（秒）
MAX_RETRIES = 3                 # 失败重试次数

# ====================================================================
#  Prompt 系统
# ====================================================================

def build_prompt(target: str, fields: str, extra: str = "") -> str:
    """Generate an extraction prompt from simple user input.

    Parameters
    ----------
    target : str
        What to extract, e.g. "独立董事辞职信息" or "固定资产购买记录"
    fields : str
        Comma-separated field names, e.g. "姓名, 辞职原因" or "资产名称, 购买金额, 交易对方"
    extra : str
        Optional extra rules, e.g. "金额以万元为单位" or "忽略金额小于100万的条目"

    Returns
    -------
    str
        Full system prompt ready for LLM.
    """
    field_list = [f.strip() for f in fields.split(",") if f.strip()]
    if not field_list:
        field_list = ["信息"]

    field_desc = "、".join(field_list)

    extra_section = ""
    if extra.strip():
        extra_section = f"\n额外规则：\n{extra.strip()}"

    # Build the JSON example
    if len(field_list) == 1:
        json_example = '[{"' + field_list[0] + '": "..."}]'
    else:
        pairs = [f'"{f}": "...（原文）"' for f in field_list]
        json_example = '[{' + ", ".join(pairs) + '}]'

    return f"""你是一名金融公告信息抽取专家。你的任务是从上市公司公告中提取{target}。

规则：
1. 只提取与"{target}"直接相关的信息，忽略无关内容
2. 提取以下字段：{field_desc}
3. 所有字段保留原文表述，不做任何概括、改写或总结。如果某项信息在公告中未提及，填"未披露"
4. 如果一条公告包含多条提取目标，每条单独一条记录
5. 如果公告中不包含任何"{target}"，返回空数组 []
6. 严格输出 JSON 数组，不要添加任何其他文字
{extra_section}
输出格式：
{json_example}"""


# ── 预设场景（非穷举，用户可按需自定义）────────────────

PRESET_SCENARIOS = {
    "高管离职": {
        "target": "高管辞职或离职信息",
        "fields": "姓名, 职位, 辞职原因",
        "extra": "高管包括：董事、独立董事、总经理、副总经理、财务总监、董事会秘书、总裁、副总裁等。监事除外。去除姓名后的称谓。职位保留全称。",
    },
    "资产收购与出售": {
        "target": "资产收购或出售信息",
        "fields": "交易类型, 资产名称, 交易金额, 交易对方, 交易日期",
        "extra": "交易类型填：收购/出售。金额保留原始数字和单位。如有多笔交易，每笔一条记录。",
    },
    "大股东增减持": {
        "target": "股东增减持或股权变动信息",
        "fields": "股东名称, 变动方向, 股份数量, 占总股本比例, 变动原因",
        "extra": "变动方向填：增持/减持/转让。忽略金额和数量过小的个人变动。",
    },
    "重大合同": {
        "target": "重大合同签署信息",
        "fields": "合同对方, 合同金额, 合同内容摘要, 签署日期",
        "extra": "合同内容用1-2句话概括即可。签署日期格式统一为yyyy-mm-dd。",
    },
    "违规处罚": {
        "target": "公司违规或收到监管处罚的信息",
        "fields": "违规主体, 处罚机构, 处罚类型, 罚款金额, 违规事由摘要",
        "extra": "违规事由用原文关键句。如无罚款则填'无'。",
    },
    "分红方案": {
        "target": "利润分配或分红方案信息",
        "fields": "分红年度, 每股分红金额, 分红总额, 除权除息日",
        "extra": "保留原始数字和单位。如公告仅含预案未实施，仍提取并在备注注明。",
    },
    "业绩预告": {
        "target": "业绩预告或业绩快报信息",
        "fields": "预告类型, 预计净利润下限, 预计净利润上限, 上年同期净利润, 变动原因",
        "extra": "预告类型填：预增/预减/扭亏/续亏/首亏/略增/略减。金额单位统一为万元。",
    },
    "诉讼仲裁": {
        "target": "重大诉讼或仲裁信息",
        "fields": "原告方, 被告方, 涉案金额, 案件状态, 案由摘要",
        "extra": "案件状态填：已立案/审理中/已判决/已和解。案由用1-2句概括。",
    },
    "会计师事务所变更": {
        "target": "会计师事务所变更信息",
        "fields": "原事务所, 新事务所, 变更原因, 变更日期",
        "extra": "如有连续审计年限也一并提取。",
    },
    "股票回购": {
        "target": "股份回购信息",
        "fields": "回购方式, 回购数量, 回购金额上限, 回购用途, 回购期限",
        "extra": "保留原始数字和单位。",
    },
    "自定义": {
        "target": "",
        "fields": "",
        "extra": "",
    },
}


def _init_presets():
    """Auto-generate full prompts for each preset."""
    presets = {}
    for name, cfg in PRESET_SCENARIOS.items():
        if name == "自定义":
            presets[name] = {
                "target": "",
                "fields": [],
                "prompt": build_prompt("（请先描述提取目标）", "字段1, 字段2"),
            }
        else:
            presets[name] = {
                "target": cfg["target"],
                "fields": cfg["fields"].split(", "),
                "prompt": build_prompt(cfg["target"], cfg["fields"], cfg.get("extra", "")),
            }
    return presets


PROMPT_PRESETS = _init_presets()

# 默认 prompt（兼容旧引用）
EXTRACTION_SYSTEM_PROMPT = PROMPT_PRESETS["高管离职"]["prompt"]
