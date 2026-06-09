import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("agentHubDesktop", {
  getState: () => ipcRenderer.invoke("desktop:get-state"),
  files: {
    importEncrypted: () => ipcRenderer.invoke("desktop:pick-files"),
    preview: (id) => ipcRenderer.invoke("desktop:preview-vault-file", id),
    revealEncryptedCopy: (id) => ipcRenderer.invoke("desktop:show-item", id),
  },
  notifications: {
    show: (payload) => ipcRenderer.invoke("desktop:notify", payload),
  },
  agent: {
    start: () => ipcRenderer.invoke("agent:start"),
    stop: () => ipcRenderer.invoke("agent:stop"),
    status: () => ipcRenderer.invoke("agent:status"),
    onLog: (callback) => {
      const listener = (_event, line) => callback(line);
      ipcRenderer.on("agent:log", listener);
      return () => ipcRenderer.removeListener("agent:log", listener);
    },
    onStatus: (callback) => {
      const listener = (_event, status) => callback(status);
      ipcRenderer.on("agent:status", listener);
      return () => ipcRenderer.removeListener("agent:status", listener);
    },
  },
  api: {
    health: (apiBase) => ipcRenderer.invoke("api:health", apiBase),
  },
});
