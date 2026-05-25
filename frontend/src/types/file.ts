export interface UploadedFile {
  id: string;
  file_id?: string;
  filename: string;
  original_filename: string;
  content_type: string;
  size: number;
  purpose: string;
  parse_status: string;
  public_url?: string;
  metadata?: Record<string, unknown>;
  created_at: string;
}
