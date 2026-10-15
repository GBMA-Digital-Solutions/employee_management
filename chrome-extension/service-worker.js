const ALARM = "activity-heartbeat";
const MAX_INTERVAL_MS = 5 * 60 * 1000;
let current = null;

function isTrackable(url) {
  return /^https?:\/\//i.test(url || "");
}

async function settings() {
  return chrome.storage.local.get({ apiBase: "", token: "", enabled: false });
}

async function sendInterval(interval, endedAt = Date.now()) {
  if (!interval || endedAt <= interval.startedAt) return { ok: true };
  const config = await settings();
  if (!config.enabled || !config.apiBase || !config.token) return { ok: false, error: "Collector is not configured." };
  const end = Math.min(endedAt, interval.startedAt + MAX_INTERVAL_MS);
  try {
    const response = await fetch(`${config.apiBase.replace(/\/$/, "")}/api/activity-monitoring/ingest/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Monitoring-Agent-Token": config.token,
        "bypass-tunnel-reminder": "true"
      },
      body: JSON.stringify({
        source: "browser", kind: "website", resource: interval.url,
        started_at: new Date(interval.startedAt).toISOString(),
        ended_at: new Date(end).toISOString()
      })
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || Object.values(body).flat().join(" ") || `API returned ${response.status}`);
    }
    await chrome.storage.local.set({ lastSuccessAt: new Date().toISOString(), lastError: "" });
    return { ok: true };
  } catch (error) {
    await chrome.storage.local.set({ lastError: error.message });
    return { ok: false, error: error.message };
  }
}

async function activePage() {
  const config = await settings();
  if (!config.enabled) return null;
  const idleState = await chrome.idle.queryState(60);
  if (idleState !== "active") return null;
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  return tab && isTrackable(tab.url) ? { tabId: tab.id, url: tab.url, startedAt: Date.now() } : null;
}

async function transition() {
  const endedAt = Date.now();
  await sendInterval(current, endedAt);
  current = await activePage();
}

chrome.runtime.onInstalled.addListener(() => chrome.alarms.create(ALARM, { periodInMinutes: 1 }));
chrome.runtime.onStartup.addListener(() => chrome.alarms.create(ALARM, { periodInMinutes: 1 }));
chrome.alarms.onAlarm.addListener((alarm) => { if (alarm.name === ALARM) transition(); });
chrome.tabs.onActivated.addListener(transition);
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.url && current?.tabId === tabId) transition();
});
chrome.windows.onFocusChanged.addListener(transition);
chrome.idle.onStateChanged.addListener(transition);
chrome.runtime.onMessage.addListener((message, _sender, respond) => {
  if (message.type !== "settings-updated") return false;
  transition().then(async () => {
    const config = await settings();
    if (!config.enabled) return respond({ ok: true });
    const test = await activePage();
    if (!test) return respond({ ok: true });
    // A short, valid interval verifies authentication without collecting page contents.
    test.startedAt = Date.now() - 1000;
    respond(await sendInterval(test));
  });
  return true;
});

chrome.alarms.create(ALARM, { periodInMinutes: 1 });
activePage().then((page) => { current = page; });
