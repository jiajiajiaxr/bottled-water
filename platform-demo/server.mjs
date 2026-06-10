import crypto from "node:crypto";
import fs from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.join(__dirname, "public");
const host = process.env.AGENTHUB_DEMO_HOST || "127.0.0.1";
const port = Number(process.env.AGENTHUB_DEMO_PORT || 4188);
const backendBase = process.env.AGENTHUB_BACKEND_API || "http://127.0.0.1:8000/api/v1";

const runs = new Map();
let latestArtifact = createArtifact(
  "artifact-initial",
  "等待运行后生成成果预览。本页面也可以直接静态发布到 GitHub Pages。",
);

const server = http.createServer(async (request, response) => {
  try {
    const url = new URL(request.url || "/", `http://${request.headers.host}`);

    if (url.pathname === "/health") {
      return json(response, 200, {
        status: "ok",
        service: "agenthub-platform-demo",
        mode: "local-api",
        time: new Date().toISOString(),
      });
    }

    if (url.pathname === "/api/status") {
      return json(response, 200, await statusPayload());
    }

    if (url.pathname === "/api/runs" && request.method === "POST") {
      const run = createRun();
      runs.set(run.id, run);
      driveRun(run);
      return json(response, 201, run);
    }

    const runMatch = /^\/api\/runs\/([^/]+)$/.exec(url.pathname);
    if (runMatch) {
      const run = runs.get(runMatch[1]);
      return run ? json(response, 200, run) : json(response, 404, { error: "run_not_found" });
    }

    const eventsMatch = /^\/api\/runs\/([^/]+)\/events$/.exec(url.pathname);
    if (eventsMatch) {
      const run = runs.get(eventsMatch[1]);
      if (!run) return json(response, 404, { error: "run_not_found" });
      return streamRunEvents(request, response, run);
    }

    if (url.pathname === "/api/artifacts/latest") {
      return json(response, 200, latestArtifact);
    }

    return staticFile(response, url.pathname);
  } catch (error) {
    console.error(error);
    return json(response, 500, {
      error: "internal_error",
      message: error instanceof Error ? error.message : String(error),
    });
  }
});

server.listen(port, host, () => {
  console.log(`AgentHub platform demo listening at http://${host}:${port}`);
  console.log(`Static publishing directory: ${publicDir}`);
  console.log(`Backend probe target: ${backendBase}`);
});

function createRun() {
  const now = new Date().toISOString();
  return {
    id: `run-${crypto.randomUUID().slice(0, 8)}`,
    status: "queued",
    progress: 0,
    created_at: now,
    updated_at: now,
    current_step: "等待调度",
    events: [
      {
        type: "run.created",
        message: "本地实操 Demo 任务已创建。",
        at: now,
      },
    ],
    agents: [
      { name: "Team Leader", status: "queued", work_product: "" },
      { name: "Frontend Worker", status: "queued", work_product: "" },
      { name: "Backend Worker", status: "queued", work_product: "" },
      { name: "QA Reviewer", status: "queued", work_product: "" },
    ],
  };
}

function driveRun(run) {
  const timeline = [
    [600, 8, "Team Leader 正在拆解任务", "Team Leader", "running", "生成 Web、桌面、移动三端联调计划。"],
    [1300, 23, "Frontend Worker 正在生成操作界面", "Frontend Worker", "running", "构建 IM、成果预览和部署核验演示流。"],
    [2100, 42, "Backend Worker 正在准备调试 API", "Backend Worker", "running", "提供健康检查、运行记录和事件流。"],
    [3100, 66, "QA Reviewer 正在核验部署闭环", "QA Reviewer", "running", "验证本地一键启动和预览卡片。"],
    [4300, 88, "正在生成成果预览卡", "Frontend Worker", "completed", "完成平台实操 Demo 页面。"],
    [5600, 100, "任务完成", "QA Reviewer", "completed", "Demo 已可本地调试、预览和验收。"],
  ];

  for (const [delay, progress, step, agentName, agentStatus, product] of timeline) {
    setTimeout(() => {
      run.progress = progress;
      run.current_step = step;
      run.updated_at = new Date().toISOString();
      run.status = progress >= 100 ? "completed" : "running";
      if (progress >= 100) {
        run.agents = run.agents.map((item) => ({
          ...item,
          status: item.work_product ? "completed" : item.status,
        }));
      }

      const agent = run.agents.find((item) => item.name === agentName);
      if (agent) {
        agent.status = agentStatus;
        agent.work_product = product;
      }

      const event = {
        type: progress >= 100 ? "run.completed" : "run.progress",
        message: `${step}: ${product}`,
        at: run.updated_at,
      };
      run.events.push(event);
      run.listeners?.forEach((listener) => listener(event, run));

      if (progress >= 100) {
        latestArtifact = createArtifact(
          `artifact-${run.id}`,
          "平台实操 Demo 已生成，可用于 GitHub Pages 静态演示和本地一键部署调试。",
        );
      }
    }, delay);
  }
}

function streamRunEvents(request, response, run) {
  response.writeHead(200, {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
    "Access-Control-Allow-Origin": "*",
  });

  const send = (event, snapshot = run) => {
    response.write(`event: ${event.type}\n`);
    response.write(`data: ${JSON.stringify({ event, run: snapshot })}\n\n`);
  };

  for (const event of run.events) send(event);

  run.listeners ||= new Set();
  run.listeners.add(send);
  request.on("close", () => run.listeners?.delete(send));
}

async function statusPayload() {
  const backend = await probeBackend();
  return {
    demo: {
      status: "ok",
      mode: "local-api",
      uptime_seconds: Math.round(process.uptime()),
    },
    backend,
    clients: [
      {
        name: "Web 云端主力办公端",
        status: backend.online ? "connected" : "demo-data",
        capability: "IM 协同、代码编辑、成果预览、一键部署",
      },
      {
        name: "桌面本地专属客户端",
        status: "ready",
        capability: "本地加密文件、系统通知、后台 Agent 进程",
      },
      {
        name: "移动端轻量化便捷端口",
        status: "ready",
        capability: "会话查看、成果预览、进度跟踪",
      },
    ],
    active_runs: Array.from(runs.values()).slice(-5),
  };
}

async function probeBackend() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 1200);
  try {
    const response = await fetch(`${backendBase}/health`, { signal: controller.signal });
    const payload = await response.json();
    return {
      online: response.ok,
      base_url: backendBase,
      status: payload?.data?.status || payload?.status || "responded",
      provider: payload?.data?.provider || payload?.provider || "",
    };
  } catch {
    return {
      online: false,
      base_url: backendBase,
      status: "offline",
      provider: "",
    };
  } finally {
    clearTimeout(timer);
  }
}

function createArtifact(id, summary) {
  return {
    id,
    title: "AgentHub 平台实操 Demo 成果",
    kind: "html",
    summary,
    preview_html: `
      <article class="artifact-document">
        <h1>AgentHub 平台实操 Demo</h1>
        <p>${escapeHtml(summary)}</p>
        <ul>
          <li>GitHub Pages 纯静态演示</li>
          <li>本地一键启动联调</li>
          <li>健康检查与后端探测</li>
          <li>多 Agent 任务流模拟</li>
          <li>成果预览与部署核验</li>
        </ul>
      </article>
    `,
  };
}

async function staticFile(response, requestPath) {
  const safePath = requestPath === "/" ? "/index.html" : requestPath;
  const normalized = path.normalize(decodeURIComponent(safePath)).replace(/^(\.\.[/\\])+/, "");
  const filePath = path.join(publicDir, normalized);
  if (!filePath.startsWith(publicDir)) {
    return json(response, 403, { error: "forbidden" });
  }

  try {
    const content = await fs.readFile(filePath);
    response.writeHead(200, {
      "Content-Type": contentType(filePath),
      "Cache-Control": "no-cache",
    });
    response.end(content);
  } catch {
    response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    response.end("Not found");
  }
}

function json(response, status, payload) {
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Access-Control-Allow-Origin": "*",
  });
  response.end(JSON.stringify(payload, null, 2));
}

function contentType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  return {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
  }[ext] || "application/octet-stream";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
