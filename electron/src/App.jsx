import React, { useEffect, useMemo, useRef, useState } from "react";

const DEFAULT_URL = "about:blank";
const DEFAULT_SEARCH_ENGINE = "https://www.google.com/search?q=";

export default function App() {
  const [tabs, setTabs] = useState([
    {
      id: crypto.randomUUID(),
      url: DEFAULT_URL,
      title: "New Tab",
      favicon: "",
    },
  ]);
  const [tabLogs, setTabLogs] = useState(() => ({
    [tabs[0].id]: [],
  }));
  const [activeTabId, setActiveTabId] = useState(tabs[0].id);
  const [url, setUrl] = useState(DEFAULT_URL);
  const [activeUrl, setActiveUrl] = useState(DEFAULT_URL);
  const [ghostMode, setGhostMode] = useState(true);
  const [pageTitle, setPageTitle] = useState("Ghost Browser");
  const [goal, setGoal] = useState(
    "Find the best noise-cancelling headphones under $200."
  );
  const [query, setQuery] = useState(
    "best noise cancelling headphones under 200"
  );
  const [runStatus, setRunStatus] = useState("Idle");
  const [runId, setRunId] = useState("");
  const [runError, setRunError] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [runDetails, setRunDetails] = useState(null);
  const [runDetailsError, setRunDetailsError] = useState("");
  const [tabRuns, setTabRuns] = useState(() => ({
    [tabs[0].id]: [],
  }));
  const [learned, setLearned] = useState([]);
  const apiBase = import.meta.env.VITE_API_BASE || "http://localhost:8000";
  const activeTab = tabs.find((tab) => tab.id === activeTabId);
  const viewportRef = useRef(null);
  const runPollRef = useRef(null);

  const appendTabLog = (tabId, message) => {
    setTabLogs((prev) => {
      const existing = prev[tabId] || [];
      const next = [...existing, message].slice(-200);
      return { ...prev, [tabId]: next };
    });
  };

  const appendTabRun = (tabId, entry) => {
    setTabRuns((prev) => {
      const existing = prev[tabId] || [];
      const next = [entry, ...existing].slice(0, 10);
      return { ...prev, [tabId]: next };
    });
  };

  useEffect(() => {
    const api = window.ghost?.tabs;
    if (!api) return;
    api.onEvent((payload) => {
      if (!payload?.tabId) return;
      if (payload.type === "navigate") {
        appendTabLog(payload.tabId, `Navigate: ${payload.url}`);
        setTabs((prev) =>
          prev.map((tab) =>
            tab.id === payload.tabId ? { ...tab, url: payload.url } : tab
          )
        );
        if (payload.tabId === activeTabId) {
          setActiveUrl(payload.url);
          setUrl(payload.url);
        }
      }
      if (payload.type === "title") {
        setTabs((prev) =>
          prev.map((tab) =>
            tab.id === payload.tabId
              ? { ...tab, title: payload.title }
              : tab
          )
        );
        if (payload.tabId === activeTabId) {
          setPageTitle(payload.title || "Ghost Browser");
        }
      }
      if (payload.type === "favicon") {
        setTabs((prev) =>
          prev.map((tab) =>
            tab.id === payload.tabId
              ? { ...tab, favicon: payload.favicon }
              : tab
          )
        );
      }
      if (payload.type === "error") {
        appendTabLog(
          payload.tabId,
          `Load failed: ${payload.url || ""} (${payload.errorCode})`
        );
      }
    });
  }, [activeTabId]);

  useEffect(() => {
    const api = window.ghost?.tabs;
    if (!api || !viewportRef.current) return;
    const element = viewportRef.current;

    const sendBounds = () => {
      const rect = element.getBoundingClientRect();
      api.setBounds({
        x: Math.round(rect.left),
        y: Math.round(rect.top),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      });
    };

    sendBounds();
    const observer = new ResizeObserver(() => sendBounds());
    observer.observe(element);
    window.addEventListener("resize", sendBounds);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", sendBounds);
    };
  }, []);

  useEffect(() => {
    const api = window.ghost?.tabs;
    if (!api) return;
    const first = tabs[0];
    if (!first) return;
    api.create(first.id, first.url);
    api.switch(first.id);
  }, []);

  const onGo = (event) => {
    event.preventDefault();
    const trimmed = url.trim();
    if (!trimmed) return;
    const hasProtocol = /^https?:\/\//i.test(trimmed);
    const looksLikeDomain = /\.[a-z]{2,}$/i.test(trimmed);
    const isSearch = !hasProtocol && !looksLikeDomain;
    const nextUrl = isSearch
      ? `${DEFAULT_SEARCH_ENGINE}${encodeURIComponent(trimmed)}`
      : hasProtocol
        ? trimmed
        : `https://${trimmed}`;
    setActiveUrl(nextUrl);
    setUrl(nextUrl);
    setTabs((prev) =>
      prev.map((tab) =>
        tab.id === activeTabId ? { ...tab, url: nextUrl } : tab
      )
    );
    window.ghost?.tabs?.navigate(activeTabId, nextUrl);
  };

  const statusText = useMemo(() => {
    return ghostMode ? "Ghost Mode: On" : "Ghost Mode: Off";
  }, [ghostMode]);

  const addTab = () => {
    const id = crypto.randomUUID();
    const newTab = { id, url: DEFAULT_URL, title: "New Tab", favicon: "" };
    setTabs((prev) => [...prev, newTab]);
    setTabLogs((prev) => ({ ...prev, [id]: [] }));
    setTabRuns((prev) => ({ ...prev, [id]: [] }));
    setActiveTabId(id);
    setActiveUrl(DEFAULT_URL);
    setUrl(DEFAULT_URL);
    setPageTitle("Ghost Browser");
    window.ghost?.tabs?.create(id, DEFAULT_URL);
    window.ghost?.tabs?.switch(id);
  };

  const switchTab = (tabId) => {
    const tab = tabs.find((t) => t.id === tabId);
    if (!tab) return;
    setActiveTabId(tabId);
    setActiveUrl(tab.url);
    setUrl(tab.url);
    setPageTitle(tab.title || "Ghost Browser");
    window.ghost?.tabs?.switch(tabId);
  };

  const closeTab = (tabId) => {
    const isLastTab = tabs.length === 1;
    const fallbackId = isLastTab ? crypto.randomUUID() : null;
    setTabs((prev) => {
      const nextTabs = prev.filter((tab) => tab.id !== tabId);
      if (nextTabs.length === 0) {
        const id = fallbackId || crypto.randomUUID();
        return [{ id, url: DEFAULT_URL, title: "New Tab", favicon: "" }];
      }
      return nextTabs;
    });
    setTabLogs((prev) => {
      const next = { ...prev };
      delete next[tabId];
      if (Object.keys(next).length === 0 && fallbackId) {
        next[fallbackId] = [];
      }
      return next;
    });
    setTabRuns((prev) => {
      const next = { ...prev };
      delete next[tabId];
      if (Object.keys(next).length === 0 && fallbackId) {
        next[fallbackId] = [];
      }
      return next;
    });

    if (tabId === activeTabId) {
      if (isLastTab && fallbackId) {
        setActiveTabId(fallbackId);
        setActiveUrl(DEFAULT_URL);
        setUrl(DEFAULT_URL);
        setPageTitle("Ghost Browser");
        window.ghost?.tabs?.create(fallbackId, DEFAULT_URL);
        window.ghost?.tabs?.switch(fallbackId);
      } else {
        const remaining = tabs.filter((tab) => tab.id !== tabId);
        const nextActive = remaining[0];
        if (nextActive) {
          setActiveTabId(nextActive.id);
          setActiveUrl(nextActive.url);
          setUrl(nextActive.url);
          setPageTitle(nextActive.title || "Ghost Browser");
          window.ghost?.tabs?.switch(nextActive.id);
        } else {
          setActiveTabId("");
          setActiveUrl(DEFAULT_URL);
          setUrl(DEFAULT_URL);
          setPageTitle("Ghost Browser");
        }
      }
    }
    window.ghost?.tabs?.close(tabId);
  };

  const onBack = () => {
    window.ghost?.tabs?.back();
  };

  const onForward = () => {
    window.ghost?.tabs?.forward();
  };

  const onReload = () => {
    window.ghost?.tabs?.reload();
  };

  const startRun = async () => {
    setRunStatus("Starting...");
    setRunError("");
    setIsRunning(true);
    setRunDetails(null);
    setRunDetailsError("");
    if (runPollRef.current) {
      clearTimeout(runPollRef.current);
      runPollRef.current = null;
    }
    const startedAt = new Date().toLocaleTimeString();
    appendTabRun(activeTabId, {
      runId: "pending",
      status: "Starting",
      goal,
      query,
      time: startedAt,
    });
    appendTabLog(activeTabId, `Run: starting (${goal})`);
    try {
      const response = await fetch(`${apiBase}/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          goal,
          query,
          limit: 5,
          tab_id: activeTabId,
          url: activeUrl,
        }),
      });
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      const data = await response.json();
      setRunId(data.run_id || "");
      setRunStatus(data.status || "Completed");
      appendTabLog(activeTabId, `Run: ${data.status || "Completed"}`);
      if (data.run_id) {
        appendTabLog(activeTabId, `Run ID: ${data.run_id}`);
      }
      appendTabRun(activeTabId, {
        runId: data.run_id || "unknown",
        status: data.status || "Completed",
        goal,
        query,
        time: new Date().toLocaleTimeString(),
      });
      if (data.run_id) {
        pollRunDetails(data.run_id, 0);
      }
    } catch (error) {
      setRunError(error.message || "Failed to start run");
      setRunStatus("Error");
      appendTabLog(
        activeTabId,
        `Run: error (${error.message || "Failed to start run"})`
      );
      appendTabRun(activeTabId, {
        runId: "error",
        status: "Error",
        goal,
        query,
        time: new Date().toLocaleTimeString(),
      });
    } finally {
      setIsRunning(false);
      fetchLearned();
    }
  };

  const fetchRunDetails = async (id) => {
    if (!id) return null;
    const response = await fetch(`${apiBase}/runs/${encodeURIComponent(id)}`);
    if (!response.ok) {
      throw new Error(`Run details error: ${response.status}`);
    }
    return response.json();
  };

  const pollRunDetails = async (id, attempt) => {
    try {
      const data = await fetchRunDetails(id);
      if (!data) return;
      setRunDetails(data);
      if (data.status === "completed" || data.status === "error") {
        return;
      }
    } catch (error) {
      setRunDetailsError(error.message || "Failed to load run details");
      return;
    }
    if (attempt >= 15) return;
    runPollRef.current = setTimeout(() => {
      pollRunDetails(id, attempt + 1);
    }, 1500);
  };

  const fetchLearned = async (tabId = activeTabId) => {
    try {
      const response = await fetch(
        `${apiBase}/learned?tab_id=${encodeURIComponent(tabId || "")}`
      );
      if (!response.ok) return;
      const data = await response.json();
      const prefs = data?.preferences && typeof data.preferences === "object"
        ? data.preferences
        : {};
      const items = Object.entries(prefs).map(([key, value]) => ({
        key,
        value,
      }));
      setLearned(items);
    } catch (error) {
      // no-op
    }
  };

  useEffect(() => {
    fetchLearned();
  }, []);

  useEffect(() => {
    if (activeTabId) {
      fetchLearned(activeTabId);
    }
  }, [activeTabId]);
  
  useEffect(() => {
    return () => {
      if (runPollRef.current) {
        clearTimeout(runPollRef.current);
        runPollRef.current = null;
      }
    };
  }, []);

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
            {tab.favicon ? (
              <img className="tab__favicon" src={tab.favicon} alt="" />
            ) : (
              <span className="tab__favicon" />
            )}
            <span className="tab__title">{tab.title || "New Tab"}</span>
            <span
              className="tab__close"
              onClick={(event) => {
                event.stopPropagation();
                closeTab(tab.id);
              }}
              role="button"
            >
              ×
            </span>
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
            {activeTab?.favicon ? (
              <img className="omnibox__favicon" src={activeTab.favicon} alt="" />
            ) : (
              <span className="omnibox__favicon" />
            )}
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
        <div className="viewport__frame" ref={viewportRef} />

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
              {isRunning ? "Starting..." : "Start Run"}
            </button>
            <div className="run-status">
              <div>Status: {runStatus}</div>
              {runId ? <div>Run ID: {runId}</div> : null}
              {runError ? <div className="error">{runError}</div> : null}
            </div>
          </div>
          <div className="sidepanel__section">
            <h3>Agent Log</h3>
            {tabLogs[activeTabId]?.length ? (
              <ul>
                {tabLogs[activeTabId].map((entry, idx) => (
                  <li key={`${activeTabId}-${idx}`}>{entry}</li>
                ))}
              </ul>
            ) : (
              <p className="muted">No activity yet for this tab.</p>
            )}
          </div>
          <div className="sidepanel__section">
            <h3>Run History</h3>
            {tabRuns[activeTabId]?.length ? (
              <ul className="runs">
                {tabRuns[activeTabId].map((run, idx) => (
                  <li key={`${activeTabId}-run-${idx}`} className="runs__item">
                    <div className="runs__row">
                      <span className="runs__status">{run.status}</span>
                      <span className="runs__time">{run.time}</span>
                    </div>
                    <div className="runs__meta">{run.goal}</div>
                    <div className="runs__meta">{run.query}</div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">No runs yet for this tab.</p>
            )}
          </div>
          <div className="sidepanel__section">
            <h3>Learned</h3>
            {learned.length ? (
              <ul className="learned">
                {learned.map((item) => (
                  <li key={item.key} className="learned__item">
                    <span className="learned__key">{item.key}</span>
                    <span className="learned__value">{item.value}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">No learned preferences yet.</p>
            )}
          </div>
          <div className="sidepanel__section">
            <h3>Run Details</h3>
            {runDetails ? (
              <div className="run-details">
                <div className="run-details__row">
                  <span>Status</span>
                  <span>{runDetails.status}</span>
                </div>
                {runDetails.plan && Object.keys(runDetails.plan).length ? (
                  <div className="run-details__block">
                    <div className="run-details__label">Plan</div>
                    <pre className="run-details__code">
                      {JSON.stringify(runDetails.plan, null, 2)}
                    </pre>
                  </div>
                ) : null}
                <div className="run-details__block">
                  <div className="run-details__label">
                    Candidates ({runDetails.candidates ? runDetails.candidates.length : 0})
                  </div>
                  {runDetails.candidates && runDetails.candidates.length ? (
                    <ul className="run-details__list">
                      {runDetails.candidates.map((item, idx) => (
                        <li key={`candidate-${idx}`}>
                          <div className="run-details__item-title">
                            {item.title || item.url}
                          </div>
                          <div className="run-details__item-url">
                            {item.url}
                          </div>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="muted">No candidates found.</p>
                  )}
                </div>
                {runDetails.extracted && runDetails.extracted.length ? (
                  <div className="run-details__block">
                    <div className="run-details__label">
                      Extracted ({runDetails.extracted.length})
                    </div>
                    <ul className="run-details__list">
                      {runDetails.extracted.map((item, idx) => (
                        <li key={`extract-${idx}`}>
                          <div className="run-details__item-title">
                            {item.title || item.url}
                          </div>
                          <div className="run-details__item-url">
                            {item.url}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <p className="muted">No extracted items yet.</p>
                )}
                {runDetails.trace && runDetails.trace.length ? (
                  <div className="run-details__block">
                    <div className="run-details__label">
                      Trace ({runDetails.trace.length})
                    </div>
                    <ul className="run-details__list">
                      {runDetails.trace.map((item, idx) => (
                        <li key={`trace-${idx}`}>
                          <div className="run-details__item-title">
                            {item.type || "event"}
                          </div>
                          <div className="run-details__item-url">
                            {item.payload ? JSON.stringify(item.payload) : ""}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            ) : runDetailsError ? (
              <p className="error">{runDetailsError}</p>
            ) : (
              <p className="muted">Run details will appear here.</p>
            )}
          </div>
        </aside>
      </main>
    </div>
  );
}
