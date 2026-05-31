from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeBase, KnowledgeDocument


TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return [item.lower() for item in TOKEN_PATTERN.findall(text or "")]


def rough_token_count(text: str) -> int:
    return max(1, len(tokenize(text)))


def chunk_text(text: str, size: int = 420, overlap: int = 60) -> list[dict]:
    tokens = tokenize(text)
    if not tokens:
        return []
    chunks: list[dict] = []
    start = 0
    while start < len(tokens):
        end = min(len(tokens), start + size)
        chunk_tokens = tokens[start:end]
        chunks.append(
            {
                "index": len(chunks),
                "text": " ".join(chunk_tokens),
                "token_count": len(chunk_tokens),
                "start_token": start,
                "end_token": end,
            }
        )
        if end == len(tokens):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _cosine(a: Counter[str], b: Counter[str]) -> float:
    common = set(a) & set(b)
    numerator = sum(a[key] * b[key] for key in common)
    left = math.sqrt(sum(value * value for value in a.values()))
    right = math.sqrt(sum(value * value for value in b.values()))
    if not left or not right:
        return 0.0
    return numerator / (left * right)


def score_chunk(query_terms: Counter[str], text: str) -> float:
    chunk_terms = Counter(tokenize(text))
    if not chunk_terms:
        return 0.0
    overlap = sum(min(query_terms[key], chunk_terms[key]) for key in query_terms)
    bm25_like = overlap / max(1, sum(query_terms.values()))
    return round((_cosine(query_terms, chunk_terms) * 0.65) + (bm25_like * 0.35), 4)


async def index_document(
    db: AsyncSession,
    kb: KnowledgeBase,
    *,
    title: str,
    content: str,
    source_type: str = "manual",
    source_uri: str = "",
    file_asset_id: str | None = None,
) -> KnowledgeDocument:
    chunks = chunk_text(content, kb.config.get("chunk_size_tokens", 420), kb.config.get("chunk_overlap_tokens", 60))
    document = KnowledgeDocument(
        knowledge_base_id=kb.id,
        file_asset_id=file_asset_id,
        title=title,
        source_type=source_type,
        source_uri=source_uri,
        content=content,
        chunks=chunks,
        token_count=rough_token_count(content),
        chunk_count=len(chunks),
        index_status="indexed",
    )
    db.add(document)
    kb.document_count += 1
    kb.chunk_count += len(chunks)
    kb.total_tokens += document.token_count
    return document


async def retrieve(
    db: AsyncSession,
    kb: KnowledgeBase,
    *,
    query: str,
    top_k: int = 5,
    threshold: float = 0.0,
) -> list[dict]:
    query_terms = Counter(tokenize(query))
    if not query_terms:
        return []
    documents = (await db.scalars(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.knowledge_base_id == kb.id)
        .order_by(KnowledgeDocument.updated_at.desc())
    )).all()
    candidates: list[dict] = []
    for document in documents:
        for chunk in document.chunks or []:
            score = score_chunk(query_terms, chunk.get("text", ""))
            if score >= threshold:
                candidates.append(
                    {
                        "document_id": document.id,
                        "title": document.title,
                        "source_type": document.source_type,
                        "source_uri": document.source_uri,
                        "chunk_index": chunk.get("index", 0),
                        "score": score,
                        "text": chunk.get("text", ""),
                    }
                )
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[: max(1, min(top_k, 50))]


def build_context_snippet(results: Iterable[dict]) -> str:
    lines = ["## 参考知识", ""]
    for index, item in enumerate(results, start=1):
        lines.append(f"### [{index}] 来源：{item['title']}")
        lines.append(f"> {item['text'][:1200]}")
        lines.append("")
    return "\n".join(lines).strip()
