import { buildPreviewDocument } from "../../../../lib/preview";
import type { WorkspaceArtifact } from "../../../../types";

export function ArtifactPreviewFrame({
  artifact,
  draft,
}: {
  artifact: WorkspaceArtifact;
  draft: string;
  isPdfArtifact: boolean;
}) {
  const previewHtml =
    artifact.content?.preview_html ??
    artifact.content?.files?.["index.html"] ??
    draft;

  return (
    <iframe
      title="artifact preview"
      sandbox="allow-scripts"
      srcDoc={buildPreviewDocument(previewHtml)}
    />
  );
}
