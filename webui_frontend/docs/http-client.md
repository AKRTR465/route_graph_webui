# Frontend HTTP Client Decision

Stage 1 keeps `axios` as the WebUI HTTP client and upgrades it to a non-vulnerable release.

Reasons:

- `src/lib/api.ts` already normalizes `AxiosError` payloads into the current user-facing error messages.
- Replacing `axios` with `fetch` would require a request wrapper and broader behavior checks, which is scheduled for T04-06.
- T01-02 only needs to remove production dependency vulnerabilities while preserving API error behavior.

T04-06 should build the request wrapper on top of the retained `axios` client unless a new audit or runtime constraint changes this decision.
