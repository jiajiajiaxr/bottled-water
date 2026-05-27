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
  const [previewResult, setPreviewResult] = useState<{
    previewUrl?: string;
    previewText?: string;
    contentType: string;
    filename?: string;
  }>();
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => {
    setPreviewResult(undefined);
    if (!artifact.id || !isPdfArtifact) return undefined;
    let cancelled = false;
    setPreviewLoading(true);
    api
      .exportArtifact(artifact.id, "pdf")
      .then((result) => {
        if (!cancelled) setPreviewResult(result);
      })
      .catch(() => {
        if (!cancelled)
          setPreviewResult({
            contentType: "text/plain",
            previewText: "PDF 预览加载失败，可以使用上方 PDF 按钮下载查看。",
          });
      })
      .finally(() => {
        if (!cancelled) setPreviewLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [artifact.id, isPdfArtifact]);

  useEffect(() => {
    return () => {
      if (previewResult?.previewUrl?.startsWith("blob:"))
        URL.revokeObjectURL(previewResult.previewUrl);
    };
  }, [previewResult?.previewUrl]);

  if (previewLoading) {
    return (
      <Flex className="preview-loading" align="center" justify="center">
        <Text type="secondary">PDF 预览加载中...</Text>
      </Flex>
    );
  }

  if (isPdfArtifact && previewResult?.previewUrl) {
    return (
      <iframe
        title="PDF artifact preview"
        className="pdf-preview-frame"
        src={previewResult.previewUrl}
      />
    );
  }

  if (isPdfArtifact && previewResult?.previewText) {
    return (
      <pre className="preview-text-fallback">{previewResult.previewText}</pre>
    );
  }

  return (
    <iframe
      title="artifact preview"
      sandbox="allow-scripts"
      srcDoc={buildPreviewDocument(draft)}
    />
  );
}
