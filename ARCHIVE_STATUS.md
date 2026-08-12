# v0.3.0 archive status

Status: **SOURCE ARCHIVE GATE PASSED / REAL-ACCOUNT LIVE ACCEPTANCE PENDING**

The v0.3.0 source candidate has passed the credential-free archive gate in the build sandbox:

- 34/34 Python tests passed.
- 38/38 archive checks passed.
- Python source compiled successfully.
- All shell scripts passed `bash -n`.
- Offline wheel build succeeded with the installed toolchain and includes Owner Web static assets.
- Rendered systemd service/timer units passed `systemd-analyze verify` and all timer calendars parsed successfully.
- Temporary bootstrap verified Owner Home 0700, Owner/runtime DB and signing/config files 0600, frozen hook 0500, and a valid signed Owner audit chain.
- Source scan found no Amazon OAuth client-id pattern, bearer token, PEM private key, or AWS access-key pattern.

This status does **not** certify a real Amazon Ads account. OAuth, live MCP tool/schema discovery, Observe-only evidence coverage, micro-live reversible writes, PAUSED-create/verify/enable lifecycle, emergency-stop drill, and ambiguous-failure drill remain required per `docs/ARCHIVE_ACCEPTANCE.md` before a specific deployment can be called production-accepted.
