import React, { useMemo, useRef, useState } from "react";

const DEFAULT_URL = "https://example.com";

export default function App() {
  const [tabs, setTabs] = useState([
    { id: crypto.randomUUID(), url: DEFAULT_URL, title: "New Tab" },
  ]);
  const [activeTabId, setActiveTabId] = useState(tabs[0].id);
  const [url, setUrl] = useState(DEFAULT_URL);
  const [activeUrl, setActiveUrl] = useState(DEFAULT_URL);
  const [ghostMode, setGhostMode] = useState(true);
  const [pageTitle, setPageTitle] = useState("Ghost Browser");
  const [goal, setGoal] = useState("Job research");
  const [query, setQuery] = useState("Remote frontend roles");
  const [runStatus, setRunStatus] = useState("Idle");
  const [runId, setRunId] = useState("");
  const [runError, setRunError] = useState("");
  const webviewMapRef = useRef(new Map());
  const apiBase = import.meta.env.VITE_API_BASE || "http://localhost:8000";

  const onGo = (event) => {
    event.preventDefault();
    const trimmed = url.trim();
    if (!trimmed) return;
    const hasProtocol = /^https?:\/\//i.test(trimmed);
    const looksLikeDomain = /\.[a-z]{2,}$/i.test(trimmed);
    const isSearch = !hasProtocol && !looksLikeDomain;
    const nextUrl = isSearch
      ? `https://www.google.com/search?q=${encodeURIComponent(trimmed)}`
      : hasProtocol
        ? trimmed
        : `https://${trimmed}`;
    setActiveUrl(nextUrl);
    setTabs((prev) =>
      prev.map((tab) =>
        tab.id === activeTabId ? { ...tab, url: nextUrl } : tab
      )
    );
  };

  const statusText = useMemo(() => {
    return ghostMode ? "Ghost Mode: On" : "Ghost Mode: Off";
  }, [ghostMode]);

  const attachWebviewListeners = (webview, tabId) => {
    if (webview.dataset.bound === "1") return;
    webview.dataset.bound = "1";

    const handleNavigate = (event) => {
      if (!event?.url) return;
      setTabs((prev) =>
        prev.map((tab) =>
          tab.id === tabId ? { ...tab, url: event.url } : tab
        )
      );
      if (tabId === activeTabId) {
        setActiveUrl(event.url);
        setUrl(event.url);
      }
    };

    const handleTitle = (event) => {
      if (!event?.title) return;
      setTabs((prev) =>
        prev.map((tab) =>
          tab.id === tabId ? { ...tab, title: event.title } : tab
        )
      );
      if (tabId === activeTabId) {
        setPageTitle(event.title);
      }
    };

    webview.addEventListener("did-navigate", handleNavigate);
    webview.addEventListener("did-navigate-in-page", handleNavigate);
    webview.addEventListener("page-title-updated", handleTitle);
  };

  const setWebviewRef = (tabId) => (node) => {
    if (!node) {
      webviewMapRef.current.delete(tabId);
      return;
    }
    webviewMapRef.current.set(tabId, node);
    attachWebviewListeners(node, tabId);
  };

  const getActiveWebview = () => webviewMapRef.current.get(activeTabId);

  const addTab = () => {
    const id = crypto.randomUUID();
    const newTab = { id, url: DEFAULT_URL, title: "New Tab" };
    setTabs((prev) => [...prev, newTab]);
    setActiveTabId(id);
    setActiveUrl(DEFAULT_URL);
    setUrl(DEFAULT_URL);
    setPageTitle("Ghost Browser");
  };

  const switchTab = (tabId) => {
    const tab = tabs.find((t) => t.id === tabId);
    if (!tab) return;
    setActiveTabId(tabId);
    setActiveUrl(tab.url);
    setUrl(tab.url);
    setPageTitle(tab.title || "Ghost Browser");
  };

  const onBack = () => {
    getActiveWebview()?.goBack();
  };

  const onForward = () => {
    getActiveWebview()?.goForward();
  };

  const onReload = () => {
    getActiveWebview()?.reload();
  };

  const startRun = async () => {
    setRunStatus("Starting...");
    setRunError("");
    try {
      const response = await fetch(`${apiBase}/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          goal,
          query,
          limit: 5,
        }),
      });
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      const data = await response.json();
      setRunId(data.run_id || "");
      setRunStatus(data.status || "Completed");
    } catch (error) {
      setRunError(error.message || "Failed to start run");
      setRunStatus("Error");
    }
  };

  return (
    <div className="app">
      <header className="app__header">
        <div className="brand">
          <span className="brand__dot" />
          <div>
            <div className="brand__title">Ghost Browser</div>
            <div className="brand__subtitle">{pageTitle}</div>
          </div>
        </div>
        <button
          className={`ghost-toggle ${ghostMode ? "ghost-toggle--on" : ""}`}
          onClick={() => setGhostMode((prev) => !prev)}
          type="button"
        >
          {statusText}
        </button>
      </header>

      <section className="tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`tab ${tab.id === activeTabId ? "tab--active" : ""}`}
            type="button"
            onClick={() => switchTab(tab.id)}
          >
            <span className="tab__favicon" />
            <span className="tab__title">{tab.title || "New Tab"}</span>
          </button>
        ))}
        <button className="tab tab--new" type="button" onClick={addTab}>
          +
        </button>
      </section>

      <section className="toolbar">
        <form onSubmit={onGo} className="toolbar__form">
          <div className="toolbar__nav">
            <button className="toolbar__icon" onClick={onBack} type="button">
              ◀
            </button>
            <button className="toolbar__icon" onClick={onForward} type="button">
              ▶
            </button>
            <button className="toolbar__icon" onClick={onReload} type="button">
              ⟳
            </button>
          </div>
          <div className="omnibox">
            <span className="omnibox__lock">🔒</span>
            <span className="omnibox__favicon" />
            <input
              className="toolbar__input"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="Enter a URL or search..."
              spellCheck={false}
            />
            <span className="omnibox__title">{pageTitle || "New Tab"}</span>
          </div>
          <button className="toolbar__button" type="submit">
            Go
          </button>
        </form>
        <div className="toolbar__actions">
          <button className="toolbar__icon" type="button">
            ⋮
          </button>
        </div>
      </section>

      <main className="viewport">
        <div className="viewport__frame">
          {tabs.map((tab) => (
            <webview
              key={tab.id}
              ref={setWebviewRef(tab.id)}
              className={`viewport__webview ${
                tab.id === activeTabId ? "viewport__webview--active" : ""
              }`}
              src={tab.url}
              partition={`persist:ghost-${tab.id}`}
            />
          ))}
        </div>

        <aside className="sidepanel">
          <div className="sidepanel__section">
            <h3>Ghost Mode</h3>
            <label className="field">
              <span>Goal</span>
              <input
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
                placeholder="Job research"
              />
            </label>
            <label className="field">
              <span>Query</span>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Remote frontend roles"
              />
            </label>
            <button className="primary" type="button" onClick={startRun}>
              Start Run
            </button>
            <div className="run-status">
              <div>Status: {runStatus}</div>
              {runId ? <div>Run ID: {runId}</div> : null}
              {runError ? <div className="error">{runError}</div> : null}
            </div>
          </div>
          <div className="sidepanel__section">
            <h3>Agent Log</h3>
            <ul>
              <li>Observe: waiting for page context</li>
              <li>Plan: build playbook</li>
              <li>Act: execute browser steps</li>
              <li>Evaluate: success metrics</li>
              <li>Update: store preferences</li>
            </ul>
          </div>
          <div className="sidepanel__section">
            <h3>Learned</h3>
            <p>Preference: Remote-only</p>
            <p>Patch: fallback selector for search button</p>
          </div>
        </aside>
      </main>
    </div>
  );
}
