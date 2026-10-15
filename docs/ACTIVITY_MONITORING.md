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
