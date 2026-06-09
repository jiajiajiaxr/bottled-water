import {
  app,
  BrowserView,
  BrowserWindow,
  clipboard,
  desktopCapturer,
  Tray,
  Menu,
  globalShortcut,
  ipcMain,
  Notification,
  nativeImage,
  screen,
  shell,
} from "electron";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rendererPath = path.join(__dirname, "../renderer/index.html");
const defaultConfigPath = path.join(__dirname, "../../config/default.json");
const iconPath = path.join(__dirname, "../../assets/icon.svg");
const TITLEBAR_HEIGHT = 36;

let mainWindow;
let titlebarView;
let webView;
let quickWindow;
let captureWindow;
let captureSession;
let tray;
let isQuitting = false;
let mainShell;
let activeShell;
const shellsByWebContentsId = new Map();

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

async function getConfig() {
  const defaults = await readJson(defaultConfigPath, {
    webAppUrl: "http://127.0.0.1:5174",
    apiBase: "http://127.0.0.1:8000/api/v1",
    globalShortcut: "Alt+Space",
    quickCaptureShortcut: "Alt+Shift+Space",
    closeToTray: true,
  });
  const userConfig = await readJson(userDataPath("config.json"), {});
  return {
    ...defaults,
    ...userConfig,
    webAppUrl:
      process.env.AGENTHUB_DESKTOP_WEB_URL ||
      userConfig.webAppUrl ||
      defaults.webAppUrl,
  };
}

async function saveConfig(patch) {
  const next = { ...(await getConfig()), ...(patch || {}) };
  await writeJson(userDataPath("config.json"), next);
  return next;
}

function viewPreferences() {
  return {
    preload: path.join(__dirname, "../preload/preload.js"),
    contextIsolation: true,
    nodeIntegration: false,
    sandbox: false,
  };
}

function registerShell(window, titlebar, web, { main = false } = {}) {
  const shell = { window, titlebar, web, main };
  shellsByWebContentsId.set(titlebar.webContents.id, shell);
  shellsByWebContentsId.set(web.webContents.id, shell);
  window.on("focus", () => {
    activeShell = shell;
  });
  window.on("closed", () => {
    shellsByWebContentsId.delete(titlebar.webContents.id);
    shellsByWebContentsId.delete(web.webContents.id);
    if (activeShell === shell) activeShell = mainShell;
  });
  if (main) {
    mainShell = shell;
    activeShell = shell;
  }
  return shell;
}

function shellForEvent(event) {
  return shellsByWebContentsId.get(event?.sender?.id) || activeShell || mainShell;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 980,
    minHeight: 680,
    title: "AgentHub",
    frame: false,
    backgroundColor: "#edf1f7",
    show: false,
    webPreferences: viewPreferences(),
  });

  titlebarView = new BrowserView({ webPreferences: viewPreferences() });
  webView = new BrowserView({ webPreferences: viewPreferences() });
  registerShell(mainWindow, titlebarView, webView, { main: true });
  mainWindow.addBrowserView(titlebarView);
  mainWindow.addBrowserView(webView);
  layoutViews();

  titlebarView.webContents.loadFile(rendererPath, { query: { mode: "titlebar" } });
  titlebarView.webContents.on("before-input-event", (_event, input) => {
    if (input.key === "F5") reloadWebApp();
  });

  webView.webContents.setWindowOpenHandler(({ url }) => {
    createDetachedWindow(url);
    return { action: "deny" };
  });
  webView.webContents.on("will-navigate", (event, url) => {
    if (!isTrustedNavigation(url)) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });
  webView.webContents.on("did-navigate", (_event, url) => {
    titlebarView?.webContents.send("desktop:navigation-state", navigationState(mainShell, url));
  });
  webView.webContents.on("did-navigate-in-page", (_event, url) => {
    titlebarView?.webContents.send("desktop:navigation-state", navigationState(mainShell, url));
  });
  webView.webContents.on("page-title-updated", (_event, title) => {
    titlebarView?.webContents.send("desktop:title-updated", title);
  });

  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.on("resize", layoutViews);
  mainWindow.on("maximize", () => titlebarView?.webContents.send("desktop:window-state", { maximized: true }));
  mainWindow.on("unmaximize", () => titlebarView?.webContents.send("desktop:window-state", { maximized: false }));
  mainWindow.on("close", async (event) => {
    const config = await getConfig();
    if (!isQuitting && config.closeToTray) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  loadWebApp().finally(() => mainWindow?.show());
}

function layoutViews() {
  if (!mainWindow || !titlebarView || !webView) return;
  const [width, height] = mainWindow.getContentSize();
  titlebarView.setBounds({ x: 0, y: 0, width, height: TITLEBAR_HEIGHT });
  titlebarView.setAutoResize({ width: true });
  webView.setBounds({ x: 0, y: TITLEBAR_HEIGHT, width, height: Math.max(0, height - TITLEBAR_HEIGHT) });
  webView.setAutoResize({ width: true, height: true });
}

async function loadWebApp() {
  const config = await getConfig();
  const url = normalizeUrl(config.webAppUrl);
  try {
    await webView.webContents.loadURL(url);
  } catch {
    await webView.webContents.loadFile(rendererPath, { query: { webAppUrl: url } });
  }
  titlebarView?.webContents.send("desktop:navigation-state", navigationState(mainShell, url));
}

async function insertTextIntoComposer(text, shell = activeShell || mainShell) {
  if (!shell?.web || !text) return false;
  shell.window.show();
  shell.window.focus();
  const script = `
    (() => {
      const text = ${JSON.stringify(text)};
      const selectors = [
        '[data-testid="message-input"] textarea',
        '[data-testid="message-input"]',
        '[aria-label="message-input"] textarea',
        'textarea[data-testid="message-input"]',
        'textarea[aria-label="message-input"]',
        '.composer-mentions textarea',
        '.ant-mentions textarea',
        '.composer textarea',
        '.composer [contenteditable="true"]',
        '[contenteditable="true"]',
        'textarea'
      ];
      const target = selectors.map((selector) => document.querySelector(selector)).find(Boolean);
      if (!target) return false;
      target.focus();
      if ("value" in target) {
        const previous = target.value ?? "";
        const next = previous ? previous + (previous.endsWith("\\n") ? "" : "\\n") + text : text;
        const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(target), "value")?.set;
        if (setter) setter.call(target, next);
        else target.value = next;
        target.dispatchEvent(new Event("input", { bubbles: true }));
        target.dispatchEvent(new Event("change", { bubbles: true }));
      } else {
        document.execCommand("insertText", false, text);
        target.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
      }
      return true;
    })();
  `;
  const ok = await shell.web.webContents.executeJavaScript(script, true).catch(() => false);
  if (!ok) {
    notify({
      title: "AgentHub Desktop",
      body: "没有找到当前聊天输入框，请先打开一个会话。",
    });
  }
  return Boolean(ok);
}

async function captureScreenQuestion(shell = activeShell || mainShell) {
  const targetShell = shell || activeShell || mainShell;
  try {
    const point = screen.getCursorScreenPoint();
    const display = screen.getDisplayNearestPoint(point);
    const sources = await desktopCapturer.getSources({
      types: ["screen"],
      thumbnailSize: {
        width: Math.max(800, display.size.width),
        height: Math.max(600, display.size.height),
      },
    });
    const source = sources.find((item) => item.display_id === String(display.id)) || sources[0];
    if (!source?.thumbnail || source.thumbnail.isEmpty()) {
      throw new Error("No screenshot source available");
    }
    openCaptureOverlay({
      targetShell,
      display,
      image: source.thumbnail,
    });
    return true;
  } catch {
    notify({
      title: "截图问答失败",
      body: "当前系统未能获取屏幕截图，请检查屏幕录制/截图权限。",
    });
    return false;
  }
}

function openCaptureOverlay({ targetShell, display, image }) {
  captureWindow?.close();
  captureSession = {
    targetShell,
    image,
    imageSize: image.getSize(),
    displayBounds: display.bounds,
  };
  captureWindow = new BrowserWindow({
    x: display.bounds.x,
    y: display.bounds.y,
    width: display.bounds.width,
    height: display.bounds.height,
    frame: false,
    resizable: false,
    movable: false,
    fullscreenable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    backgroundColor: "#000000",
    webPreferences: viewPreferences(),
  });
  captureWindow.setAlwaysOnTop(true, "screen-saver");
  captureWindow.loadFile(rendererPath, { query: { mode: "capture" } });
  captureWindow.webContents.once("did-finish-load", () => {
    captureWindow?.webContents.send("desktop:capture-start", {
      dataUrl: image.toDataURL(),
      width: display.bounds.width,
      height: display.bounds.height,
    });
  });
  captureWindow.on("closed", () => {
    captureWindow = undefined;
    captureSession = undefined;
  });
}

function cancelCapture() {
  captureWindow?.close();
  captureWindow = undefined;
  captureSession = undefined;
  return true;
}

function confirmCapture(selection) {
  if (!captureSession?.image || !captureSession?.targetShell || !selection) {
    return cancelCapture();
  }
  const { image, imageSize, displayBounds, targetShell } = captureSession;
  const scaleX = imageSize.width / Math.max(1, displayBounds.width);
  const scaleY = imageSize.height / Math.max(1, displayBounds.height);
  const crop = {
    x: clamp(Math.round(selection.x * scaleX), 0, imageSize.width - 1),
    y: clamp(Math.round(selection.y * scaleY), 0, imageSize.height - 1),
    width: clamp(Math.round(selection.width * scaleX), 1, imageSize.width),
    height: clamp(Math.round(selection.height * scaleY), 1, imageSize.height),
  };
  if (crop.width < 8 || crop.height < 8) {
    notify({
      title: "截图区域太小",
      body: "请重新框选一个更大的区域。",
    });
    return false;
  }
  const clipped = image.crop(crop);
  const png = clipped.toPNG();
  const capturedAt = new Date().toISOString();
  const filename = `agenthub-screenshot-${capturedAt.replace(/[:.]/g, "-")}.png`;
  targetShell.window.show();
  targetShell.window.focus();
  targetShell.web.webContents.send("desktop:screenshot-captured", {
    filename,
    contentType: "image/png",
    dataUrl: `data:image/png;base64,${png.toString("base64")}`,
    prompt: "请分析这张截图。",
    capturedAt,
  });
  captureWindow?.close();
  captureWindow = undefined;
  captureSession = undefined;
  notify({
    title: "截图已加入当前聊天",
    body: "截图正在上传为输入框附件，可直接发送给 Agent 分析。",
  });
  return true;
}

function reloadWebApp() {
  if (webView?.webContents.getURL()) {
    webView.webContents.reload();
  } else {
    loadWebApp();
  }
}

function createQuickWindow() {
  if (quickWindow && !quickWindow.isDestroyed()) return quickWindow;

  const display = screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
  const width = 640;
  const height = 188;
  quickWindow = new BrowserWindow({
    width,
    height,
    x: Math.round(display.workArea.x + (display.workArea.width - width) / 2),
    y: Math.round(display.workArea.y + 80),
    resizable: false,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    backgroundColor: "#00000000",
    webPreferences: viewPreferences(),
  });
  quickWindow.loadFile(rendererPath, { query: { mode: "quick" } });
  quickWindow.on("blur", () => quickWindow?.hide());
  return quickWindow;
}

function createDetachedWindow(url) {
  const child = new BrowserWindow({
    width: 960,
    height: 760,
    minWidth: 820,
    minHeight: 620,
    title: "AgentHub Conversation",
    frame: false,
    backgroundColor: "#edf1f7",
    webPreferences: viewPreferences(),
  });
  const childTitlebar = new BrowserView({ webPreferences: viewPreferences() });
  const childWeb = new BrowserView({ webPreferences: viewPreferences() });
  const childShell = registerShell(child, childTitlebar, childWeb);
  child.addBrowserView(childTitlebar);
  child.addBrowserView(childWeb);
  const layoutChild = () => {
    const [width, height] = child.getContentSize();
    childTitlebar.setBounds({ x: 0, y: 0, width, height: TITLEBAR_HEIGHT });
    childTitlebar.setAutoResize({ width: true });
    childWeb.setBounds({ x: 0, y: TITLEBAR_HEIGHT, width, height: Math.max(0, height - TITLEBAR_HEIGHT) });
    childWeb.setAutoResize({ width: true, height: true });
  };
  layoutChild();
  child.on("resize", layoutChild);
  child.on("maximize", () => childTitlebar.webContents.send("desktop:window-state", { maximized: true }));
  child.on("unmaximize", () => childTitlebar.webContents.send("desktop:window-state", { maximized: false }));
  childTitlebar.webContents.loadFile(rendererPath, { query: { mode: "titlebar" } });
  childWeb.webContents.setWindowOpenHandler(({ url: nextUrl }) => {
    createDetachedWindow(nextUrl);
    return { action: "deny" };
  });
  childWeb.webContents.on("did-navigate", (_event, nextUrl) => {
    childTitlebar.webContents.send("desktop:navigation-state", navigationState(childShell, nextUrl));
  });
  childWeb.webContents.on("did-navigate-in-page", (_event, nextUrl) => {
    childTitlebar.webContents.send("desktop:navigation-state", navigationState(childShell, nextUrl));
  });
  childWeb.webContents.on("page-title-updated", (_event, title) => {
    childTitlebar.webContents.send("desktop:title-updated", title);
  });
  childWeb.loadURL(url);
  return child;
}

function showMainWindow() {
  if (!mainWindow || mainWindow.isDestroyed()) createWindow();
  mainWindow.show();
  mainWindow.focus();
}

function toggleQuickWindow() {
  const win = createQuickWindow();
  if (win.isVisible()) {
    win.hide();
  } else {
    win.show();
    win.focus();
    win.webContents.send("desktop:quick-focus");
  }
}

function createTray() {
  const image = nativeImage.createFromPath(iconPath);
  tray = new Tray(image.isEmpty() ? nativeImage.createEmpty() : image);
  tray.setToolTip("AgentHub Desktop");
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "打开 AgentHub", click: showMainWindow },
      { label: "悬浮输入 Alt+Space", click: toggleQuickWindow },
      { label: "新建独立窗口", click: () => getConfig().then((config) => createDetachedWindow(normalizeUrl(config.webAppUrl))) },
      { type: "separator" },
      {
        label: "退出",
        click: () => {
          isQuitting = true;
          app.quit();
        },
      },
    ]),
  );
  tray.on("click", showMainWindow);
}

async function registerShortcuts() {
  globalShortcut.unregisterAll();
  const config = await getConfig();
  globalShortcut.register(config.globalShortcut || "Alt+Space", toggleQuickWindow);
  globalShortcut.register(config.quickCaptureShortcut || "Alt+Shift+Space", captureScreenQuestion);
}

function navigationState(shell = mainShell, url = shell?.web.webContents.getURL()) {
  return {
    url,
    canGoBack: Boolean(shell?.web.webContents.canGoBack()),
    canGoForward: Boolean(shell?.web.webContents.canGoForward()),
    maximized: Boolean(shell?.window.isMaximized()),
  };
}

function normalizeUrl(value) {
  const url = String(value || "http://127.0.0.1:5174").trim();
  return /^https?:\/\//i.test(url) ? url : `http://${url}`;
}

function isTrustedNavigation(url) {
  try {
    const target = new URL(url);
    return ["http:", "https:", "file:"].includes(target.protocol);
  } catch {
    return false;
  }
}

app.whenReady().then(async () => {
  Menu.setApplicationMenu(null);
  createWindow();
  createTray();
  await registerShortcuts();
  app.on("activate", showMainWindow);
});

app.on("before-quit", () => {
  isQuitting = true;
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
});

app.on("window-all-closed", () => {
  if (process.platform === "darwin") return;
  app.quit();
});

ipcMain.handle("desktop:get-config", getConfig);
ipcMain.handle("desktop:save-config", async (_event, patch) => {
  const next = await saveConfig(patch);
  await registerShortcuts();
  return next;
});
ipcMain.handle("desktop:reload-web", async () => {
  reloadWebApp();
  return true;
});
ipcMain.handle("desktop:open-main", (_event, payload) => {
  const targetShell = activeShell || mainShell;
  targetShell?.window.show();
  targetShell?.window.focus();
  if (payload?.text) {
    insertTextIntoComposer(payload.text, targetShell);
  }
  return true;
});
ipcMain.handle("desktop:quick-input", () => {
  toggleQuickWindow();
  return true;
});
ipcMain.handle("desktop:screen-question", (_event) => captureScreenQuestion(shellForEvent(_event)));
ipcMain.handle("desktop:capture-payload", () => {
  if (!captureSession?.image || !captureSession?.displayBounds) return null;
  return {
    dataUrl: captureSession.image.toDataURL(),
    width: captureSession.displayBounds.width,
    height: captureSession.displayBounds.height,
  };
});
ipcMain.handle("desktop:capture-confirm", (_event, selection) => confirmCapture(selection));
ipcMain.handle("desktop:capture-cancel", cancelCapture);
ipcMain.handle("desktop:copy-url", (_event) => {
  const shell = shellForEvent(_event);
  const url = shell?.web.webContents.getURL() || "";
  if (url) clipboard.writeText(url);
  notify({
    title: "已复制当前链接",
    body: url || "当前没有可复制的链接。",
  });
  return url;
});
ipcMain.handle("desktop:new-window", async (_event, url) => {
  const config = await getConfig();
  createDetachedWindow(url || normalizeUrl(config.webAppUrl));
  return true;
});
ipcMain.handle("desktop:navigation", (_event, action) => {
  const shell = shellForEvent(_event);
  if (!shell?.web) return navigationState();
  if (action === "back" && shell.web.webContents.canGoBack()) shell.web.webContents.goBack();
  if (action === "forward" && shell.web.webContents.canGoForward()) shell.web.webContents.goForward();
  if (action === "reload") shell.web.webContents.reload();
  return navigationState(shell);
});
ipcMain.handle("desktop:window-control", (_event, action) => {
  const shell = shellForEvent(_event);
  const targetWindow = shell?.window || mainWindow;
  if (!targetWindow) return false;
  if (action === "minimize") targetWindow.minimize();
  if (action === "maximize") {
    if (targetWindow.isMaximized()) {
      targetWindow.unmaximize();
    } else {
      targetWindow.maximize();
    }
  }
  if (action === "close") targetWindow.close();
  return true;
});
ipcMain.handle("desktop:notify", (_event, payload) => {
  return notify(payload);
});

function notify(payload) {
  if (Notification.isSupported()) {
    new Notification({
      title: payload?.title || "AgentHub",
      body: payload?.body || "任务状态已更新",
    }).show();
  }
  return true;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
