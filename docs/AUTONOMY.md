# Full-managed autonomy

The default policy intentionally gives Codex broad Amazon Ads operational authority without per-action human approval. The owner supplies a standing deterministic envelope instead of approving each mutation.

Autonomous families include bids, budgets, placements, keywords, targets, negative targeting, campaign/ad-group/ad creation and reversible state transitions. Permanent account/billing/credential/user-management/destructive operations are outside advertising optimization and remain blocked.

The hard boundary is Python + SQLite, not prompt wording. Current machine-enforced controls include:

- exact product/action scope and HMAC binding;
- fresh pre-write observation requirements;
- fresh same-day spend evidence before any spend increase;
- owner daily spend ceiling with a platform buffer and reservations;
- ambiguous write outcomes continuing to consume reserved spend capacity;
- per-action bid/budget/placement magnitude limits;
- per-cycle profile budget expansion limit;
- daily campaign-create count and new-campaign budget limits;
- current-cycle observed-ASIN provenance for product-ad creation;
- cross-cycle entity/action-family cooldowns;
- consecutive-exception circuit breaker and kill switch;
- autonomous campaign namespace + PAUSED creation + independent verification lineage before activation;
- independent post-write verification.

To raise or lower autonomy in production, use the authenticated Owner Web (or the trusted local `ownerctl` only for supported emergency/mode controls). The mutable standing policy is stored in the Owner DB outside the Git checkout; prompts and model workspaces cannot edit it. `owner_daily_spend_ceiling` is the principal monetary authority boundary and should be set to the maximum same-day ad spend you are willing to place under autonomous control.
