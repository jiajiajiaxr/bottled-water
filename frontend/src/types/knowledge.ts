export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  scope: string;
  visibility: string;
  document_count: number;
  chunk_count: number;
  total_tokens: number;
  status: string;
}

export interface KnowledgeDocument {
  id: string;
  title: string;
  source_type: string;
  token_count: number;
  chunk_count: number;
  index_status: string;
  created_at: string;
}
