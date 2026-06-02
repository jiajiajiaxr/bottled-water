from __future__ import annotations

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
        "方案": "proposal",
        "报告": "report",
        "需求": "prd",
        "会议": "meeting",
        "实验": "lab_report",
        "lab": "lab_report",
    }
    value = aliases.get(value, value)
    return value if value in DOCUMENT_TEMPLATES else "report"


def _section(title: str, *blocks: dict[str, Any]) -> dict[str, Any]:
    return {"title": title, "level": 1, "blocks": list(blocks)}


def _paragraph(text: str) -> dict[str, str]:
    return {"type": "paragraph", "text": text}


def _list(*items: str, ordered: bool = False) -> dict[str, Any]:
    return {"type": "list", "ordered": ordered, "items": list(items)}


def _table(headers: list[str], rows: list[list[str]]) -> dict[str, Any]:
    return {"type": "table", "headers": headers, "rows": rows}


def _callout(title: str, text: str, variant: str = "info") -> dict[str, str]:
    return {"type": "callout", "title": title, "text": text, "variant": variant}


_TABLE_STYLE = {"header_background": "#eef6ff", "border": "#cbd5e1", "text": "#1f2937"}


DOCUMENT_TEMPLATES: dict[str, DocumentTemplate] = {
    "report": DocumentTemplate(
        name="report",
        label="正式报告",
        description="用于分析、复盘、阶段总结和汇报材料。",
        subtitle="结构化分析与结论建议",
        required_fields=("title", "sections"),
        cover={"issuer": "AgentHub", "confidentiality": "内部资料", "date_label": "生成日期"},
        header="AgentHub 报告",
        footer="本报告由 AgentHub 文档工具生成",
        table_style=_TABLE_STYLE,
        title_levels={"section": 1, "subsection": 2},
        sections=(
            _section("摘要", _paragraph("概括背景、核心发现和建议结论。")),
            _section("背景与目标", _paragraph("说明问题背景、业务目标和评估范围。")),
            _section(
                "分析内容",
                _table(["维度", "观察", "影响"], [["现状", "待补充", "待评估"], ["风险", "待识别", "待跟踪"]]),
            ),
            _section("结论与建议", _list("形成可执行结论", "明确下一步负责人和时间点", ordered=True)),
        ),
    ),
    "proposal": DocumentTemplate(
        name="proposal",
        label="项目方案",
        description="用于项目立项、技术方案、实施计划和交付说明。",
        subtitle="目标、范围、计划与验收",
        required_fields=("title", "objectives", "timeline"),
        cover={"issuer": "AgentHub", "confidentiality": "项目资料", "date_label": "方案日期"},
        header="AgentHub 项目方案",
        footer="方案内容需结合实际项目进一步确认",
        table_style=_TABLE_STYLE,
        title_levels={"section": 1, "subsection": 2},
        sections=(
            _section("项目背景", _paragraph("说明项目来源、业务痛点和当前约束。")),
            _section("目标与范围", _list("明确建设目标", "界定交付范围", "列出不在本期处理的内容")),
            _section("实施计划", _table(["阶段", "关键任务", "交付物"], [["设计", "方案细化", "设计文档"], ["实现", "开发联调", "可运行版本"]])),
            _section("风险与保障", _callout("重点风险", "识别技术、进度、数据和权限风险，并给出缓解措施。", "warning")),
            _section("验收标准", _list("功能闭环可演示", "导出文件可打开", "测试与日志可追踪", ordered=True)),
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
        title_levels={"section": 1, "subsection": 2},
        sections=(
            _section("产品背景", _paragraph("描述目标用户、业务场景和当前痛点。")),
            _section("用户场景", _list("核心用户是谁", "用户要完成什么任务", "成功标准是什么")),
            _section("功能需求", _table(["模块", "需求描述", "优先级"], [["核心流程", "待补充", "P0"], ["辅助能力", "待补充", "P1"]])),
            _section("非功能需求", _list("性能", "安全", "可用性", "可观测性")),
            _section("验收指标", _paragraph("列出可验证的验收条件、测试数据和边界场景。")),
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
        title_levels={"section": 1, "subsection": 2},
        sections=(
            _section("会议信息", _table(["项目", "内容"], [["时间", "待补充"], ["参会人", "待补充"], ["主持人", "待补充"]])),
            _section("议题与讨论", _paragraph("按议题记录主要观点、分歧和达成共识。")),
            _section("会议结论", _list("结论一", "结论二", ordered=True)),
            _section("行动项", _table(["事项", "负责人", "截止时间", "状态"], [["待办事项", "待定", "待定", "未开始"]])),
            _section("签字确认", {"type": "signatures", "items": ["主持人", "记录人"]}),
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
        title_levels={"section": 1, "subsection": 2},
        sections=(
            _section("实验目的", _paragraph("说明实验要验证的问题、假设和评价指标。")),
            _section("环境与材料", _table(["类别", "配置"], [["软件环境", "待补充"], ["数据/样本", "待补充"], ["工具", "AgentHub"]])),
            _section("实验步骤", _list("准备环境", "执行实验", "记录数据", "复核结果", ordered=True)),
            _section("结果数据", _table(["指标", "结果", "说明"], [["准确率/通过率", "待补充", "待分析"], ["耗时", "待补充", "待分析"]])),
            _section("分析讨论", _paragraph("分析结果是否支持实验假设，说明异常、误差来源和改进方向。")),
            _section("结论", _callout("实验结论", "总结实验发现、适用范围和后续工作。", "success")),
            _section("附录", _paragraph("补充原始日志、配置、脚本或额外图表。")),
        ),
    ),
}
