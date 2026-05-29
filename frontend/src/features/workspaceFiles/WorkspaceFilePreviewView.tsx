import { Empty, Typography } from "antd";
import type { WorkspaceFileNode, WorkspaceFilePreview } from "../../types";

const { Text } = Typography;

export type PreviewState = {
  node: WorkspaceFileNode;
  payload: WorkspaceFilePreview;
  objectUrl?: string;
  error?: string;
};

export function WorkspaceFilePreviewView({ preview }: { preview: PreviewState }) {
  const payload = preview.payload;
  const text = payload.text ?? payload.preview_text ?? "";
  if (preview.error) {
    return <Empty description={preview.error} />;
  }
  if (payload.mode === "image") {
    return preview.objectUrl ? (
      <img
        className="workspace-file-preview-image"
        src={preview.objectUrl}
        alt={preview.node.display_name ?? preview.node.name}
      />
    ) : (
      <Empty description="图片文件下载失败，无法在线预览。" />
    );
  }
  if (payload.mode === "pdf") {
    return preview.objectUrl ? (
      <iframe title="workspace-file-pdf-preview" className="workspace-file-preview-frame" src={preview.objectUrl} />
    ) : (
      <Empty description="PDF 文件下载失败，无法在线预览。" />
    );
  }
  if (payload.mode === "html") {
    return text ? (
      <iframe title="workspace-file-html-preview" className="workspace-file-preview-frame" srcDoc={text} />
    ) : (
      <Empty description="HTML 预览内容为空，请下载原文件查看。" />
    );
  }
  if (payload.mode === "office_text") {
    return (
      <div className="workspace-file-preview-office">
        <Text type="secondary">Office 文件暂以文本摘要预览；如需完整格式，请下载原文件打开。</Text>
        {text ? (
          <pre className="workspace-file-preview-text">{text}</pre>
        ) : (
          <Empty description="未提取到可预览文本，请下载原文件查看。" />
        )}
      </div>
    );
  }
  if (payload.mode === "binary") {
    return <Empty description="不支持在线预览，请下载原文件。" />;
  }
  return text ? (
    <pre className="workspace-file-preview-text">{text}</pre>
  ) : (
    <Empty description="文件为空或暂未提取到可预览文本，请下载原文件查看。" />
  );
}
