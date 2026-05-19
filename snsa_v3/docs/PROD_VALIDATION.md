# SNSA — Production Validation Checklist

> To be completed by the deployment team after each production rollout.
> Record the actual result and evidence for each check.
> All checks must be PASS before marking the release as stable.

---

## Pre-deployment

| # | Check | Command | Expected | Result | Evidence |
|---|---|---|---|---|---|
| P1 | Migration Job completed | `oc wait --for=condition=complete job/snsa-migrate-VERSION --timeout=120s` | Job succeeded | | |
| P2 | No failed pods after rollout | `oc get pods -l app=snsa` | All Running | | |
| P3 | 2 replicas available | `oc get deployment snsa` | READY 2/2 | | |

---

## A — Security runtime

| # | Check | Command | Expected | Result | Evidence |
|---|---|---|---|---|---|
| A1 | Pod runs as non-root | `oc exec -it <pod> -- id` | UID ≠ 0 | | |
| A2 | No privilege escalation | `oc describe pod <pod> \| grep -A5 securityContext` | allowPrivilegeEscalation: false | | |
| A3 | SCC applied | `oc describe pod <pod> \| grep scc` | restricted / restricted-v2 | | |
| A4 | All capabilities dropped | `oc describe pod <pod> \| grep -A3 capabilities` | drop: ALL | | |

---

## B — Network and headers

| # | Check | Command | Expected | Result | Evidence |
|---|---|---|---|---|---|
| B1 | Route accessible over HTTPS | `curl -I https://snsa.CLUSTER_DOMAIN/api/health/live/` | HTTP/2 200 | | |
| B2 | HTTP redirects to HTTPS | `curl -I http://snsa.CLUSTER_DOMAIN/api/health/live/` | 301/302 → HTTPS | | |
| B3 | XFF from trusted proxy honoured | Check `device_ip` in `ScanLog` after a scan from Zebra | Warehouse device IP, not router IP | | |
| B4 | XFF from untrusted source ignored | Send spoofed XFF from outside proxy range | `device_ip` = actual source IP | | |
| B5 | IP whitelist blocks unknown IP | `curl` from IP not in AllowedIP (when whitelist enabled) | 403 Forbidden | | |

---

## C — Database

| # | Check | Command | Expected | Result | Evidence |
|---|---|---|---|---|---|
| C1 | Readiness probe passes | `curl https://snsa.CLUSTER_DOMAIN/api/health/ready/` | `{"status":"ok","db":"ok"}` | | |
| C2 | Migration Job ran cleanly | `oc logs job/snsa-migrate-VERSION` | No errors, `No migrations to apply` or applied list | | |
| C3 | Both replicas connect to DB | `oc logs deploy/snsa` (both pods) | No DB connection errors | | |
| C4 | Session data persists across pods | Login on pod A, reload hitting pod B | Session maintained | | |

---

## D — Functional smoke test

Run against the deployed environment. Use a test HU configured in the mock or DEV APIM.

| # | Check | Steps | Expected | Result | Evidence |
|---|---|---|---|---|---|
| D1 | Login | Open `https://snsa.CLUSTER_DOMAIN/login/` | Login page loads with local assets (no CDN) | | |
| D2 | HU lookup — GS1 HU | Scan `9780201379624` | Session created, items displayed | | |
| D3 | GS1 DataMatrix scan | Scan a GS1 barcode with AI 240 + AI 21 | Serial accepted, counter decrements | | |
| D4 | EAN + serial flow | Scan EAN, then serial | EAN sets pending item; serial completes it | | |
| D5 | Quantity exceeded error | Scan one extra serial | `SN_QTY_EXCEEDED` error shown | | |
| D6 | Duplicate serial rejected | Scan same serial twice | `SN_DUPLICATE_LOCAL` error shown | | |
| D7 | Confirm and push | Tap Confirm | Redirects to session_complete, SAP doc ref shown | | |
| D8 | Session recovery | Reload during scan | Existing active session recovered | | |
| D9 | Push retry after failure | Use `HU_PUSH_FAIL`, then retry | Retry succeeds (or fails cleanly with correct status) | | |
| D10 | No-serialization HU | Scan `HU_NO_SERIAL` | Redirects to no_serialization page | | |
| D11 | Supervisor view | Login as supervisor, view sessions | Session list visible | | |

---

## E — Resource and performance

| # | Check | Command | Expected | Result | Evidence |
|---|---|---|---|---|---|
| E1 | Pod memory within limits | `oc top pod -l app=snsa` | < 512Mi | | |
| E2 | Pod CPU within limits | `oc top pod -l app=snsa` | < 500m | | |
| E3 | Response time health endpoint | `curl -w "%{time_total}" https://.../api/health/ready/` | < 500ms | | |

---

## Useful commands

```bash
# Pod status
oc get pods -l app=snsa
oc describe deployment snsa
oc logs deploy/snsa --tail=100

# Migration job
oc logs job/snsa-migrate-VERSION
oc describe job snsa-migrate-VERSION

# Live in pod
oc exec -it <pod> -- id
oc exec -it <pod> -- python manage.py check --deploy

# Events (useful for probe failures)
oc get events --sort-by=.lastTimestamp | tail -20
```

---

## Sign-off

| Role | Name | Date | Signature |
|---|---|---|---|
| App developer | | | |
| Platform / ISSC | | | |
| Functional owner | | | |
