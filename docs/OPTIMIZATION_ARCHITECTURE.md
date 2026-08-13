# Sponsored Products Optimization Architecture

## Purpose

The project deliberately separates **authority** from **advertising intelligence**.
Owner Control defines the monetary/scope envelope. Inside that envelope, Codex is expected to act as a fully managed Sponsored Products portfolio operator without human approval or artificial micro-limits. The optimization plane must improve what the AI knows, not reduce what it is allowed to do.

This architecture focuses on Sponsored Products. Sponsored Brands, Sponsored Display and DSP are intentionally not optimization priorities.

## Three optimization planes

### 1. Sponsored Products strategy plane

The Planner reasons at four nested levels:

`account -> ASIN portfolio -> campaign/ad group -> query/keyword/target/placement/audience/format`

The primary question is not "is ACOS low?". It is:

> Where should the next unit of authorized advertising capital go to maximize expected incremental contribution profit and future information value?

The Planner therefore combines:

- search-term mining, harvesting, negatives and traffic isolation;
- auto/broad/phrase/exact lifecycle management;
- category and ASIN/product targeting;
- cannibalization and campaign role separation;
- base bids plus bidding strategy interactions;
- top-of-search, rest-of-search, product-page and available Amazon Business/off-Amazon placement evidence;
- Sponsored Products audience bid boosts when exposed;
- Sponsored Products video evidence and video bid boosts when exposed;
- Search Term Impression Share/rank as competitive headroom evidence;
- hourly/near-real-time signals such as Amazon Marketing Stream when available;
- budget starvation, saturation and portfolio reallocation;
- event/schedule/rule-based bidding and budget rules when they are the better expression of recurring demand.

Feature awareness never permits invented API calls. The live authenticated Amazon Ads MCP tool surface remains the source of truth for executable capabilities.

### 2. Learning and data-science plane

`OptimizationMemory` adds persistent tables to the existing runtime SQLite database without changing Owner authority:

- `optimization_observations`: normalized performance facts across entity/window dimensions;
- `optimization_economics`: optional trusted ASIN economics;
- `optimization_candidates`: executed and foregone capital-allocation hypotheses;
- `optimization_experiments`: explicit interventions with evaluation horizons;
- `optimization_outcomes`: sealed action and independent verification outcomes.

Every real Planner response carries a `learning_snapshot`, including zero-action cycles. That makes observation itself durable instead of discarding all performance evidence after a single prompt.

The current statistical layer is dependency-free and deterministic:

- empirical/Bayesian CVR shrinkage for sparse entities, with the prior built from one canonical dimensional cut to avoid double-counting the same traffic;
- evidence-confidence and attribution-tail scores instead of treating immature clicks as fully settled conversions;
- expected ROAS and expected profit-per-click/ad-dollar estimates;
- short-vs-long trend and hourly-pattern diagnostics;
- Search Term Impression Share headroom and next-dollar capital frontier ranking;
- query-routing/cannibalization detection, exact-harvest candidates and mature waste candidates;
- placement, audience, video and budget-state opportunity surfaces;
- retail/Featured Offer/inventory context as economic evidence rather than a permission gate;
- explicit experiment baselines and later evaluation, including contribution-profit evaluation when trusted ASIN economics exist;
- durable action/outcome lineage.

The statistical signals are advisory. A fresh Amazon observation can override historical priors, and Codex retains the full business discretion granted by Owner Control.

### 3. Contribution-profit and portfolio plane

The optimizer uses the strongest available economics in this order:

1. ASIN `contribution_margin_per_order` supplied by Owner economics;
2. ASIN `contribution_margin_pct` supplied by Owner economics;
3. a derived cost stack from AOV minus unit COGS, Amazon fees and per-order promotion cost;
4. configured `break_even_acos_pct` as a margin proxy when detailed economics are unavailable.

This means the system remains useful before a Seller/SP-API economics integration is available, while automatically becoming profit-native when trusted COGS/fee/return/promotion data is supplied.

The optional Owner economics file defaults to:

`$ADS_OWNER_HOME/economics.json`

or can be overridden with `ADS_ECONOMICS_FILE`.

Use `config/economics.example.json` as the format. `contribution_margin_pct` means contribution margin **before advertising spend**. Do not put target ACOS in this field.

Portfolio signals rank scale/learn/restructure opportunities by expected marginal economics, uncertainty/confidence and available demand headroom. These rankings do not reserve budget or restrict actions; they are evidence for Codex to use when choosing among competing opportunities.

## Production flow

```text
Amazon Ads read-only evidence
        +
optional Owner ASIN economics
        +
prior performance/action/outcome memory
        |
        v
OptimizationMemory
  - normalized facts
  - Bayesian evidence
  - experiment history
  - marginal profit signals
        |
        v
Sponsored Products Portfolio Strategist (Codex)
  - observe current account
  - compare alternatives
  - choose autonomous action portfolio
  - emit durable learning_snapshot
        |
        v
existing Owner policy / sealed execution / verifier
        |
        v
verified outcomes
        |
        +---------------------> OptimizationMemory
```

`OptimizationController` is intentionally fail-open **only for learning telemetry**: if the learning database/context cannot be produced, the normal sealed Controller still runs with the same Owner-granted authority and fresh Amazon evidence. It does not fail-open any write authorization boundary.

## Cycle behavior

Hourly, daily and weekly cycles are different analytical cadences, not different permission tiers.

- **Hourly**: intraday pacing, budget consumption, daypart response, anomalies and profitable reallocation.
- **Daily**: full bid/budget/placement/search-term/target optimization and harvesting.
- **Weekly**: structural architecture, isolation, larger experiments, lifecycle reassessment and portfolio capital allocation.

If Owner policy permits an action and evidence supports it, the cycle label alone should not prevent the Planner from taking it.

## Long-term learning contract

The system should increasingly answer questions such as:

- Which query archetypes for this ASIN respond positively to higher bids?
- At what placement boost does marginal CPC exceed marginal conversion value?
- When is impression-share headroom profitable versus merely expensive?
- Which auto/broad discovery sources generate unique profitable exact terms?
- Which campaign is budget constrained and which is demand constrained?
- Which ASIN has the highest expected profit return on the next $100?
- Which effects repeat by hour/day/event and deserve scheduled rules?
- Which interventions produced persistent profit rather than temporary attributed-sales noise?

The repository stores the evidence needed to begin answering these questions instead of asking Codex to rediscover the account from scratch every cycle.
