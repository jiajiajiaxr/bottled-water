import { request } from "./client";
import { demoKnowledgeBases } from "../mock";
import type { KnowledgeBase, KnowledgeDocument } from "../types";

export async function knowledgeBases(): Promise<KnowledgeBase[]> {
  try {
    const result = await request<{ items: KnowledgeBase[] }>(
      "/knowledge-bases",
    );
    return result.items;
  } catch {
    return demoKnowledgeBases;
  }
}

export async function createKnowledgeBase(payload: {
  name: string;
  description: string;
  scope: string;
  visibility: string;
}): Promise<KnowledgeBase> {
  try {
    return await request<KnowledgeBase>("/knowledge-bases", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  } catch {
    return {
      id: `kb-${Date.now()}`,
      document_count: 0,
      chunk_count: 0,
      total_tokens: 0,
      status: "ready",
      ...payload,
    };
  }
}

export async function importKnowledgeText(
  kbId: string,
  payload: { title: string; content: string },
): Promise<KnowledgeDocument> {
  return await request<KnowledgeDocument>(
    `/knowledge-bases/${kbId}/documents`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function retrieveKnowledge(
  kbId: string,
  query: string,
): Promise<{
  items: Array<{ title: string; score: number; text: string }>;
  context: string;
}> {
  try {
    return await request<{
      items: Array<{ title: string; score: number; text: string }>;
      context: string;
    }>(`/knowledge-bases/${kbId}/retrieve`, {
      method: "POST",
      body: JSON.stringify({ query, top_k: 5, mode: "hybrid" }),
    });
  } catch {
    return { items: [], context: "暂无检索结果" };
  }
}
