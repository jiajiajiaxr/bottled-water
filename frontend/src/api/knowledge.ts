import { get, post } from "./client";
import type { KnowledgeBase, KnowledgeDocument } from "@/types";

export async function knowledgeBases(): Promise<KnowledgeBase[]> {
  const result = await get<{ items: KnowledgeBase[] }>(
    "/knowledge-bases",
  );
  return result.items;
}

export async function createKnowledgeBase(payload: {
  name: string;
  description: string;
  scope: string;
  visibility: string;
}): Promise<KnowledgeBase> {
  return await post<KnowledgeBase>("/knowledge-bases", payload);
}

export async function importKnowledgeText(
  kbId: string,
  payload: { title: string; content: string },
): Promise<KnowledgeDocument> {
  return await post<KnowledgeDocument>(
    `/knowledge-bases/${kbId}/documents`,
    payload,
  );
}

export async function retrieveKnowledge(
  kbId: string,
  query: string,
): Promise<{
  items: Array<{ title: string; score: number; text: string }>;
  context: string;
}> {
  return await post<{
    items: Array<{ title: string; score: number; text: string }>;
    context: string;
  }>(`/knowledge-bases/${kbId}/retrieve`, { query, top_k: 5, mode: "hybrid" });
}
