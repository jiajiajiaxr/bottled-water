import { Empty, Typography } from "antd";
import type { WorkspaceFileNode, WorkspaceFilePreview } from "../../types";

const { Text } = Typography;

export type PreviewState = {
  node: WorkspaceFileNode;
  payload: WorkspaceFilePreview;
  objectUrl?: string;
};

export function WorkspaceFilePreviewView({ preview }: { preview: PreviewState }) {
  const payload = preview.payload;
  const text = payload.text ?? payload.preview_text ?? "";
  if (payload.mode === "image" && preview.objectUrl) {
    return (
      <img
        className="workspace-file-preview-image"
        src={preview.objectUrl}
        alt={preview.node.display_name ?? preview.node.name}
      />
    );
  }
  if (payload.mode === "pdf" && preview.objectUrl) {
    return <iframe title="workspace-file-pdf-preview" className="workspace-file-preview-frame" src={preview.objectUrl} />;
  }
  if (payload.mode === "html") {
    return <iframe title="workspace-file-html-preview" className="workspace-file-preview-frame" srcDoc={text} />;
  }
  if (payload.mode === "office_text") {
    return (
      <div className="workspace-file-preview-office">
        <Text type="secondary">Office 文件暂以文本摘要预览；如需完整格式，请下载原文件打开。</Text>
        <pre className="workspace-file-preview-text">{text || "未提取到可预览文本。"}</pre>
      </div>
    );
  }
  if (payload.mode === "binary") {
    return <Empty description="该文件暂不支持在线预览，请下载查看。" />;
  }
  return <pre className="workspace-file-preview-text">{text || "预览失败：未返回可显示内容。"}</pre>;
}
