const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("ghost", {
  ping: () => ipcRenderer.invoke("ping"),
  tabs: {
    create: (tabId, url) => ipcRenderer.invoke("tabs:create", { tabId, url }),
    switch: (tabId) => ipcRenderer.invoke("tabs:switch", { tabId }),
    close: (tabId) => ipcRenderer.invoke("tabs:close", { tabId }),
    navigate: (tabId, url) => ipcRenderer.invoke("tabs:navigate", { tabId, url }),
    back: () => ipcRenderer.invoke("tabs:back"),
    forward: () => ipcRenderer.invoke("tabs:forward"),
    reload: () => ipcRenderer.invoke("tabs:reload"),
    setBounds: (bounds) => ipcRenderer.invoke("tabs:setBounds", bounds),
    onEvent: (handler) => ipcRenderer.on("tabs:event", (_event, payload) => handler(payload)),
  },
});
