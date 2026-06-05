import React, { useMemo, useState, type ReactNode } from "react";
import { stripInternalAgentOutput } from "./message";
import { renderInlineMarkdown } from "./markdown-inline";
import type { CodeRunRecord } from "@/types";

type RunCodeHandler = (
  index: number,
  language: string,
  code: string,
) => Promise<CodeRunRecord>;

interface MarkdownContentProps {
  text: string;
  onRunCode?: RunCodeHandler;
  codeRunResults?: Record<string, CodeRunRecord>;
}

const RUNNABLE_LANGUAGES = new Set([
  "python",
  "py",
  "javascript",
  "js",
  "node",
  "bash",
  "sh",
  "shell",
]);

function looksLikeInternalFence(
  fenceName: string | undefined,
  code: string[],
): boolean {
  if (fenceName === "status_report" || fenceName === "status") return true;
  const firstMeaningful = code.find((line) => line.trim().length > 0);
  if (!firstMeaningful) return false;
  const first = firstMeaningful.trim().toLowerCase();
  if (first === "status_report" || first === "status") return true;
  const body = code.join("\n").toLowerCase();
  return (
    body.trim().startsWith("{") &&
    /"state"\s*:/.test(body) &&
    /"(?:will|rationale|blockers|priority|confidence)"\s*:/.test(body)
  );
}

function MarkdownContentComponent({
  text,
  onRunCode,
  codeRunResults,
}: MarkdownContentProps) {
  const blocks = useMemo(() => {
    const result: ReactNode[] = [];
    const paragraph: string[] = [];
    const visibleText = stripInternalAgentOutput(text);
    const lines = visibleText.split(/\r?\n/);
    let codeIndex = 0;
    const flushParagraph = () => {
      if (!paragraph.length) return;
      result.push(
        <p key={`p-${result.length}`}>
          {renderInlineMarkdown(paragraph.join(" "))}
        </p>,
      );
      paragraph.length = 0;
    };
    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index];
      if (line.trim().startsWith("```")) {
        flushParagraph();
        const fenceName = line
          .trim()
          .replace(/^```\s*/, "")
          .split(/\s+/)[0]
          ?.toLowerCase();
        const code: string[] = [];
        index += 1;
        while (index < lines.length && !lines[index].trim().startsWith("```")) {
          code.push(lines[index]);
          index += 1;
        }
        const closed = index < lines.length;
        if (looksLikeInternalFence(fenceName, code)) continue;
        const currentCodeIndex = codeIndex;
        codeIndex += 1;
        result.push(
          <CodeBlock
            key={`code-${currentCodeIndex}`}
            index={currentCodeIndex}
            language={fenceName || "text"}
            code={code.join("\n")}
            streaming={!closed}
            onRunCode={onRunCode}
            result={codeRunResults?.[String(currentCodeIndex)]}
          />,
        );
        continue;
      }
      if (!line.trim()) {
        flushParagraph();
        continue;
      }
      const heading = /^(#{1,4})\s+(.+)$/.exec(line);
      if (heading) {
        flushParagraph();
        const level = Math.min(heading[1].length, 4);
        const content = renderInlineMarkdown(heading[2]);
        if (level === 1)
          result.push(<h3 key={`h-${result.length}`}>{content}</h3>);
        else if (level === 2)
          result.push(<h4 key={`h-${result.length}`}>{content}</h4>);
        else if (level === 3)
          result.push(<h5 key={`h-${result.length}`}>{content}</h5>);
        else result.push(<h6 key={`h-${result.length}`}>{content}</h6>);
        continue;
      }
      const listItems: string[] = [];
      if (/^\s*[-*]\s+/.test(line)) {
        flushParagraph();
        while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
          listItems.push(lines[index].replace(/^\s*[-*]\s+/, ""));
          index += 1;
        }
        index -= 1;
        result.push(
          <ul key={`ul-${result.length}`}>
            {listItems.map((item, itemIndex) => (
              <li key={itemIndex}>{renderInlineMarkdown(item)}</li>
            ))}
          </ul>,
        );
        continue;
      }
      if (/^\s*\d+[.)]\s+/.test(line)) {
        flushParagraph();
        while (index < lines.length && /^\s*\d+[.)]\s+/.test(lines[index])) {
          listItems.push(lines[index].replace(/^\s*\d+[.)]\s+/, ""));
          index += 1;
        }
        index -= 1;
        result.push(
          <ol key={`ol-${result.length}`}>
            {listItems.map((item, itemIndex) => (
              <li key={itemIndex}>{renderInlineMarkdown(item)}</li>
            ))}
          </ol>,
        );
        continue;
      }
      paragraph.push(line.trim());
    }
    flushParagraph();
    return result;
  }, [codeRunResults, onRunCode, text]);

  return (
    <div className="markdown-content">
      {blocks.length ? (
        blocks
      ) : (
        <p className="typing-placeholder">正在组织语言...</p>
      )}
    </div>
  );
}

function CodeBlock({
  index,
  language,
  code,
  streaming,
  onRunCode,
  result,
}: {
  index: number;
  language: string;
  code: string;
  streaming: boolean;
  onRunCode?: RunCodeHandler;
  result?: CodeRunRecord;
}) {
  const [running, setRunning] = useState(false);
  const [localResult, setLocalResult] = useState<CodeRunRecord | undefined>();
  const visibleResult = result ?? localResult;
  const canRun = RUNNABLE_LANGUAGES.has(language) && Boolean(onRunCode);
  const handleRun = async () => {
    if (!onRunCode || running || !code.trim()) return;
    setRunning(true);
    try {
      const next = await onRunCode(index, language, code);
      setLocalResult(next);
    } catch (error) {
      setLocalResult({
        status: "failed",
        stdout: "",
        stderr:
          error instanceof Error
            ? error.message
            : "\u4ee3\u7801\u8fd0\u884c\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002",
        exit_code: -1,
        duration_ms: 0,
      });
    } finally {
      setRunning(false);
    }
  };
  return (
    <div className="markdown-code-block" data-testid="markdown-code-block">
      <div className="markdown-code-head">
        <span>{language || "text"}</span>
        {streaming && (
          <span className="markdown-code-streaming">
            {"\u751f\u6210\u4e2d"}
          </span>
        )}
        {canRun && (
          <button
            type="button"
            className="markdown-code-run"
            disabled={running || !code.trim()}
            onClick={handleRun}
          >
            {running ? "\u8fd0\u884c\u4e2d..." : "\u8fd0\u884c"}
          </button>
        )}
      </div>
      <pre>
        <code>{code}</code>
      </pre>
      {visibleResult && <CodeRunResultView result={visibleResult} />}
    </div>
  );
}

function CodeRunResultView({ result }: { result: CodeRunRecord }) {
  const ok = String(result.status || "").toLowerCase() === "succeeded";
  return (
    <div
      className={`markdown-code-result ${ok ? "succeeded" : "failed"}`}
      data-testid="code-run-result"
    >
      <div className="markdown-code-result-meta">
        <span>{ok ? "\u6267\u884c\u6210\u529f" : "\u6267\u884c\u5931\u8d25"}</span>
        <span>exit_code: {String(result.exit_code ?? -1)}</span>
        <span>{String(result.duration_ms ?? 0)}ms</span>
      </div>
      {result.stdout ? (
        <pre className="markdown-code-output">{result.stdout}</pre>
      ) : null}
      {result.stderr ? (
        <pre className="markdown-code-error">{result.stderr}</pre>
      ) : null}
    </div>
  );
}

export const MarkdownContent = React.memo(MarkdownContentComponent);
