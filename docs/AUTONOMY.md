# Full-managed autonomy

The default policy intentionally gives Codex broad Amazon Ads operational authority without per-action human approval. The Owner supplies a standing deterministic envelope instead of approving each mutation.

**v0.4 archive hardening does not shrink that business decision space.** Replay barriers, fresh-state checks, crash recovery and runtime compatibility checks protect execution correctness; they do not turn valid in-envelope strategies into recommendation-only work.

Autonomous families include bids, budgets, placements, keywords, targets, negative targeting, campaign/ad-group/ad creation and reversible state transitions. Permanent account/billing/credential/user-management/destructive operations are outside advertising optimization and remain blocked.

The hard boundary is Python + SQLite + the frozen execution hook, not prompt wording. Current machine-enforced controls include:

- exact product/action scope and HMAC binding;
- fresh pre-write observation requirements plus a final fresh-state check for existing-entity writes;
- fresh same-day spend evidence before any spend increase;
- Owner daily spend ceiling with a platform buffer and transactional reservations;
- one-use Executor grants that cannot authorize the same sealed action twice;
- final-boundary re-check of Autopilot mode, Emergency Stop and Policy/Operator revisions;
- ambiguous or crash-interrupted write outcomes continuing to consume reserved spend capacity;
- restart reconciliation from fresh Amazon state instead of blind mutation replay;
- per-action bid/budget/placement magnitude limits;
- per-cycle profile budget expansion limit;
- daily campaign-create count and new-campaign budget limits;
- current-cycle observed-ASIN provenance for product-ad creation;
- cross-cycle entity/action-family cooldowns;
- consecutive-exception circuit breaker and kill switch;
- autonomous campaign namespace + PAUSED creation + independent verification lineage before activation;
- independent post-write verification.

A stale pre-write action is cancelled so Codex can replan from current Amazon reality; the strategy family is not permanently blocked. Likewise, recovery guards decide whether an already-authorized mutation was applied, not whether Codex was allowed to choose that optimization.

To raise or lower autonomy in production, use the authenticated Owner Web (or the trusted local `ownerctl` for supported emergency/mode controls). The mutable standing policy is stored in the Owner DB outside the Git checkout; prompts and model workspaces cannot edit it. `owner_daily_spend_ceiling` is the principal monetary authority boundary and should be set to the maximum same-day ad spend you are willing to place under autonomous control.
