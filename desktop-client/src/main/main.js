import { app, BrowserWindow, dialog, ipcMain, Notification, shell } from "electron";
import { spawn } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rendererPath = path.join(__dirname, "../renderer/index.html");

let mainWindow;
let agentProcess;
let agentStatus = {
  running: false,
  pid: null,
  startedAt: null,
  logs: [],
};

function userDataPath(...segments) {
  return path.join(app.getPath("userData"), ...segments);
}

async function ensureDir(target) {
  await fs.mkdir(target, { recursive: true });
}

async function readJson(file, fallback) {
  try {
    return JSON.parse(await fs.readFile(file, "utf-8"));
  } catch {
    return fallback;
  }
}

async function writeJson(file, value) {
  await ensureDir(path.dirname(file));
  await fs.writeFile(file, JSON.stringify(value, null, 2), "utf-8");
}

async function vaultKey() {
  const keyPath = userDataPath("secure-vault", "vault.key");
  await ensureDir(path.dirname(keyPath));
  try {
    return await fs.readFile(keyPath);
  } catch {
    const key = crypto.randomBytes(32);
    await fs.writeFile(keyPath, key);
    return key;
  }
}

async function vaultIndex() {
  return readJson(userDataPath("secure-vault", "index.json"), []);
}

async function saveVaultIndex(items) {
  await writeJson(userDataPath("secure-vault", "index.json"), items);
}

async function sha256(buffer) {
  return crypto.createHash("sha256").update(buffer).digest("hex");
}

async function encryptFile(filePath) {
  const key = await vaultKey();
  const raw = await fs.readFile(filePath);
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv("aes-256-gcm", key, iv);
  const encrypted = Buffer.concat([cipher.update(raw), cipher.final()]);
  const tag = cipher.getAuthTag();
  const id = crypto.randomUUID();
  const stat = await fs.stat(filePath);
  const filename = path.basename(filePath);
  const encryptedPath = userDataPath("secure-vault", `${id}.bin`);

  await fs.writeFile(encryptedPath, Buffer.concat([iv, tag, encrypted]));

  const item = {
    id,
    filename,
    size: stat.size,
    checksum: await sha256(raw),
    encrypted_path: encryptedPath,
    imported_at: new Date().toISOString(),
    classification: classifyFile(filename),
    source_hint: path.dirname(filePath),
  };
  const index = await vaultIndex();
  index.unshift(item);
  await saveVaultIndex(index);
  return item;
}

async function decryptVaultItem(id) {
  const index = await vaultIndex();
  const item = index.find((entry) => entry.id === id);
  if (!item) throw new Error("Vault file not found.");

  const key = await vaultKey();
  const payload = await fs.readFile(item.encrypted_path);
  const iv = payload.subarray(0, 12);
  const tag = payload.subarray(12, 28);
  const body = payload.subarray(28);
  const decipher = crypto.createDecipheriv("aes-256-gcm", key, iv);
  decipher.setAuthTag(tag);
  const raw = Buffer.concat([decipher.update(body), decipher.final()]);
  return { item, raw };
}

function classifyFile(filename) {
  const ext = path.extname(filename).toLowerCase();
  if ([".doc", ".docx", ".pdf", ".ppt", ".pptx", ".xls", ".xlsx"].includes(ext)) {
    return "office";
  }
  if ([".js", ".ts", ".tsx", ".py", ".java", ".go", ".rs", ".md"].includes(ext)) {
    return "code";
  }
  if ([".png", ".jpg", ".jpeg", ".webp", ".gif"].includes(ext)) {
    return "visual";
  }
  return "general";
}

function appendAgentLog(line) {
  agentStatus.logs.unshift(line);
  agentStatus.logs = agentStatus.logs.slice(0, 80);
  mainWindow?.webContents.send("agent:log", line);
}

function startAgentProcess() {
  if (agentProcess) return agentStatus;

  const workerPath = path.join(__dirname, "agent-worker.js");
  agentProcess = spawn(process.execPath, [workerPath], {
    stdio: ["ignore", "pipe", "pipe"],
    env: {
      ...process.env,
      AGENTHUB_DESKTOP_WORKER: "1",
    },
  });

  agentStatus = {
    running: true,
    pid: agentProcess.pid,
    startedAt: new Date().toISOString(),
    logs: agentStatus.logs,
  };

  agentProcess.stdout.on("data", (chunk) => {
    for (const line of chunk.toString("utf-8").trim().split(/\r?\n/)) {
      if (line) appendAgentLog(line);
    }
  });
  agentProcess.stderr.on("data", (chunk) => appendAgentLog(chunk.toString("utf-8")));
  agentProcess.on("exit", (code) => {
    appendAgentLog(JSON.stringify({ event: "agent.exit", detail: { code } }));
    agentProcess = undefined;
    agentStatus = {
      ...agentStatus,
      running: false,
      pid: null,
    };
    mainWindow?.webContents.send("agent:status", agentStatus);
  });

  return agentStatus;
}

function stopAgentProcess() {
  if (!agentProcess) return agentStatus;
  agentProcess.kill();
  return {
    ...agentStatus,
    running: false,
  };
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1320,
    height: 860,
    minWidth: 1080,
    minHeight: 720,
    title: "AgentHub Desktop",
    backgroundColor: "#f4f0e8",
    webPreferences: {
      preload: path.join(__dirname, "../preload/preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  mainWindow.loadFile(rendererPath);
}

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  if (agentProcess) agentProcess.kill();
});

ipcMain.handle("desktop:get-state", async () => ({
  vault: await vaultIndex(),
  agent: agentStatus,
  apiBase: "http://127.0.0.1:8000/api/v1",
}));

ipcMain.handle("desktop:pick-files", async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "选择要加密纳管的本地文件",
    properties: ["openFile", "multiSelections"],
  });
  if (result.canceled) return [];
  return Promise.all(result.filePaths.map(encryptFile));
});

ipcMain.handle("desktop:preview-vault-file", async (_event, id) => {
  const { item, raw } = await decryptVaultItem(id);
  const textLike = /\.(txt|md|json|csv|log|js|ts|tsx|py|html|css)$/i.test(item.filename);
  return {
    item,
    previewText: textLike ? raw.toString("utf-8").slice(0, 12000) : "",
    previewNote: textLike ? "" : "该文件已加密纳管，当前类型建议通过 Web 主端成果预览或原生应用打开。",
  };
});

ipcMain.handle("desktop:show-item", async (_event, id) => {
  const index = await vaultIndex();
  const item = index.find((entry) => entry.id === id);
  if (!item) return false;
  await shell.showItemInFolder(item.encrypted_path);
  return true;
});

ipcMain.handle("desktop:notify", (_event, payload) => {
  if (Notification.isSupported()) {
    new Notification({
      title: payload?.title || "AgentHub",
      body: payload?.body || "任务状态已更新",
    }).show();
  }
  return true;
});

ipcMain.handle("agent:start", () => startAgentProcess());
ipcMain.handle("agent:stop", () => stopAgentProcess());
ipcMain.handle("agent:status", () => agentStatus);

ipcMain.handle("api:health", async (_event, apiBase) => {
  const target = `${apiBase || "http://127.0.0.1:8000/api/v1"}/health`;
  const response = await fetch(target);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
});
