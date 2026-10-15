const fields = {
  apiBase: document.querySelector("#apiBase"),
  token: document.querySelector("#token"),
  enabled: document.querySelector("#enabled"),
  status: document.querySelector("#status"),
};

chrome.storage.local.get({ apiBase: "http://localhost:5173", token: "", enabled: false }, (saved) => {
  fields.apiBase.value = saved.apiBase;
  fields.token.value = saved.token;
  fields.enabled.checked = saved.enabled;
});

document.querySelector("#save").addEventListener("click", async () => {
  const settings = {
    apiBase: fields.apiBase.value.trim().replace(/\/$/, ""),
    token: fields.token.value.trim(),
    enabled: fields.enabled.checked,
  };
  if (!/^https?:\/\//.test(settings.apiBase) || !settings.token) {
    fields.status.textContent = "Enter a valid URL and collector token.";
    return;
  }
  await chrome.storage.local.set(settings);
  fields.status.textContent = "Testing connection…";
  chrome.runtime.sendMessage({ type: "settings-updated" }, (response) => {
    if (chrome.runtime.lastError) fields.status.textContent = chrome.runtime.lastError.message;
    else fields.status.textContent = response?.ok ? "Connected. Tracking is ready." : response?.error || "Connection failed.";
  });
});
