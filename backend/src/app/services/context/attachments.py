from __future__ import annotations

import re
from typing import Any

from app.services.context.compression import trim_text


IMAGE_PROMPT_PATTERN = re.compile(
    r"(图片|图像|照片|截图|看一下|识别|这是什么|什么内容|describe|image|photo|picture)",
    re.I,
)
VISION_EXTRACTORS = {"ocr", "vision", "vision_model", "image_ocr"}
IMAGE_PLACEHOLDER_PATTERN = re.compile(
    r"(当前未启用视觉|未启用.*OCR|无法判断图片内容|图片附件；当前未启用|ready_for_vision_model)",
    re.I,
)


def attachment_context_from_items(attachments: list[Any], *, max_chars: int = 12_000) -> str:
    if not attachments:
        return ""
    parts: list[str] = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        filename = attachment_filename(item)
        content_type = attachment_content_type(item)
        file_id = str(item.get("file_id") or item.get("id") or "").strip()
        parse_status = str(item.get("parse_status") or "unknown")
        header = f"- {filename} ({content_type or 'unknown'})"
        if file_id:
            header += f" file_id={file_id}"
        header += f" parse_status={parse_status}"

        extracted = readable_attachment_text(item)
        if extracted:
            parts.append(f"{header}\n{trim_text(extracted, max_chars=3000)}")
        elif is_image_attachment(item):
            parts.append(
                f"{header}：图片附件；未启用视觉解析或未提取到可用 OCR/视觉文本，不能假装理解图片内容。"
            )
        else:
            parts.append(f"{header}：未提取到可读文本。")
    return trim_text("\n\n".join(parts), max_chars=max_chars)


def attachment_preflight_reply(prompt: str, attachments: list[Any]) -> str | None:
    normalized = [item for item in attachments if isinstance(item, dict)]
    if not normalized:
        return None
    readable = [item for item in normalized if readable_attachment_text(item)]
    unreadable_images = [item for item in normalized if is_unreadable_image(item)]
    if unreadable_images and (not readable or IMAGE_PROMPT_PATTERN.search(prompt)):
        names = "、".join(attachment_filename(item) for item in unreadable_images[:4])
        metadata = unreadable_images[0].get("metadata") if isinstance(unreadable_images[0].get("metadata"), dict) else {}
        hint = str(metadata.get("setup_hint") or "请安装 Tesseract OCR 或启用视觉模型后再自动识别图片。")
        return (
            f"我已收到图片附件（{names}），但当前环境未提取到可用 OCR/视觉文本，无法判断图片内容。"
            f"当前未启用视觉/OCR解析；{hint}"
        )
    if not readable and normalized:
        names = "、".join(attachment_filename(item) for item in normalized[:4])
        return f"附件（{names}）未提取到可读文本，我无法基于文件内容总结。请换成可解析的文本类文件，或启用对应解析能力。"
    return None


def attachment_filename(item: dict[str, Any]) -> str:
    return str(item.get("filename") or item.get("original_filename") or item.get("file_id") or "attachment")


def attachment_content_type(item: dict[str, Any]) -> str:
    return str(item.get("content_type") or "")


def readable_attachment_text(item: dict[str, Any]) -> str:
    extracted = str(item.get("extracted_text") or "").strip()
    if not extracted:
        return ""
    if is_image_attachment(item) and not has_real_image_text(item):
        return ""
    if IMAGE_PLACEHOLDER_PATTERN.search(extracted):
        return ""
    return extracted


def is_image_attachment(item: dict[str, Any]) -> bool:
    return attachment_content_type(item).lower().startswith("image/")


def is_unreadable_image(item: dict[str, Any]) -> bool:
    return is_image_attachment(item) and not readable_attachment_text(item)


def has_real_image_text(item: dict[str, Any]) -> bool:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    extractor = str(metadata.get("extractor") or "").lower()
    vision_status = str(metadata.get("vision_status") or "").lower()
    return extractor in VISION_EXTRACTORS and vision_status in {"parsed", "succeeded", "success"}
