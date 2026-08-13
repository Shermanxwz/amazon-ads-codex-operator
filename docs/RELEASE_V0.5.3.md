# Amazon Ads Codex Operator v0.5.3

**Production-surface full-stack acceptance seal.**

v0.5.3 keeps the v0.5.2 execution, recovery, reproducibility and provenance controls unchanged, then closes the final credential-free end-to-end coverage gap at the operator/deployment surface.

The Ubuntu 24.04 Python-3.12 `virtual-full-stack` gate now runs **ten** required production scenarios across two cooperating harnesses:

1. fresh bootstrap + preflight;
2. Observe with no external write;
3. sealed live planner → policy → prewrite → one-use frozen Hook → mutation → verifier path;
4. Codex Evergreen candidate promotion + rollback;
5. backup/restore preserving ACTIVE runtime identity and clearing stale auth/grants;
6. successful write followed by ambiguous transport, reconciled without replay;
7. grant consumption followed by pre-write crash/restart uncertainty, never replayed;
8. final-boundary Emergency Stop plus Linux process-lock rejection;
9. the real `scripts/run_web.py` loopback HTTP entrypoint: static UI, readiness, unauthenticated denial, password login, CSRF enforcement, Owner policy revision, revision restore, Autopilot transition and Emergency Stop;
10. the real `scripts/install_systemd.sh` rendering path in an isolated HOME, followed by template-elimination and `systemd-analyze verify` checks.

`install_systemd.sh` gains an explicit `ADS_SYSTEMD_RENDER_ONLY=1` certification mode that renders the exact production units but deliberately does not call `systemctl`; normal production installation behavior is unchanged.

The archive tests make these two surface checks mandatory so a later edit cannot silently remove them from the full-stack gate. Local `make virtual-acceptance` also runs both harnesses.

As before, this proves the entire credential-free control plane and production entry/deployment surfaces, not a particular Amazon advertiser/profile, live OAuth session, authenticated MCP schema or real-money Amazon behavior. Those remain account/host-specific acceptance items.
