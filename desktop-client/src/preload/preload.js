import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("agentHubDesktop", {
  getConfig: () => ipcRenderer.invoke("desktop:get-config"),
  saveConfig: (patch) => ipcRenderer.invoke("desktop:save-config", patch),
  reloadWeb: () => ipcRenderer.invoke("desktop:reload-web"),
  openMain: (payload) => ipcRenderer.invoke("desktop:open-main", payload),
  quickInput: () => ipcRenderer.invoke("desktop:quick-input"),
  screenQuestion: () => ipcRenderer.invoke("desktop:screen-question"),
  getCapturePayload: () => ipcRenderer.invoke("desktop:capture-payload"),
  confirmCapture: (selection) => ipcRenderer.invoke("desktop:capture-confirm", selection),
  cancelCapture: () => ipcRenderer.invoke("desktop:capture-cancel"),
  copyUrl: () => ipcRenderer.invoke("desktop:copy-url"),
  newWindow: (url) => ipcRenderer.invoke("desktop:new-window", url),
  navigation: (action) => ipcRenderer.invoke("desktop:navigation", action),
  windowControl: (action) => ipcRenderer.invoke("desktop:window-control", action),
  notify: (payload) => ipcRenderer.invoke("desktop:notify", payload),
  onNavigationState: (callback) => {
    const listener = (_event, state) => callback(state);
    ipcRenderer.on("desktop:navigation-state", listener);
    return () => ipcRenderer.removeListener("desktop:navigation-state", listener);
  },
  onTitleUpdated: (callback) => {
    const listener = (_event, title) => callback(title);
    ipcRenderer.on("desktop:title-updated", listener);
    return () => ipcRenderer.removeListener("desktop:title-updated", listener);
  },
  onWindowState: (callback) => {
    const listener = (_event, state) => callback(state);
    ipcRenderer.on("desktop:window-state", listener);
    return () => ipcRenderer.removeListener("desktop:window-state", listener);
  },
  onQuickFocus: (callback) => {
    const listener = () => callback();
    ipcRenderer.on("desktop:quick-focus", listener);
    return () => ipcRenderer.removeListener("desktop:quick-focus", listener);
  },
  onQuickMode: (callback) => {
    const listener = (_event, mode) => callback(mode);
    ipcRenderer.on("desktop:quick-mode", listener);
    return () => ipcRenderer.removeListener("desktop:quick-mode", listener);
  },
  onQuickSubmit: (callback) => {
    const listener = (_event, text) => callback(text);
    ipcRenderer.on("desktop:quick-submit", listener);
    return () => ipcRenderer.removeListener("desktop:quick-submit", listener);
  },
  onScreenshotCaptured: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("desktop:screenshot-captured", listener);
    return () => ipcRenderer.removeListener("desktop:screenshot-captured", listener);
  },
  onCaptureStart: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("desktop:capture-start", listener);
    return () => ipcRenderer.removeListener("desktop:capture-start", listener);
  },
});
