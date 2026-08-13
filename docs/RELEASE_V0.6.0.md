# Amazon Ads Codex Operator v0.6.0

**Sponsored Products optimization-intelligence seal.**

v0.6.0 keeps the Owner-controlled sealed execution architecture and deliberately shifts engineering effort upward into advertising intelligence rather than adding another AI permission tier.

## New production intelligence loop

Every production cycle now starts with a read-only Sponsored Products observation pass. Normalized evidence is persisted in `OptimizationMemory` before the Planner makes its decision, so Codex receives both fresh Amazon reality and durable historical learning.

Every Planner result also emits a required `learning_snapshot`, including zero-write cycles. The runtime persists performance facts, optional Owner ASIN economics, alternative portfolio opportunities, explicit experiments and verified action outcomes.

The dependency-free statistical layer supplies empirical-Bayesian CVR shrinkage, evidence confidence, attribution-tail risk, short-vs-long trend comparisons, temporal patterns, impression-share headroom, expected profit per click/ad dollar, next-dollar capital ranking, query/cannibalization diagnostics, harvesting/waste candidates, placement/audience/video/budget opportunities and exploration-value signals.

## Sponsored Products strategy upgrade

The Planner is now instructed to optimize account/ASIN portfolio opportunity cost and expected incremental contribution profit, not isolated ACOS. Its native reasoning surface includes search-term harvesting/isolation, target lifecycle, cannibalization, bidding-strategy interactions, placement economics, Amazon Business/off-Amazon evidence, Search Term Impression Share, audience bid boosting, Marketing Stream-style intraday evidence, budget/bid rules and Sponsored Products video when those capabilities are exposed by the authenticated Amazon Ads surface.

## Economics

Trusted ASIN economics can be supplied at `$ADS_OWNER_HOME/economics.json` or `ADS_ECONOMICS_FILE`. When detailed economics are absent, `break_even_acos_pct` remains a useful margin proxy so portfolio optimization does not collapse back to raw ACOS ranking.

## Authority invariant

No human approval layer was added. No new advertising micro-limit was added. Owner Control remains the authority boundary, and the AI retains its configured budget-within-scope freedom. Optimization telemetry is allowed to degrade without silently shrinking that standing business authority; sealed write authorization remains unchanged.

The release remains subject to the existing credential-free full-stack, reproducible-build, complete-history privacy and provenance gates. Real-account effectiveness still requires live evidence and cannot be truthfully certified by source code alone.
