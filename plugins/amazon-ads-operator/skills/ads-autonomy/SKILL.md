---
name: ads-autonomy
description: Operate Amazon Sponsored Products autonomously inside Owner authority, including explicitly armed Owner Direct Override commands.
---

The Owner control plane is the authority boundary. In normal operation, preserve broad AI decision freedom inside the configured Sponsored Products scope and monetary envelope, and route every live change through Planner -> deterministic policy -> fresh-state guard -> one-use Atomic Executor -> independent Verifier.

## Owner Direct Override

When the Owner gives a special natural-language advertising instruction, first inspect `python3 scripts/ownerctl.py status` and read `direct_override`.

- Never arm or extend Owner Direct Override yourself. Only the authenticated Owner Control Plane may open the 30-minute, 1-hour, 2-hour or permanent authorization window.
- If the window is not armed, tell the Owner to select an Owner Direct Override duration in the Control Plane before attempting the special write.
- If the window is armed, execute the Owner's instruction verbatim through `python3 scripts/run_cycle.py direct --instruction <owner instruction>` rather than issuing raw Amazon writes.
- The direct cycle may use the full executable Sponsored Products advertising surface needed by that instruction and may bypass routine autonomy toggles, money/bid/placement caps, cooldowns, naming rules, managed-ASIN filters, PAUSED-first creation rules and routine irreversible-ad restrictions.
- Do not broaden the direct command into unrelated account optimization merely because the window is open. A satisfied instruction should produce no repeat mutation.
- Billing, payment, credentials/OAuth, user management, account administration and account deletion remain outside the direct-override capability. Emergency Stop always wins.
- Exact MCP binding, fresh pre-write state, one-use grants, independent verification, crash ambiguity handling and the Owner audit chain remain mandatory.

The permanent option means the capability window stays armed until the Owner explicitly selects another Control Plane mode, clears the override, or triggers Emergency Stop. It is not permission for the AI to self-renew or self-expand authority.
