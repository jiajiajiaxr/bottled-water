import { useEffect, useState } from "react";
import { Flex, Typography } from "antd";
import { api } from "../../../../api";
import { buildPreviewDocument } from "../../../../lib/preview";
import type { WorkspaceArtifact } from "../../../../types";

const { Text } = Typography;

export function ArtifactPreviewFrame({
  artifact,
  draft,
  isPdfArtifact,
}: {
  artifact: WorkspaceArtifact;
  draft: string;
  isPdfArtifact: boolean;
}) {
  const [pdfPreview, setPdfPreview] = useState<{
    previewUrl?: string;
    previewText?: string;
  }>();
  const [loadingPdf, setLoadingPdf] = useState(false);
  const previewHtml =
    artifact.content?.preview_html ??
    artifact.content?.files?.["index.html"] ??
    draft;

  useEffect(() => {
    setPdfPreview(undefined);
    if (!isPdfArtifact || !artifact.id) return undefined;
    let cancelled = false;
    setLoadingPdf(true);
    api
      .exportArtifact(artifact.id, "pdf")
      .then((result) => {
        if (!cancelled) setPdfPreview(result);
      })
      .catch(() => {
        if (!cancelled) setPdfPreview({ previewText: "PDF 预览加载失败，请使用 PDF 主下载查看。" });
      })
      .finally(() => {
        if (!cancelled) setLoadingPdf(false);
      });
    return () => {
      cancelled = true;
    };
  }, [artifact.id, isPdfArtifact]);

  useEffect(() => {
    return () => {
      if (pdfPreview?.previewUrl?.startsWith("blob:")) URL.revokeObjectURL(pdfPreview.previewUrl);
    };
  }, [pdfPreview?.previewUrl]);

  if (isPdfArtifact) {
    if (loadingPdf) {
      return (
        <Flex className="preview-loading" align="center" justify="center">
          <Text type="secondary">PDF 预览加载中...</Text>
        </Flex>
      );
    }
    if (pdfPreview?.previewUrl) {
      return <iframe title="PDF artifact preview" className="pdf-preview-frame" src={pdfPreview.previewUrl} />;
    }
    if (pdfPreview?.previewText) {
      return <pre className="preview-text-fallback">{pdfPreview.previewText}</pre>;
    }
  }

  return (
    <iframe
      title="artifact preview"
      sandbox="allow-scripts"
      srcDoc={buildPreviewDocument(previewHtml)}
    />
  );
}
