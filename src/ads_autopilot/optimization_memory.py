from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any

UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode()).hexdigest()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _bounded(value: Any, low: float, high: float, default: float = 0.0) -> float:
    return max(low, min(high, _num(value, default)))


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _beta_signal(successes: float, trials: float, prior_rate: float, prior_strength: float = 20.0) -> dict[str, float]:
    trials = max(0.0, trials)
    successes = max(0.0, min(trials, successes))
    prior_rate = max(0.001, min(0.999, prior_rate))
    alpha = successes + prior_rate * prior_strength
    beta = max(0.0, trials - successes) + (1.0 - prior_rate) * prior_strength
    total = alpha + beta
    mean = alpha / total
    variance = alpha * beta / (total * total * (total + 1.0))
    sd = math.sqrt(max(0.0, variance))
    lower80 = max(0.0, mean - 1.2815515655446004 * sd)
    confidence = 1.0 - math.exp(-trials / 35.0)
    return {"mean": mean, "lower80": lower80, "confidence": confidence}


def _metric(row: dict[str, Any], name: str) -> float | None:
    if name == "roas":
        spend = _num(row.get("spend"))
        return _num(row.get("sales")) / spend if spend > 0 else None
    if name == "acos_pct":
        sales = _num(row.get("sales"))
        return 100.0 * _num(row.get("spend")) / sales if sales > 0 else None
    if name == "cvr":
        clicks = _num(row.get("clicks"))
        return _num(row.get("orders")) / clicks if clicks > 0 else None
    if name == "ctr":
        impressions = _num(row.get("impressions"))
        return _num(row.get("clicks")) / impressions if impressions > 0 else None
    if name == "sales":
        return _num(row.get("sales"))
    if name == "orders":
        return _num(row.get("orders"))
    if name == "contribution_profit":
        return _num(row.get("contribution_profit"))
    return None


class OptimizationMemory:
    """Persistent SP learning and portfolio decision-support plane.

    This layer never grants or removes mutation authority. It only turns observed
    advertising evidence, historical interventions and optional ASIN economics
    into richer evidence for the autonomous Planner.
    """

    def __init__(self, store: Any, economics_path: str | Path | None = None):
        self.store = store
        self.economics_path = Path(economics_path).expanduser() if economics_path else None
        self._init()

    def _init(self) -> None:
        with self.store.connection() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS optimization_observations(
                    fact_hash TEXT PRIMARY KEY,
                    cycle_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    campaign_id TEXT,
                    ad_group_id TEXT,
                    asin TEXT,
                    query TEXT,
                    match_type TEXT,
                    placement TEXT,
                    window_label TEXT NOT NULL,
                    window_start TEXT,
                    window_end TEXT,
                    impressions REAL NOT NULL DEFAULT 0,
                    clicks REAL NOT NULL DEFAULT 0,
                    spend REAL NOT NULL DEFAULT 0,
                    orders REAL NOT NULL DEFAULT 0,
                    sales REAL NOT NULL DEFAULT 0,
                    units REAL NOT NULL DEFAULT 0,
                    new_to_brand_orders REAL,
                    impression_share_pct REAL,
                    impression_rank REAL,
                    budget REAL,
                    bid REAL,
                    evidence_ref TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_opt_obs_entity
                    ON optimization_observations(entity_type, entity_id, observed_at DESC);
                CREATE INDEX IF NOT EXISTS idx_opt_obs_asin
                    ON optimization_observations(asin, observed_at DESC);
                CREATE INDEX IF NOT EXISTS idx_opt_obs_cycle
                    ON optimization_observations(cycle_id);

                CREATE TABLE IF NOT EXISTS optimization_economics(
                    economics_hash TEXT PRIMARY KEY,
                    cycle_id TEXT,
                    observed_at TEXT NOT NULL,
                    asin TEXT NOT NULL,
                    contribution_margin_pct REAL,
                    contribution_margin_per_order REAL,
                    unit_cogs REAL,
                    amazon_fees REAL,
                    promo_cost_per_order REAL,
                    return_rate_pct REAL,
                    inventory_units REAL,
                    source TEXT NOT NULL,
                    evidence_ref TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_opt_econ_asin
                    ON optimization_economics(asin, observed_at DESC);

                CREATE TABLE IF NOT EXISTS optimization_candidates(
                    candidate_hash TEXT PRIMARY KEY,
                    cycle_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    asin TEXT,
                    campaign_id TEXT,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    hypothesis TEXT NOT NULL,
                    expected_incremental_spend REAL NOT NULL DEFAULT 0,
                    expected_incremental_sales REAL NOT NULL DEFAULT 0,
                    expected_incremental_profit REAL NOT NULL DEFAULT 0,
                    uncertainty REAL NOT NULL DEFAULT 1,
                    horizon_days INTEGER NOT NULL DEFAULT 7,
                    evidence_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_opt_candidates_cycle
                    ON optimization_candidates(cycle_id);

                CREATE TABLE IF NOT EXISTS optimization_experiments(
                    experiment_id TEXT PRIMARY KEY,
                    cycle_id TEXT NOT NULL,
                    hypothesis TEXT NOT NULL,
                    action_ids_json TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    primary_metric TEXT NOT NULL,
                    expected_direction TEXT NOT NULL,
                    baseline_window_days INTEGER NOT NULL,
                    evaluation_days INTEGER NOT NULL,
                    baseline_value REAL,
                    latest_value REAL,
                    lift_pct REAL,
                    confidence REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_opt_experiment_status
                    ON optimization_experiments(status, updated_at DESC);

                CREATE TABLE IF NOT EXISTS optimization_outcomes(
                    action_hash TEXT PRIMARY KEY,
                    cycle_id TEXT NOT NULL,
                    action_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    verification_status TEXT,
                    spend_delta REAL NOT NULL DEFAULT 0,
                    before_json TEXT NOT NULL,
                    after_json TEXT NOT NULL,
                    observed_json TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_opt_outcome_entity
                    ON optimization_outcomes(entity_type, entity_id, recorded_at DESC);
                """
            )

    def ingest_plan(self, cycle_id: str, plan: dict[str, Any]) -> dict[str, int]:
        snapshot = dict(plan.get("learning_snapshot") or {})
        observed_at = str(snapshot.get("observed_at") or _now_iso())
        entities = list(snapshot.get("entities") or [])
        economics = list(snapshot.get("economics") or [])
        candidates = list(snapshot.get("portfolio_candidates") or [])
        experiments = list(snapshot.get("experiments") or [])
        counts = {"observations": 0, "economics": 0, "candidates": 0, "experiments": 0}
        with self.store.connection() as c:
            for raw in entities:
                if not isinstance(raw, dict):
                    continue
                entity_type = str(raw.get("entity_type") or "").strip().lower()
                entity_id = str(raw.get("entity_id") or raw.get("query") or "").strip()
                profile_id = str(raw.get("profile_id") or "").strip()
                evidence_ref = str(raw.get("evidence_ref") or "").strip()
                if not (entity_type and entity_id and profile_id and evidence_ref):
                    continue
                item = {
                    "cycle_id": cycle_id,
                    "observed_at": str(raw.get("observed_at") or observed_at),
                    "profile_id": profile_id,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "campaign_id": str(raw.get("campaign_id") or "") or None,
                    "ad_group_id": str(raw.get("ad_group_id") or "") or None,
                    "asin": str(raw.get("asin") or "").upper() or None,
                    "query": str(raw.get("query") or "") or None,
                    "match_type": str(raw.get("match_type") or "") or None,
                    "placement": str(raw.get("placement") or "") or None,
                    "window_label": str(raw.get("window_label") or "custom").lower(),
                    "window_start": str(raw.get("window_start") or "") or None,
                    "window_end": str(raw.get("window_end") or "") or None,
                    "impressions": max(0.0, _num(raw.get("impressions"))),
                    "clicks": max(0.0, _num(raw.get("clicks"))),
                    "spend": max(0.0, _num(raw.get("spend"))),
                    "orders": max(0.0, _num(raw.get("orders"))),
                    "sales": max(0.0, _num(raw.get("sales"))),
                    "units": max(0.0, _num(raw.get("units"))),
                    "new_to_brand_orders": None if raw.get("new_to_brand_orders") is None else max(0.0, _num(raw.get("new_to_brand_orders"))),
                    "impression_share_pct": None if raw.get("impression_share_pct") is None else _bounded(raw.get("impression_share_pct"), 0.0, 100.0),
                    "impression_rank": None if raw.get("impression_rank") is None else max(1.0, _num(raw.get("impression_rank"), 1.0)),
                    "budget": None if raw.get("budget") is None else max(0.0, _num(raw.get("budget"))),
                    "bid": None if raw.get("bid") is None else max(0.0, _num(raw.get("bid"))),
                    "evidence_ref": evidence_ref,
                }
                fact_hash = _hash({k: v for k, v in item.items() if k != "cycle_id"})
                before = c.total_changes
                c.execute(
                    """INSERT OR IGNORE INTO optimization_observations(
                    fact_hash,cycle_id,observed_at,profile_id,entity_type,entity_id,campaign_id,ad_group_id,asin,query,match_type,placement,window_label,window_start,window_end,impressions,clicks,spend,orders,sales,units,new_to_brand_orders,impression_share_pct,impression_rank,budget,bid,evidence_ref,payload_json,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        fact_hash, cycle_id, item["observed_at"], profile_id, entity_type, entity_id,
                        item["campaign_id"], item["ad_group_id"], item["asin"], item["query"], item["match_type"], item["placement"], item["window_label"], item["window_start"], item["window_end"],
                        item["impressions"], item["clicks"], item["spend"], item["orders"], item["sales"], item["units"], item["new_to_brand_orders"], item["impression_share_pct"], item["impression_rank"], item["budget"], item["bid"], evidence_ref, _stable_json(raw), _now_iso(),
                    ),
                )
                counts["observations"] += int(c.total_changes > before)

            for raw in economics:
                counts["economics"] += self._insert_economics(c, cycle_id, raw, source="planner")
            for raw in candidates:
                if not isinstance(raw, dict):
                    continue
                candidate_id = str(raw.get("candidate_id") or "").strip()
                entity_type = str(raw.get("entity_type") or "").strip().lower()
                entity_id = str(raw.get("entity_id") or "").strip()
                hypothesis = str(raw.get("hypothesis") or "").strip()
                if not (candidate_id and entity_type and entity_id and hypothesis):
                    continue
                item = {
                    "cycle_id": cycle_id,
                    "candidate_id": candidate_id,
                    "asin": str(raw.get("asin") or "").upper() or None,
                    "campaign_id": str(raw.get("campaign_id") or "") or None,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "hypothesis": hypothesis,
                    "expected_incremental_spend": max(0.0, _num(raw.get("expected_incremental_spend"))),
                    "expected_incremental_sales": max(0.0, _num(raw.get("expected_incremental_sales"))),
                    "expected_incremental_profit": _num(raw.get("expected_incremental_profit")),
                    "uncertainty": _bounded(raw.get("uncertainty"), 0.0, 1.0, 1.0),
                    "horizon_days": max(1, min(90, int(_num(raw.get("horizon_days"), 7.0)))),
                    "evidence_refs": [str(x) for x in raw.get("evidence_refs") or []],
                }
                candidate_hash = _hash(item)
                before = c.total_changes
                c.execute(
                    "INSERT OR IGNORE INTO optimization_candidates(candidate_hash,cycle_id,candidate_id,asin,campaign_id,entity_type,entity_id,hypothesis,expected_incremental_spend,expected_incremental_sales,expected_incremental_profit,uncertainty,horizon_days,evidence_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (candidate_hash, cycle_id, candidate_id, item["asin"], item["campaign_id"], entity_type, entity_id, hypothesis, item["expected_incremental_spend"], item["expected_incremental_sales"], item["expected_incremental_profit"], item["uncertainty"], item["horizon_days"], _stable_json(item["evidence_refs"]), _now_iso()),
                )
                counts["candidates"] += int(c.total_changes > before)

            for raw in experiments:
                if not isinstance(raw, dict):
                    continue
                experiment_id = str(raw.get("experiment_id") or "").strip()
                entity_type = str(raw.get("entity_type") or "").strip().lower()
                entity_id = str(raw.get("entity_id") or "").strip()
                primary_metric = str(raw.get("primary_metric") or "").strip().lower()
                if not (experiment_id and entity_type and entity_id and primary_metric):
                    continue
                baseline = self._latest_metric(c, entity_type, entity_id, primary_metric)
                before = c.total_changes
                c.execute(
                    """INSERT OR IGNORE INTO optimization_experiments(
                    experiment_id,cycle_id,hypothesis,action_ids_json,entity_type,entity_id,primary_metric,expected_direction,baseline_window_days,evaluation_days,baseline_value,latest_value,lift_pct,confidence,status,evidence_json,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        experiment_id, cycle_id, str(raw.get("hypothesis") or ""), _stable_json([str(x) for x in raw.get("action_ids") or []]), entity_type, entity_id, primary_metric,
                        str(raw.get("expected_direction") or "increase").lower(), max(1, int(_num(raw.get("baseline_window_days"), 14))), max(1, int(_num(raw.get("evaluation_days"), 7))), baseline, baseline, None, 0.0, "running", _stable_json([str(x) for x in raw.get("evidence_refs") or []]), _now_iso(), _now_iso(),
                    ),
                )
                counts["experiments"] += int(c.total_changes > before)
        self.ingest_external_economics(cycle_id)
        self.refresh_experiments()
        return counts

    def _insert_economics(self, c: Any, cycle_id: str | None, raw: Any, source: str) -> int:
        if not isinstance(raw, dict):
            return 0
        asin = str(raw.get("asin") or "").strip().upper()
        if not asin:
            return 0
        observed_at = str(raw.get("observed_at") or _now_iso())
        item = {
            "cycle_id": cycle_id,
            "observed_at": observed_at,
            "asin": asin,
            "contribution_margin_pct": None if raw.get("contribution_margin_pct") is None else _bounded(raw.get("contribution_margin_pct"), 0.0, 100.0),
            "contribution_margin_per_order": None if raw.get("contribution_margin_per_order") is None else _num(raw.get("contribution_margin_per_order")),
            "unit_cogs": None if raw.get("unit_cogs") is None else max(0.0, _num(raw.get("unit_cogs"))),
            "amazon_fees": None if raw.get("amazon_fees") is None else max(0.0, _num(raw.get("amazon_fees"))),
            "promo_cost_per_order": None if raw.get("promo_cost_per_order") is None else max(0.0, _num(raw.get("promo_cost_per_order"))),
            "return_rate_pct": None if raw.get("return_rate_pct") is None else _bounded(raw.get("return_rate_pct"), 0.0, 100.0),
            "inventory_units": None if raw.get("inventory_units") is None else max(0.0, _num(raw.get("inventory_units"))),
            "source": source,
            "evidence_ref": str(raw.get("evidence_ref") or f"{source}:{asin}"),
        }
        economics_hash = _hash({k: v for k, v in item.items() if k != "cycle_id"})
        before = c.total_changes
        c.execute(
            "INSERT OR IGNORE INTO optimization_economics(economics_hash,cycle_id,observed_at,asin,contribution_margin_pct,contribution_margin_per_order,unit_cogs,amazon_fees,promo_cost_per_order,return_rate_pct,inventory_units,source,evidence_ref,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (economics_hash, cycle_id, observed_at, asin, item["contribution_margin_pct"], item["contribution_margin_per_order"], item["unit_cogs"], item["amazon_fees"], item["promo_cost_per_order"], item["return_rate_pct"], item["inventory_units"], source, item["evidence_ref"], _stable_json(raw), _now_iso()),
        )
        return int(c.total_changes > before)

    def ingest_external_economics(self, cycle_id: str | None = None) -> int:
        path = self.economics_path
        if not path or not path.exists():
            return 0
        try:
            doc = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return 0
        if not isinstance(doc, dict):
            return 0
        defaults = dict(doc.get("default") or {})
        asins = doc.get("asins") or {}
        if not isinstance(asins, dict):
            return 0
        inserted = 0
        try:
            file_observed_at = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
        except OSError:
            file_observed_at = _now_iso()
        with self.store.connection() as c:
            for asin, value in asins.items():
                if not isinstance(value, dict):
                    continue
                raw = {**defaults, **value, "asin": str(asin).upper()}
                raw.setdefault("observed_at", file_observed_at)
                raw.setdefault("evidence_ref", f"owner-economics:{str(asin).upper()}")
                inserted += self._insert_economics(c, cycle_id, raw, source="owner_file")
        return inserted

    def capture_action_outcomes(self, cycle_id: str) -> int:
        inserted = 0
        with self.store.connection() as c:
            rows = c.execute(
                """SELECT a.action_hash,a.cycle_id,a.action_id,a.action_type,a.status,a.spend_delta,a.payload_json,
                v.status verification_status,v.observed_json
                FROM actions a
                LEFT JOIN verifications v ON v.id=(SELECT id FROM verifications vv WHERE vv.action_hash=a.action_hash ORDER BY vv.id DESC LIMIT 1)
                WHERE a.cycle_id=?""",
                (cycle_id,),
            ).fetchall()
            for row in rows:
                try:
                    payload = json.loads(row["payload_json"] or "{}")
                except Exception:
                    payload = {}
                try:
                    observed = json.loads(row["observed_json"] or "{}") if row["observed_json"] else {}
                except Exception:
                    observed = {}
                before = c.total_changes
                c.execute(
                    """INSERT INTO optimization_outcomes(action_hash,cycle_id,action_id,action_type,entity_type,entity_id,status,verification_status,spend_delta,before_json,after_json,observed_json,rationale,recorded_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(action_hash) DO UPDATE SET status=excluded.status,verification_status=excluded.verification_status,observed_json=excluded.observed_json,recorded_at=excluded.recorded_at""",
                    (
                        row["action_hash"], row["cycle_id"], row["action_id"], row["action_type"], str(payload.get("entity_type") or "").lower(), str(payload.get("entity_id") or ""), row["status"], row["verification_status"], float(row["spend_delta"] or 0), _stable_json(payload.get("before") or {}), _stable_json(payload.get("after") or {}), _stable_json(observed), str(payload.get("rationale") or ""), _now_iso(),
                    ),
                )
                inserted += int(c.total_changes > before)
        return inserted

    @staticmethod
    def _owner_margin_for_row(row: dict[str, Any], econ: dict[str, Any], proxy_margin: float | None = None) -> tuple[float | None, float | None, str]:
        orders = _num(row.get("orders")); sales = _num(row.get("sales")); aov = sales / orders if orders > 0 else 0.0
        if econ.get("contribution_margin_per_order") is not None and aov > 0:
            margin_per_order = _num(econ.get("contribution_margin_per_order"))
            ratio = margin_per_order / aov if aov else proxy_margin
            return margin_per_order, ratio, "owner_margin_per_order"
        if econ.get("contribution_margin_pct") is not None and aov > 0:
            ratio = _bounded(econ.get("contribution_margin_pct"), 0, 100) / 100.0
            return aov * ratio, ratio, "owner_margin_pct"
        if aov > 0 and any(econ.get(k) is not None for k in ("unit_cogs", "amazon_fees", "promo_cost_per_order")):
            units = _num(row.get("units"))
            units_per_order = units / orders if orders > 0 and units > 0 else 1.0
            margin_per_order = max(
                0.0,
                aov
                - _num(econ.get("unit_cogs")) * units_per_order
                - _num(econ.get("amazon_fees"))
                - _num(econ.get("promo_cost_per_order")),
            )
            return margin_per_order, margin_per_order / aov if aov else proxy_margin, "owner_cost_stack"
        if proxy_margin is not None and aov > 0:
            return aov * proxy_margin, proxy_margin, "break_even_acos_proxy"
        return None, None, "economics_unavailable"

    def _latest_metric(self, c: Any, entity_type: str, entity_id: str, metric: str) -> float | None:
        row = c.execute(
            "SELECT * FROM optimization_observations WHERE entity_type=? AND entity_id=? ORDER BY observed_at DESC, created_at DESC LIMIT 1",
            (entity_type, entity_id),
        ).fetchone()
        if not row:
            return None
        value = dict(row)
        if metric != "contribution_profit":
            return _metric(value, metric)
        asin = str(value.get("asin") or "").upper()
        if not asin:
            return None
        econ_row = c.execute(
            "SELECT * FROM optimization_economics WHERE asin=? ORDER BY observed_at DESC, created_at DESC LIMIT 1",
            (asin,),
        ).fetchone()
        if not econ_row:
            return None
        margin_per_order, _, _ = self._owner_margin_for_row(value, dict(econ_row), None)
        if margin_per_order is None:
            return None
        return _num(value.get("orders")) * margin_per_order * (1.0 - _bounded(econ_row["return_rate_pct"], 0, 100, 0) / 100.0) - _num(value.get("spend"))

    def refresh_experiments(self) -> int:
        now = datetime.now(UTC)
        updates = 0
        with self.store.connection() as c:
            rows = c.execute("SELECT * FROM optimization_experiments WHERE status='running'").fetchall()
            for row in rows:
                created = _parse_time(row["created_at"])
                if not created:
                    continue
                age_days = (now - created).total_seconds() / 86400.0
                latest = self._latest_metric(c, row["entity_type"], row["entity_id"], row["primary_metric"])
                baseline = row["baseline_value"]
                lift = None
                if latest is not None and baseline is not None and abs(float(baseline)) > 1e-12:
                    lift = 100.0 * (float(latest) - float(baseline)) / abs(float(baseline))
                status = "evaluated" if age_days >= int(row["evaluation_days"]) and latest is not None else "running"
                evidence = c.execute(
                    "SELECT clicks,orders FROM optimization_observations WHERE entity_type=? AND entity_id=? ORDER BY observed_at DESC LIMIT 1",
                    (row["entity_type"], row["entity_id"]),
                ).fetchone()
                confidence = 0.0
                if evidence:
                    confidence = min(1.0, (1.0 - math.exp(-float(evidence["clicks"] or 0) / 35.0)) * 0.7 + (1.0 - math.exp(-float(evidence["orders"] or 0) / 8.0)) * 0.3)
                c.execute(
                    "UPDATE optimization_experiments SET latest_value=?,lift_pct=?,confidence=?,status=?,updated_at=? WHERE experiment_id=?",
                    (latest, lift, confidence, status, _now_iso(), row["experiment_id"]),
                )
                updates += 1
        return updates

    def _latest_economics(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        with self.store.connection() as c:
            rows = c.execute("SELECT * FROM optimization_economics ORDER BY observed_at DESC, created_at DESC").fetchall()
        for row in rows:
            asin = str(row["asin"] or "").upper()
            if asin and asin not in result:
                result[asin] = dict(row)
        return result

    def _latest_window_facts(self, limit: int = 2400) -> list[dict[str, Any]]:
        with self.store.connection() as c:
            rows = c.execute("SELECT * FROM optimization_observations ORDER BY observed_at DESC, created_at DESC LIMIT ?", (limit,)).fetchall()
        latest_by_window: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in rows:
            d = dict(row)
            key = (d["entity_type"], d["entity_id"], d["window_label"])
            if key not in latest_by_window:
                latest_by_window[key] = d
        return list(latest_by_window.values())

    def _preferred_facts(self, limit: int = 1600) -> list[dict[str, Any]]:
        latest = self._latest_window_facts(limit=max(limit, 1600))
        preference = {"30d": 0, "28d": 1, "14d": 2, "7d": 3, "65d": 4, "90d": 5, "intraday": 6, "today": 7, "custom": 8}
        by_entity: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for d in latest:
            by_entity[(d["entity_type"], d["entity_id"])].append(d)
        selected = []
        for options in by_entity.values():
            options.sort(key=lambda r: (preference.get(str(r["window_label"]).lower(), 20), -_num(r.get("clicks"))))
            selected.append(options[0])
        return selected

    @staticmethod
    def _attribution_tail_risk(row: dict[str, Any], attribution_days: float = 14.0) -> float:
        end = _parse_time(row.get("window_end"))
        start = _parse_time(row.get("window_start"))
        if not end:
            return 0.35 if str(row.get("window_label") or "").lower() in {"intraday", "today", "7d"} else 0.15
        age = max(0.0, (datetime.now(UTC) - end).total_seconds() / 86400.0)
        if age >= attribution_days:
            return 0.0
        if start and end > start:
            window_days = max(1.0, (end - start).total_seconds() / 86400.0)
        else:
            labels = {"7d": 7.0, "14d": 14.0, "28d": 28.0, "30d": 30.0, "65d": 65.0, "90d": 90.0, "today": 1.0, "intraday": 1.0}
            window_days = labels.get(str(row.get("window_label") or "").lower(), 14.0)
        immature_days = min(window_days, attribution_days - age)
        return max(0.0, min(1.0, immature_days / window_days))

    @staticmethod
    def _window_comparisons(latest: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
        for row in latest:
            groups[(row["entity_type"], row["entity_id"])][str(row["window_label"]).lower()] = row
        out = []
        for (entity_type, entity_id), windows in groups.items():
            short = next((windows[x] for x in ("7d", "14d", "today", "intraday") if x in windows), None)
            long = next((windows[x] for x in ("30d", "28d", "65d", "90d") if x in windows), None)
            if not short or not long:
                continue
            def ratios(row: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
                spend = _num(row.get("spend")); sales = _num(row.get("sales")); clicks = _num(row.get("clicks")); orders = _num(row.get("orders"))
                return (sales / spend if spend > 0 else None, orders / clicks if clicks > 0 else None, spend / clicks if clicks > 0 else None)
            s_roas, s_cvr, s_cpc = ratios(short); l_roas, l_cvr, l_cpc = ratios(long)
            def delta(a: float | None, b: float | None) -> float | None:
                return None if a is None or b is None or abs(b) < 1e-12 else (a / b) - 1.0
            roas_delta, cvr_delta, cpc_delta = delta(s_roas, l_roas), delta(s_cvr, l_cvr), delta(s_cpc, l_cpc)
            components = [x for x in (roas_delta, cvr_delta, None if cpc_delta is None else -cpc_delta) if x is not None]
            trend_score = sum(components) / len(components) if components else 0.0
            confidence = 1.0 - math.exp(-_num(short.get("clicks")) / 35.0)
            if confidence < 0.2:
                posture = "insufficient_evidence"
            elif trend_score > 0.18:
                posture = "improving"
            elif trend_score < -0.18:
                posture = "deteriorating"
            else:
                posture = "stable"
            out.append({
                "entity_type": entity_type, "entity_id": entity_id,
                "short_window": short["window_label"], "long_window": long["window_label"],
                "roas_delta_pct": None if roas_delta is None else round(roas_delta * 100, 2),
                "cvr_delta_pct": None if cvr_delta is None else round(cvr_delta * 100, 2),
                "cpc_delta_pct": None if cpc_delta is None else round(cpc_delta * 100, 2),
                "trend_score": round(trend_score, 4), "confidence": round(confidence, 4), "trend": posture,
            })
        out.sort(key=lambda x: abs(x["trend_score"]) * x["confidence"], reverse=True)
        return out

    @staticmethod
    def _temporal_patterns(latest: list[dict[str, Any]], margin_proxy: float) -> list[dict[str, Any]]:
        parsed = []
        for row in latest:
            try:
                payload = json.loads(row.get("payload_json") or "{}")
            except Exception:
                payload = {}
            hour = payload.get("hour_of_day")
            if hour is None:
                label = str(row.get("window_label") or "")
                if label.startswith("hour-"):
                    try: hour = int(label.split("-", 1)[1])
                    except ValueError: hour = None
            try: hour = int(hour) if hour is not None else None
            except (TypeError, ValueError): hour = None
            if hour is None or not 0 <= hour <= 23:
                continue
            parsed.append((hour, row, payload))
        if not parsed:
            return []
        campaign_rows = [x for x in parsed if x[1].get("entity_type") == "campaign"]
        use = campaign_rows or parsed
        agg: dict[int, dict[str, float]] = defaultdict(lambda: {"spend": 0.0, "sales": 0.0, "clicks": 0.0, "orders": 0.0, "impressions": 0.0})
        for hour, row, _ in use:
            for key in agg[hour]: agg[hour][key] += _num(row.get(key))
        total_spend = sum(v["spend"] for v in agg.values())
        result = []
        for hour in sorted(agg):
            v = agg[hour]; spend = v["spend"]; sales = v["sales"]; clicks = v["clicks"]; orders = v["orders"]
            roas = sales / spend if spend > 0 else None; cvr = orders / clicks if clicks > 0 else None
            result.append({
                "hour_of_day": hour, "spend": round(spend, 4), "sales": round(sales, 4),
                "roas": None if roas is None else round(roas, 4), "cvr": None if cvr is None else round(cvr, 6),
                "spend_share": round(spend / total_spend, 5) if total_spend > 0 else 0.0,
                "profit_proxy": round(sales * margin_proxy - spend, 4),
                "clicks": round(clicks, 3), "orders": round(orders, 3),
            })
        return result

    @staticmethod
    def _query_diagnostics(signals: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        by_query: dict[str, list[dict[str, Any]]] = defaultdict(list)
        exact_terms = {
            str(x.get("keyword_text") or x.get("query") or "").strip().casefold()
            for x in signals
            if x.get("entity_type") == "keyword" and str(x.get("match_type") or "").upper() == "EXACT"
        }
        for signal in signals:
            query = str(signal.get("query") or "").strip().casefold()
            if query:
                by_query[query].append(signal)
        conflicts: list[dict[str, Any]] = []
        harvest: list[dict[str, Any]] = []
        waste: list[dict[str, Any]] = []
        for query, rows in by_query.items():
            paid = [x for x in rows if _num(x.get("spend")) > 0]
            if len({(x.get("entity_type"), x.get("entity_id")) for x in paid}) > 1:
                ranked = sorted(paid, key=lambda x: (_num(x.get("expected_profit_per_ad_dollar")), _num(x.get("sales"))), reverse=True)
                total_spend = sum(_num(x.get("spend")) for x in paid)
                conflicts.append({
                    "query": query,
                    "entities": [{"entity_type": x.get("entity_type"), "entity_id": x.get("entity_id"), "campaign_id": x.get("campaign_id"), "spend": x.get("spend"), "expected_profit_per_ad_dollar": x.get("expected_profit_per_ad_dollar")} for x in ranked[:8]],
                    "total_spend": round(total_spend, 4),
                    "winner_entity_id": ranked[0].get("entity_id") if ranked else None,
                    "interpretation": "Overlapping query traffic. Treat as a routing/isolation opportunity, not an automatic negative; preserve the path with the best marginal economics and strategic role.",
                })
            search_rows = [x for x in rows if x.get("entity_type") in {"search_term", "searchterm"}]
            for x in search_rows:
                orders = _num(x.get("orders")); clicks = _num(x.get("clicks")); profit = _num(x.get("expected_profit_per_ad_dollar"))
                if orders >= 2 and profit > 0 and query not in exact_terms:
                    harvest.append({"query": query, "source_entity_id": x.get("entity_id"), "campaign_id": x.get("campaign_id"), "orders": orders, "spend": x.get("spend"), "expected_profit_per_ad_dollar": profit, "confidence": x.get("evidence_confidence")})
                if orders <= 0 and clicks >= 12 and profit < 0:
                    waste.append({"query": query, "source_entity_id": x.get("entity_id"), "campaign_id": x.get("campaign_id"), "clicks": clicks, "spend": x.get("spend"), "confidence": x.get("evidence_confidence"), "interpretation": "Candidate for negative/routing/bid restructuring after strategic relevance is checked."})
        conflicts.sort(key=lambda x: x["total_spend"], reverse=True)
        harvest.sort(key=lambda x: x["expected_profit_per_ad_dollar"] * max(1.0, x["orders"]), reverse=True)
        waste.sort(key=lambda x: x["spend"], reverse=True)
        return {"query_conflicts": conflicts[:40], "harvest_candidates": harvest[:50], "waste_candidates": waste[:50]}

    @staticmethod
    def _dimension_opportunities(signals: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        placements = [x for x in signals if x.get("placement") and _num(x.get("spend")) > 0]
        audiences = [x for x in signals if x.get("audience") and _num(x.get("spend")) > 0]
        video = [x for x in signals if str(x.get("ad_format") or "").lower() == "video" and _num(x.get("spend")) > 0]
        budget = [x for x in signals if x.get("entity_type") == "campaign" and (x.get("budget_status") or x.get("budget_utilization_pct") is not None)]
        def compact(x: dict[str, Any]) -> dict[str, Any]:
            return {k: x.get(k) for k in ("campaign_id", "entity_id", "placement", "audience", "ad_format", "budget_status", "budget_utilization_pct", "spend", "sales", "expected_profit_per_ad_dollar", "evidence_confidence", "opportunity_score")}
        placements.sort(key=lambda x: x["opportunity_score"], reverse=True)
        audiences.sort(key=lambda x: x["opportunity_score"], reverse=True)
        video.sort(key=lambda x: x["opportunity_score"], reverse=True)
        budget.sort(key=lambda x: (str(x.get("budget_status") or "").lower() in {"budget_capped", "out_of_budget", "limited_by_budget"}, x["opportunity_score"]), reverse=True)
        return {
            "placement_opportunities": [compact(x) for x in placements[:50]],
            "audience_opportunities": [compact(x) for x in audiences[:40]],
            "video_opportunities": [compact(x) for x in video[:30]],
            "budget_opportunities": [compact(x) for x in budget[:50]],
        }

    @staticmethod
    def _next_dollar_frontier(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        frontier = []
        for x in signals:
            roi = _num(x.get("expected_profit_per_ad_dollar"), -1.0)
            confidence = _bounded(x.get("evidence_confidence"), 0, 1)
            exploration = _num(x.get("exploration_value_score"))
            if roi <= 0 and exploration <= 0.08:
                continue
            score = max(0.0, roi) * (0.45 + 0.55 * confidence) + 0.35 * exploration
            frontier.append({
                "entity_type": x.get("entity_type"), "entity_id": x.get("entity_id"), "campaign_id": x.get("campaign_id"), "asin": x.get("asin"), "query": x.get("query"), "placement": x.get("placement"),
                "expected_profit_per_ad_dollar": x.get("expected_profit_per_ad_dollar"), "evidence_confidence": x.get("evidence_confidence"), "exploration_value_score": x.get("exploration_value_score"), "capital_priority_score": round(score, 6),
                "allocation_role": "exploit" if roi > 0.10 and confidence >= 0.35 else "learn",
            })
        frontier.sort(key=lambda x: x["capital_priority_score"], reverse=True)
        return frontier[:80]

    def planner_context(self, owner_snapshot: dict[str, Any]) -> dict[str, Any]:
        self.ingest_external_economics(None)
        self.refresh_experiments()
        operator = dict(owner_snapshot.get("operator") or {})
        objectives = dict(operator.get("objectives") or {})
        break_even_acos = _bounded(objectives.get("break_even_acos_pct"), 0.1, 100.0, 35.0)
        proxy_margin = break_even_acos / 100.0
        economics = self._latest_economics()
        facts = self._preferred_facts()
        prior_facts = [x for x in facts if x.get("entity_type") == "advertised_product"]
        if not prior_facts:
            prior_facts = [x for x in facts if x.get("entity_type") == "campaign"]
        if not prior_facts:
            entity_types = sorted({str(x.get("entity_type") or "") for x in facts if x.get("entity_type")})
            canonical_type = entity_types[0] if entity_types else ""
            prior_facts = [x for x in facts if x.get("entity_type") == canonical_type] or facts
        total_clicks = sum(_num(x.get("clicks")) for x in prior_facts)
        total_orders = sum(_num(x.get("orders")) for x in prior_facts)
        global_cvr = total_orders / total_clicks if total_clicks > 0 else 0.08
        signals: list[dict[str, Any]] = []
        for row in facts:
            clicks = _num(row.get("clicks")); orders = _num(row.get("orders")); spend = _num(row.get("spend")); sales = _num(row.get("sales"))
            cpc = spend / clicks if clicks > 0 else 0.0
            aov = sales / orders if orders > 0 else 0.0
            cvr = _beta_signal(orders, clicks, global_cvr)
            expected_roas = (cvr["mean"] * aov / cpc) if cpc > 0 and aov > 0 else (sales / spend if spend > 0 else 0.0)
            asin = str(row.get("asin") or "").upper()
            econ = economics.get(asin, {}) if asin else {}
            margin_per_order, margin_ratio, economics_mode = self._owner_margin_for_row(row, econ, proxy_margin)
            margin_per_order = _num(margin_per_order)
            margin_ratio = _num(margin_ratio, proxy_margin)
            return_rate = _bounded(econ.get("return_rate_pct"), 0, 100, 0) / 100.0 if econ else 0.0
            margin_per_order *= 1.0 - return_rate
            expected_profit_per_click = cvr["mean"] * margin_per_order - cpc
            expected_profit_per_ad_dollar = expected_roas * margin_ratio * (1.0 - return_rate) - 1.0 if expected_roas else -1.0
            share = row.get("impression_share_pct")
            headroom = (100.0 - float(share)) / 100.0 if share is not None else 0.5
            attribution_tail_risk = self._attribution_tail_risk(row)
            try:
                raw_payload = json.loads(row.get("payload_json") or "{}")
            except Exception:
                raw_payload = {}
            confidence = cvr["confidence"] * (1.0 - 0.35 * attribution_tail_risk)
            inventory_units = econ.get("inventory_units") if econ else None
            label_days = {"today": 1.0, "intraday": 1.0, "7d": 7.0, "14d": 14.0, "28d": 28.0, "30d": 30.0, "65d": 65.0, "90d": 90.0}.get(str(row.get("window_label") or "").lower(), 30.0)
            order_velocity = orders / label_days if orders > 0 else 0.0
            inventory_days_proxy = _num(inventory_units) / order_velocity if inventory_units is not None and order_velocity > 0 else None
            featured_offer = raw_payload.get("featured_offer_eligible")
            in_stock = raw_payload.get("in_stock")
            retail_factor = 1.0
            if in_stock is False:
                retail_factor *= 0.05
            if featured_offer is False:
                retail_factor *= 0.55
            if inventory_days_proxy is not None and inventory_days_proxy < 7:
                retail_factor *= 0.45
            elif inventory_days_proxy is not None and inventory_days_proxy < 14:
                retail_factor *= 0.75
            opportunity_score = expected_profit_per_ad_dollar * (0.35 + 0.65 * confidence) * (0.5 + 0.5 * headroom) * retail_factor
            exploration_value_score = (1.0 - confidence) * (0.35 + 0.65 * headroom) * max(0.05, expected_roas * margin_ratio if expected_roas else 0.05)
            if confidence < 0.25:
                posture = "learn"
            elif expected_profit_per_ad_dollar > 0.10:
                posture = "scale"
            elif expected_profit_per_ad_dollar < -0.10:
                posture = "reduce_or_restructure"
            else:
                posture = "hold_and_measure"
            signals.append({
                "profile_id": row["profile_id"], "entity_type": row["entity_type"], "entity_id": row["entity_id"], "campaign_id": row.get("campaign_id"), "asin": asin or None, "query": row.get("query"), "match_type": row.get("match_type"), "placement": row.get("placement"), "window_label": row["window_label"],
                "keyword_text": raw_payload.get("keyword_text"), "target_type": raw_payload.get("target_type"), "audience": raw_payload.get("audience"), "ad_format": raw_payload.get("ad_format"), "bidding_strategy": raw_payload.get("bidding_strategy"), "budget_status": raw_payload.get("budget_status"), "budget_utilization_pct": raw_payload.get("budget_utilization_pct"), "featured_offer_eligible": raw_payload.get("featured_offer_eligible"), "in_stock": raw_payload.get("in_stock"), "price": raw_payload.get("price"),
                "impressions": _num(row.get("impressions")), "clicks": clicks, "spend": spend, "orders": orders, "sales": sales,
                "cvr_posterior": round(cvr["mean"], 6), "cvr_lower80": round(cvr["lower80"], 6), "evidence_confidence": round(confidence, 4),
                "observed_roas": round(sales / spend, 4) if spend > 0 else None, "expected_roas": round(expected_roas, 4) if expected_roas else None,
                "margin_mode": economics_mode, "expected_profit_per_click": round(expected_profit_per_click, 6), "expected_profit_per_ad_dollar": round(expected_profit_per_ad_dollar, 6),
                "impression_share_pct": share, "impression_rank": row.get("impression_rank"), "attribution_tail_risk": round(attribution_tail_risk, 4), "inventory_units": inventory_units, "inventory_days_proxy": None if inventory_days_proxy is None else round(inventory_days_proxy, 2), "retail_readiness_factor": round(retail_factor, 4), "opportunity_score": round(opportunity_score, 6), "exploration_value_score": round(exploration_value_score, 6), "posture": posture,
            })
        signals.sort(key=lambda x: x["opportunity_score"], reverse=True)
        latest_windows = self._latest_window_facts()
        window_comparisons = self._window_comparisons(latest_windows)
        temporal_patterns = self._temporal_patterns(latest_windows, proxy_margin)
        asin_portfolio = [x for x in signals if x.get("asin") and x.get("entity_type") == "advertised_product"]
        if not asin_portfolio:
            asin_portfolio = [x for x in signals if x.get("asin") and x.get("entity_type") == "campaign"]
        asin_portfolio = sorted(asin_portfolio, key=lambda x: x["opportunity_score"], reverse=True)[:50]
        query_diagnostics = self._query_diagnostics(signals)
        dimension_opportunities = self._dimension_opportunities(signals)
        next_dollar_frontier = self._next_dollar_frontier(signals)

        with self.store.connection() as c:
            counts = {
                "observations": int(c.execute("SELECT COUNT(*) FROM optimization_observations").fetchone()[0]),
                "outcomes": int(c.execute("SELECT COUNT(*) FROM optimization_outcomes").fetchone()[0]),
                "experiments": int(c.execute("SELECT COUNT(*) FROM optimization_experiments").fetchone()[0]),
                "evaluated_experiments": int(c.execute("SELECT COUNT(*) FROM optimization_experiments WHERE status='evaluated'").fetchone()[0]),
                "economics_asins": int(c.execute("SELECT COUNT(DISTINCT asin) FROM optimization_economics").fetchone()[0]),
            }
            experiments = [dict(r) for r in c.execute("SELECT experiment_id,hypothesis,entity_type,entity_id,primary_metric,expected_direction,baseline_value,latest_value,lift_pct,confidence,status,created_at,updated_at FROM optimization_experiments ORDER BY updated_at DESC LIMIT 40").fetchall()]
            candidates = [dict(r) for r in c.execute("SELECT candidate_id,asin,campaign_id,entity_type,entity_id,hypothesis,expected_incremental_spend,expected_incremental_sales,expected_incremental_profit,uncertainty,horizon_days,created_at FROM optimization_candidates ORDER BY created_at DESC LIMIT 60").fetchall()]
        return {
            "version": 1,
            "objective": str(objectives.get("primary") or "contribution_profit"),
            "economics_mode": "owner_economics" if economics else "break_even_acos_proxy",
            "break_even_acos_proxy_pct": break_even_acos,
            "learning_maturity": counts,
            "entity_signals": signals[:120],
            "top_scale_opportunities": [x for x in signals if x["posture"] == "scale"][:30],
            "top_learning_opportunities": sorted([x for x in signals if x["posture"] == "learn"], key=lambda x: x["exploration_value_score"], reverse=True)[:20],
            "top_reduce_or_restructure": sorted([x for x in signals if x["posture"] == "reduce_or_restructure"], key=lambda x: x["opportunity_score"])[:30],
            "asin_portfolio": asin_portfolio,
            "next_dollar_frontier": next_dollar_frontier,
            "window_comparisons": window_comparisons[:80],
            "temporal_patterns": temporal_patterns,
            **query_diagnostics,
            **dimension_opportunities,
            "planner_portfolio_candidates": candidates,
            "experiments": experiments,
            "owner_economics": [
                {k: v for k, v in row.items() if k in {"asin", "contribution_margin_pct", "contribution_margin_per_order", "unit_cogs", "amazon_fees", "promo_cost_per_order", "return_rate_pct", "inventory_units", "observed_at", "source", "evidence_ref"}}
                for row in economics.values()
            ][:200],
            "interpretation": "Decision support only. These signals never reduce the Planner's Owner-granted authority; the Planner may override them when fresh Amazon evidence supports a better portfolio decision.",
        }

    def report(self, owner_snapshot: dict[str, Any]) -> dict[str, Any]:
        context = self.planner_context(owner_snapshot)
        return {
            "generated_at": _now_iso(),
            "learning_maturity": context["learning_maturity"],
            "economics_mode": context["economics_mode"],
            "top_scale_opportunities": context["top_scale_opportunities"][:15],
            "next_dollar_frontier": context["next_dollar_frontier"][:20],
            "harvest_candidates": context["harvest_candidates"][:20],
            "query_conflicts": context["query_conflicts"][:20],
            "top_reduce_or_restructure": context["top_reduce_or_restructure"][:15],
            "experiments": context["experiments"][:20],
        }
