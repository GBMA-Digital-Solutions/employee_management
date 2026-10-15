# Activity monitoring collector contract

The existing employer dashboard issues a revocable collector token only after the employee acknowledges the disclosure in their employee workspace. The raw token is displayed once and must be stored in the authorized Windows agent/browser extension credential store.

Collectors submit short activity intervals to:

`POST /api/activity-monitoring/ingest/`

Headers:

```text
Content-Type: application/json
X-Monitoring-Agent-Token: <issued token>
```

Browser extension example:

```json
{
  "source": "browser",
  "kind": "website",
  "resource": "https://docs.example.com/project/page",
  "started_at": "2026-10-15T08:30:00+02:00",
  "ended_at": "2026-10-15T08:35:00+02:00"
}
```

Windows agent example:

```json
{
  "source": "windows",
  "kind": "application",
  "resource": "Microsoft Excel",
  "started_at": "2026-10-15T08:35:00+02:00",
  "ended_at": "2026-10-15T08:40:00+02:00"
}
```

Intervals must be 15 minutes or shorter. The server accepts them only when they fit entirely inside an open attendance visit and, when configured, the company's fixed working hours. Website query strings and fragments are removed before storage.

Collectors must never send window titles, private messages, passwords, keystrokes, clipboard/form contents, or screenshots. The API explicitly rejects those fields. A `201` response means the interval was accepted; `401` means the collector token is invalid or revoked; `403` means the interval is outside authorized working time.

## Chrome extension setup

1. The employee signs in, opens their account page, and acknowledges the monitoring disclosure.
2. The employer opens **Activity Monitoring**, selects that employee, and chooses **Issue collector token**.
3. In Chrome, open `chrome://extensions`, enable **Developer mode**, choose **Load unpacked**, and select the repository's `chrome-extension` folder.
4. Open the extension, enter the dashboard origin (for example `http://localhost:5173` or the current `https://...loca.lt` URL), paste the one-time token, enable tracking, and choose **Save and test**.
5. Keep the employee checked in. The API intentionally rejects activity outside an open attendance visit and outside configured fixed working hours.

The extension requires `tabs` to read the active tab URL, `idle` to stop counting inactive time, `alarms` to submit bounded intervals, `storage` for the API URL/token, and host access only for local development and LocalTunnel. When a LocalTunnel URL changes, update the URL in the extension popup; no new collector token is required.
