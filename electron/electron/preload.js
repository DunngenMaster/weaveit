import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("ghost", {
  ping: () => ipcRenderer.invoke("ping"),
});
