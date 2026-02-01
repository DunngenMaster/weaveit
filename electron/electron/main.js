import { app, BrowserView, BrowserWindow, ipcMain } from "electron";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const VITE_DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL || "http://127.0.0.1:5174";
const DEFAULT_USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36";

let mainWindow;
const views = new Map();
let activeTabId = null;
let lastBounds = { x: 0, y: 0, width: 800, height: 600 };

const createView = (tabId, url) => {
  const view = new BrowserView({
    webPreferences: {
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      partition: `persist:ghost-${tabId}`,
    },
  });
  view.webContents.setUserAgent(DEFAULT_USER_AGENT);
  view.webContents.loadURL(url || "about:blank");

  view.webContents.on("did-navigate", (_event, navigatedUrl) => {
    mainWindow?.webContents.send("tabs:event", {
      tabId,
      type: "navigate",
      url: navigatedUrl,
    });
  });

  view.webContents.on("page-title-updated", (_event, title) => {
    mainWindow?.webContents.send("tabs:event", {
      tabId,
      type: "title",
      title,
    });
  });

  view.webContents.on("page-favicon-updated", (_event, favicons) => {
    const favicon = favicons?.[0] || "";
    if (!favicon) return;
    mainWindow?.webContents.send("tabs:event", {
      tabId,
      type: "favicon",
      favicon,
    });
  });

  view.webContents.on("did-fail-load", (_event, errorCode, errorDescription, failedUrl) => {
    mainWindow?.webContents.send("tabs:event", {
      tabId,
      type: "error",
      errorCode,
      errorDescription,
      url: failedUrl,
    });
  });

  return view;
};

const attachView = (tabId) => {
  if (!mainWindow) return;
  const view = views.get(tabId);
  if (!view) return;
  mainWindow.setBrowserView(view);
  view.setBounds(lastBounds);
  view.setAutoResize({ width: true, height: true });
  activeTabId = tabId;
};

const detachView = () => {
  if (!mainWindow) return;
  const current = mainWindow.getBrowserView();
  if (current) {
    mainWindow.setBrowserView(null);
  }
};

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 1200,
    backgroundColor: "#0c0f14",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      webviewTag: false,
    },
  });

  if (process.env.NODE_ENV === "development") {
    mainWindow.loadURL(VITE_DEV_SERVER_URL);
    mainWindow.webContents.openDevTools({ mode: "detach" });
    return;
  }

  // Fallback to dev server if it is running but NODE_ENV wasn't set.
  mainWindow.loadURL(VITE_DEV_SERVER_URL).catch(() => {
    mainWindow.loadFile(path.join(__dirname, "../dist/index.html"));
  });
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

ipcMain.handle("ping", async () => "pong");

ipcMain.handle("tabs:create", (_event, { tabId, url }) => {
  if (!tabId) return;
  const view = createView(tabId, url);
  views.set(tabId, view);
  if (!activeTabId) {
    attachView(tabId);
  }
});

ipcMain.handle("tabs:switch", (_event, { tabId }) => {
  if (!tabId) return;
  if (activeTabId === tabId) return;
  detachView();
  attachView(tabId);
});

ipcMain.handle("tabs:close", (_event, { tabId }) => {
  if (!tabId) return;
  const view = views.get(tabId);
  if (view) {
    if (activeTabId === tabId) {
      detachView();
      activeTabId = null;
    }
    view.webContents.destroy();
    views.delete(tabId);
  }
});

ipcMain.handle("tabs:navigate", (_event, { tabId, url }) => {
  const view = views.get(tabId);
  if (!view || !url) return;
  view.webContents.loadURL(url);
});

ipcMain.handle("tabs:back", () => {
  const view = views.get(activeTabId);
  if (view?.webContents.canGoBack()) view.webContents.goBack();
});

ipcMain.handle("tabs:forward", () => {
  const view = views.get(activeTabId);
  if (view?.webContents.canGoForward()) view.webContents.goForward();
});

ipcMain.handle("tabs:reload", () => {
  const view = views.get(activeTabId);
  if (view) view.webContents.reload();
});

ipcMain.handle("tabs:setBounds", (_event, bounds) => {
  if (!bounds) return;
  lastBounds = bounds;
  const view = views.get(activeTabId);
  if (view) {
    view.setBounds(bounds);
  }
});
