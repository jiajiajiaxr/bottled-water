from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DocumentTemplate:
    name: str
    label: str
    description: str
    subtitle: str
    required_fields: tuple[str, ...]
    cover: dict[str, Any]
    header: str
    footer: str
    table_style: dict[str, str]
    title_levels: dict[str, int]
    sections: tuple[dict[str, Any], ...]

    def default_sections(self) -> list[dict[str, Any]]:
        return deepcopy(list(self.sections))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "subtitle": self.subtitle,
            "required_fields": list(self.required_fields),
            "cover": deepcopy(self.cover),
            "header": self.header,
            "footer": self.footer,
            "table_style": deepcopy(self.table_style),
            "title_levels": deepcopy(self.title_levels),
        }

    def example(self) -> dict[str, Any]:
        return {
            "kind": "document",
            "title": f"{self.label}示例",
            "subtitle": self.subtitle,
            "template": self.name,
            "cover": deepcopy(self.cover),
            "toc": {"enabled": True, "title": "目录"},
            "sections": self.default_sections(),
            "metadata": {"template": self.name, "source": "AgentHub"},
        }


def available_templates() -> list[dict[str, Any]]:
    return [template.to_dict() for template in DOCUMENT_TEMPLATES.values()]


def get_template(name: str | None) -> DocumentTemplate:
    return DOCUMENT_TEMPLATES[normalize_template_name(name)]


def normalize_template_name(name: str | None) -> str:
    value = (name or "report").strip().lower()
    aliases = {
        "word": "report",
        "doc": "report",
        "document": "report",
        "报告": "report",
        "正式报告": "report",
        "分析报告": "report",
        "方案": "proposal",
        "项目方案": "proposal",
        "技术方案": "proposal",
        "prd": "prd",
        "需求": "prd",
        "需求文档": "prd",
        "产品需求": "prd",
        "meeting": "meeting",
        "会议": "meeting",
        "会议纪要": "meeting",
        "weekly": "weekly",
        "周报": "weekly",
        "工作周报": "weekly",
        "lab": "lab_report",
        "experiment": "lab_report",
        "实验": "lab_report",
        "实验报告": "lab_report",
        "project": "project_plan",
        "project_plan": "project_plan",
        "项目计划": "project_plan",
        "项目计划书": "project_plan",
        "工作计划": "project_plan",
        "计划": "project_plan",
    }
    value = aliases.get(value, value)
    return value if value in DOCUMENT_TEMPLATES else "report"


def infer_template_name(*values: str | None) -> str:
    text = " ".join(value or "" for value in values).lower()
    rules: tuple[tuple[str, str], ...] = (
        ("lab_report", r"实验|试验|化学|滴定|测定|样本|实验报告|lab|experiment"),
        ("weekly", r"周报|本周|下周|weekly|week report|工作进展"),
        ("project_plan", r"项目计划|排期|里程碑|甘特|行动计划|计划书|project plan"),
        ("proposal", r"方案|建议书|实施方案|技术方案|proposal|解决方案"),
        ("prd", r"prd|产品需求|需求文档|用户故事|验收标准"),
        ("meeting", r"会议|纪要|会议纪要|议题|参会|meeting|minutes"),
        ("report", r"报告|分析|总结|复盘|调研|评估|report"),
    )
    for template, pattern in rules:
        if re.search(pattern, text, re.I):
            return template
    return "report"


def _section(title: str, *blocks: dict[str, Any], level: int = 1) -> dict[str, Any]:
    return {"title": title, "level": level, "blocks": list(blocks)}


def _paragraph(text: str) -> dict[str, str]:
    return {"type": "paragraph", "text": text}


def _heading(text: str, level: int = 2) -> dict[str, Any]:
    return {"type": "heading", "level": level, "text": text}


def _list(*items: str, ordered: bool = False) -> dict[str, Any]:
    return {"type": "list", "ordered": ordered, "items": list(items)}


def _table(headers: list[str], rows: list[list[str]]) -> dict[str, Any]:
    return {"type": "table", "headers": headers, "rows": rows}


def _callout(title: str, text: str, variant: str = "info") -> dict[str, str]:
    return {"type": "callout", "title": title, "text": text, "variant": variant}


def _quote(text: str) -> dict[str, str]:
    return {"type": "quote", "text": text}


def _risk_items(rows: list[list[str]]) -> dict[str, Any]:
    return {"type": "risk_item", "items": rows}


def _action_plan(rows: list[list[str]]) -> dict[str, Any]:
    return {"type": "action_plan", "items": rows}


_TABLE_STYLE = {"header_background": "#eef6ff", "border": "#cbd5e1", "text": "#1f2937"}
_TITLE_LEVELS = {"section": 1, "subsection": 2, "minor": 3}


DOCUMENT_TEMPLATES: dict[str, DocumentTemplate] = {
    "report": DocumentTemplate(
        name="report",
        label="正式报告",
        description="用于分析、复盘、调研、评估和阶段性汇报。",
        subtitle="摘要、分析、风险、行动计划与结论",
        required_fields=("title", "summary", "sections", "conclusion"),
        cover={"issuer": "AgentHub", "confidentiality": "内部资料", "date_label": "生成日期"},
        header="AgentHub 正式报告",
        footer="本报告由 AgentHub 文档工具生成",
        table_style=_TABLE_STYLE,
        title_levels=_TITLE_LEVELS,
        sections=(
            _section("摘要", _paragraph("概括背景、核心发现、关键建议和最终结论。")),
            _section(
                "背景与目标",
                _paragraph("说明问题背景、业务目标、使用场景和评估范围。"),
                _heading("范围说明", 2),
                _list("明确本报告覆盖内容", "列出关键约束和假设", "说明不在本次分析范围内的事项"),
            ),
            _section(
                "分析内容",
                _table(["维度", "观察", "影响"], [["现状", "待补充", "待评估"], ["机会", "待识别", "待评估"]]),
                _quote("关键判断应基于可验证信息，并在必要时标注假设。"),
            ),
            _section("风险项", _risk_items([["待识别风险", "中", "待评估", "制定缓解措施"]])),
            _section("行动计划", _action_plan([["补充数据", "负责人待定", "本周", "未开始"]])),
            _section("结论", {"type": "conclusion", "text": "总结判断、适用范围和下一步建议。"}),
        ),
    ),
    "proposal": DocumentTemplate(
        name="proposal",
        label="项目方案",
        description="用于项目立项、技术方案、实施计划和交付说明。",
        subtitle="目标、范围、设计、实施与验收",
        required_fields=("title", "objectives", "timeline", "acceptance"),
        cover={"issuer": "AgentHub", "confidentiality": "项目资料", "date_label": "方案日期"},
        header="AgentHub 项目方案",
        footer="方案内容需结合实际项目进一步确认",
        table_style=_TABLE_STYLE,
        title_levels=_TITLE_LEVELS,
        sections=(
            _section("方案摘要", _paragraph("说明方案目标、核心路径、预期收益和交付边界。")),
            _section("项目背景", _paragraph("描述项目来源、业务痛点、现有约束和关键干系人。")),
            _section("目标与范围", _list("明确建设目标", "界定交付范围", "列出不在本期处理的内容")),
            _section(
                "技术与实施方案",
                _heading("整体设计", 2),
                _paragraph("说明核心模块、数据流、交互流程和技术选型。"),
                _table(["模块", "职责", "交付物"], [["前端", "页面与交互", "可演示界面"], ["后端", "服务与数据", "API 与数据模型"]]),
            ),
            _section("实施计划", _action_plan([["方案细化", "产品/技术", "第 1 周", "待启动"], ["开发联调", "研发", "第 2-3 周", "待启动"]])),
            _section("风险项", _risk_items([["需求变更", "中", "影响排期", "设置变更确认机制"]])),
            _section("验收标准", _list("功能闭环可演示", "导出文件可打开", "测试与日志可追溯", ordered=True)),
            _section("结论", {"type": "conclusion", "text": "给出推荐执行路径、资源需求和下一步决策点。"}),
        ),
    ),
    "weekly": DocumentTemplate(
        name="weekly",
        label="工作周报",
        description="用于团队或个人本周进展、风险、下周计划和需要协同事项。",
        subtitle="本周进展、问题风险与下周计划",
        required_fields=("title", "progress", "risks", "next_week"),
        cover={"issuer": "AgentHub", "confidentiality": "工作资料", "date_label": "周报日期"},
        header="AgentHub 工作周报",
        footer="周报用于同步进展与风险，不替代正式验收文档",
        table_style=_TABLE_STYLE,
        title_levels=_TITLE_LEVELS,
        sections=(
            _section("摘要", _paragraph("概括本周整体进展、主要成果和需要关注的问题。")),
            _section("本周完成", _table(["事项", "结果", "备注"], [["重点任务", "已推进", "待补充"]])),
            _section("关键进展", _list("完成事项一", "完成事项二", "协同事项三")),
            _section("风险项", _risk_items([["进度依赖", "中", "影响交付节奏", "提前确认协同窗口"]])),
            _section("下周行动计划", _action_plan([["推进下一阶段任务", "负责人待定", "下周", "计划中"]])),
            _section("结论", {"type": "conclusion", "text": "总结当前状态，并明确下周优先级。"}),
        ),
    ),
    "lab_report": DocumentTemplate(
        name="lab_report",
        label="实验报告",
        description="用于实验目的、环境、步骤、数据、分析和结论记录。",
        subtitle="实验过程、结果与分析",
        required_fields=("title", "objective", "environment", "results"),
        cover={"issuer": "AgentHub", "confidentiality": "实验资料", "date_label": "实验日期"},
        header="AgentHub 实验报告",
        footer="实验结果需保留原始数据和复现实验环境",
        table_style=_TABLE_STYLE,
        title_levels=_TITLE_LEVELS,
        sections=(
            _section("摘要", _paragraph("概括实验目的、方法、主要数据和结论。")),
            _section("实验目的", _paragraph("说明实验要验证的问题、假设和评价指标。")),
            _section("实验原理", _paragraph("说明实验涉及的基本原理、计算方法或理论依据。")),
            _section("实验环境与材料", _table(["类别", "配置"], [["软件/仪器", "待补充"], ["样本/试剂", "待补充"], ["工具", "AgentHub"]])),
            _section("实验步骤", _list("准备环境与材料", "执行实验流程", "记录原始数据", "复核结果", ordered=True)),
            _section("结果数据", _table(["指标", "结果", "说明"], [["测量值", "待补充", "待分析"], ["误差", "待补充", "待分析"]])),
            _section("分析讨论", _paragraph("分析结果是否支持实验假设，说明异常、误差来源和改进方向。")),
            _section("风险项", _risk_items([["样本误差", "中", "影响结论可靠性", "增加重复实验或校准步骤"]])),
            _section("结论", {"type": "conclusion", "text": "总结实验发现、适用范围和后续工作。"}),
            _section("附录", _paragraph("补充原始日志、配置、脚本或额外图表。")),
        ),
    ),
    "project_plan": DocumentTemplate(
        name="project_plan",
        label="项目计划",
        description="用于项目目标、里程碑、资源分工、风险和行动计划。",
        subtitle="目标、里程碑、分工、风险与交付",
        required_fields=("title", "milestones", "owners", "risks"),
        cover={"issuer": "AgentHub", "confidentiality": "项目计划", "date_label": "计划日期"},
        header="AgentHub 项目计划",
        footer="项目计划需随执行情况持续更新",
        table_style=_TABLE_STYLE,
        title_levels=_TITLE_LEVELS,
        sections=(
            _section("摘要", _paragraph("概括项目目标、周期、资源和关键交付物。")),
            _section("项目目标", _list("明确业务目标", "定义成功指标", "确认约束条件")),
            _section("里程碑计划", _table(["里程碑", "时间", "交付物", "负责人"], [["启动", "第 1 周", "计划确认", "待定"], ["交付", "第 4 周", "正式版本", "待定"]])),
            _section("资源与分工", _table(["角色", "职责", "投入"], [["产品", "需求与验收", "待定"], ["研发", "实现与联调", "待定"]])),
            _section("风险项", _risk_items([["范围扩张", "中", "影响排期", "冻结一期边界并设置变更流程"]])),
            _section("行动计划", _action_plan([["确认需求边界", "负责人待定", "本周", "未开始"], ["完成方案评审", "负责人待定", "下周", "未开始"]])),
            _section("结论", {"type": "conclusion", "text": "明确是否建议启动、关键依赖和下一步行动。"}),
        ),
    ),
    "prd": DocumentTemplate(
        name="prd",
        label="产品需求文档",
        description="用于产品功能定义、用户故事、交互规则和验收口径。",
        subtitle="场景、需求、规则与验收",
        required_fields=("title", "users", "requirements"),
        cover={"issuer": "AgentHub", "confidentiality": "产品资料", "date_label": "需求日期"},
        header="AgentHub PRD",
        footer="需求变更需同步版本记录",
        table_style=_TABLE_STYLE,
        title_levels=_TITLE_LEVELS,
        sections=(
            _section("摘要", _paragraph("概括产品目标、目标用户、核心能力和上线边界。")),
            _section("产品背景", _paragraph("描述目标用户、业务场景和当前痛点。")),
            _section("用户场景", _list("核心用户是谁", "用户要完成什么任务", "成功标准是什么")),
            _section("功能需求", _table(["模块", "需求描述", "优先级"], [["核心流程", "待补充", "P0"], ["辅助能力", "待补充", "P1"]])),
            _section("交互与规则", _paragraph("说明页面、状态、异常、权限和数据规则。")),
            _section("风险项", _risk_items([["需求歧义", "中", "影响研发理解", "补充验收案例与边界条件"]])),
            _section("验收标准", _list("核心路径可完成", "异常状态有提示", "数据状态可追溯", ordered=True)),
            _section("结论", {"type": "conclusion", "text": "给出上线建议、依赖事项和后续迭代方向。"}),
        ),
    ),
    "meeting": DocumentTemplate(
        name="meeting",
        label="会议纪要",
        description="用于记录会议背景、议题、结论、行动项和签字确认。",
        subtitle="议题、结论与行动项",
        required_fields=("title", "attendees", "action_items"),
        cover={"issuer": "AgentHub", "confidentiality": "会议资料", "date_label": "会议日期"},
        header="AgentHub 会议纪要",
        footer="行动项以会后确认版本为准",
        table_style=_TABLE_STYLE,
        title_levels=_TITLE_LEVELS,
        sections=(
            _section("摘要", _paragraph("概括会议目的、主要结论和待办事项。")),
            _section("会议信息", _table(["项目", "内容"], [["时间", "待补充"], ["参会人", "待补充"], ["主持人", "待补充"]])),
            _section("议题与讨论", _paragraph("按议题记录主要观点、分歧和达成共识。")),
            _section("会议结论", _list("结论一", "结论二", ordered=True)),
            _section("行动计划", _action_plan([["待办事项", "待定", "待定", "未开始"]])),
            _section("风险项", _risk_items([["行动项无人负责", "中", "影响落地", "会后确认负责人和截止时间"]])),
            _section("签字确认", {"type": "signatures", "items": ["主持人", "记录人"]}),
        ),
    ),
}
