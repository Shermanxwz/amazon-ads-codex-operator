from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any

from .canonical import digest
from .owner_store import OwnerStore, _autopilot_blockers, now_iso

UTC = timezone.utc
DIRECT_DURATIONS: dict[str, int | None] = {"30m": 30, "1h": 60, "2h": 120, "permanent": None}
BASE_MODES = {"autopilot", "observe", "paused"}


def _utc(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class OwnerOverrideStore(OwnerStore):
    """Owner-only, time-bounded capability for exceptional direct ad commands."""

    def __init__(self, path, audit_key: bytes):
        super().__init__(path, audit_key)
        with self.connection() as c:
            c.execute("""
            CREATE TABLE IF NOT EXISTS owner_direct_override(
              id INTEGER PRIMARY KEY CHECK(id=1), armed INTEGER NOT NULL DEFAULT 0,
              duration_code TEXT NOT NULL DEFAULT 'off', activated_at TEXT, expires_at TEXT,
              return_mode TEXT NOT NULL DEFAULT 'observe', generation INTEGER NOT NULL DEFAULT 0,
              command_active INTEGER NOT NULL DEFAULT 0, command_instruction TEXT NOT NULL DEFAULT '',
              command_started_at TEXT, updated_at TEXT NOT NULL, updated_by TEXT NOT NULL);
            """)
            if not c.execute("SELECT 1 FROM owner_direct_override WHERE id=1").fetchone():
                c.execute("INSERT INTO owner_direct_override(id,updated_at,updated_by) VALUES(1,?,?)", (now_iso(), "bootstrap"))

    def _raw_documents(self, c) -> tuple[dict[str, Any], dict[str, Any]]:
        policy = json.loads(c.execute("SELECT body_json FROM owner_documents WHERE kind='policy'").fetchone()["body_json"])
        operator = json.loads(c.execute("SELECT body_json FROM owner_documents WHERE kind='operator'").fetchone()["body_json"])
        return policy, operator

    def _bump_policy(self, c, actor: str) -> int:
        policy, _ = self._raw_documents(c)
        return int(self._put_document(c, "policy", policy, actor)["revision"])

    @staticmethod
    def _readiness(policy: dict[str, Any], operator: dict[str, Any]) -> list[str]:
        reasons: list[str] = []
        profiles = [str(x).strip() for x in operator.get("profile_ids", []) if str(x).strip() and str(x).strip() != "REPLACE_ME"]
        account = str(operator.get("advertiser_account_id") or "").strip()
        products = {str(x).upper() for x in operator.get("scope", {}).get("ad_products", []) if str(x).strip()}
        allowed = {str(x).upper() for x in policy.get("scope", {}).get("allowed_ad_products", []) if str(x).strip()}
        if not profiles:
            reasons.append("no real profile_id configured")
        if not account or account == "REPLACE_ME":
            reasons.append("no real advertiser_account_id configured")
        if products != {"SPONSORED_PRODUCTS"}:
            reasons.append("Owner Direct Override is certified only for Sponsored Products")
        if not products.issubset(allowed):
            reasons.append("operator ad-product scope exceeds Owner policy scope")
        return reasons

    @staticmethod
    def _view(row) -> dict[str, Any]:
        expires_at = str(row["expires_at"] or "") or None
        expires = _utc(expires_at)
        return {
            "armed": bool(row["armed"]), "duration": str(row["duration_code"]),
            "activated_at": str(row["activated_at"] or "") or None, "expires_at": expires_at,
            "permanent": bool(row["armed"] and not expires_at),
            "remaining_seconds": None if expires is None else max(0, int((expires - datetime.now(UTC)).total_seconds())),
            "return_mode": str(row["return_mode"] or "observe"), "generation": int(row["generation"]),
            "command_active": bool(row["command_active"]), "command_instruction": str(row["command_instruction"] or ""),
            "command_started_at": str(row["command_started_at"] or "") or None,
            "updated_at": str(row["updated_at"]), "updated_by": str(row["updated_by"]),
        }

    def _return_mode(self, c, requested: str) -> str:
        if requested != "autopilot":
            return requested if requested in BASE_MODES else "observe"
        policy, operator = self._raw_documents(c)
        return "observe" if _autopilot_blockers(policy, operator) else "autopilot"

    def _deactivate(self, c, *, target_mode: str, actor: str, event_type: str, reason: str) -> None:
        row = c.execute("SELECT * FROM owner_direct_override WHERE id=1").fetchone()
        if not row:
            raise RuntimeError("Owner Direct Override state missing")
        revision = self._bump_policy(c, actor) if bool(row["armed"] or row["command_active"]) else int(c.execute("SELECT revision FROM owner_documents WHERE kind='policy'").fetchone()["revision"])
        target_mode = self._return_mode(c, target_mode)
        stamp = now_iso()
        c.execute("""UPDATE owner_direct_override SET armed=0,duration_code='off',activated_at=NULL,expires_at=NULL,
                     return_mode=?,generation=generation+1,command_active=0,command_instruction='',command_started_at=NULL,
                     updated_at=?,updated_by=? WHERE id=1""", (target_mode, stamp, actor))
        c.execute("UPDATE control_state SET mode=?,updated_at=?,updated_by=? WHERE id=1", (target_mode, stamp, actor))
        self._append_audit(c, event_type, actor, {"reason": reason, "return_mode": target_mode, "previous_duration": str(row["duration_code"]), "previous_generation": int(row["generation"]), "policy_revision": revision})

    def _expire(self) -> None:
        with self.connection() as c:
            row = c.execute("SELECT * FROM owner_direct_override WHERE id=1").fetchone()
            if not row or not bool(row["armed"]):
                return
            expires = _utc(str(row["expires_at"] or "") or None)
            if expires is not None and expires <= datetime.now(UTC):
                self._deactivate(c, target_mode=str(row["return_mode"] or "observe"), actor="owner-direct-override", event_type="owner.direct_override_expired", reason="authorization window expired")

    def direct_override_state(self) -> dict[str, Any]:
        self._expire()
        with self.connection() as c:
            row = c.execute("SELECT * FROM owner_direct_override WHERE id=1").fetchone()
        if not row:
            raise RuntimeError("Owner Direct Override state missing")
        return self._view(row)

    def snapshot(self) -> dict[str, Any]:
        self._expire()
        value = super().snapshot()
        with self.connection() as c:
            row = c.execute("SELECT * FROM owner_direct_override WHERE id=1").fetchone()
        state = self._view(row)
        value["direct_override"] = state
        if state["armed"] and state["command_active"]:
            instruction = state["command_instruction"]
            direct = {
                "active": True, "authority": "all-sponsored-products-advertising-operations",
                "generation": state["generation"], "expires_at": state["expires_at"], "permanent_window": state["permanent"],
                "instruction": instruction, "instruction_hash": hashlib.sha256(instruction.encode()).hexdigest(),
                "bypasses": ["autonomy_matrix", "money_caps", "bid_caps", "placement_caps", "cooldowns", "campaign_naming", "paused_create_requirement", "managed_asin_filter", "routine_confidence_thresholds", "routine_recovery_breaker"],
                "retained_invariants": ["configured_advertiser_and_profile_scope", "Sponsored_Products_only", "Owner_authentication", "Emergency_Stop", "sealed_exact_MCP_call", "one_use_executor_grant", "fresh_prewrite_state", "independent_verification", "audit_chain", "no_billing_credentials_user_admin_or_account_delete"],
            }
            effective = dict(value["policy"])
            effective["owner_direct_override"] = direct
            value["policy"] = effective
            value["policy_hash"] = digest(effective)
        return value

    def arm_direct_override(self, duration: str, actor: str = "owner-web") -> dict[str, Any]:
        code = str(duration).strip().lower()
        if code not in DIRECT_DURATIONS:
            raise ValueError("duration must be 30m, 1h, 2h, or permanent")
        with self.connection() as c:
            control = c.execute("SELECT * FROM control_state WHERE id=1").fetchone()
            if not control:
                raise RuntimeError("owner control state missing")
            if bool(control["emergency_stop"]):
                raise ValueError("clear Emergency Stop before arming Owner Direct Override")
            policy, operator = self._raw_documents(c)
            blockers = self._readiness(policy, operator)
            if blockers:
                raise ValueError("direct override readiness failed: " + "; ".join(blockers))
            previous = c.execute("SELECT * FROM owner_direct_override WHERE id=1").fetchone()
            return_mode = str(previous["return_mode"] if previous and bool(previous["armed"]) else control["mode"])
            if return_mode not in BASE_MODES:
                return_mode = "observe"
            revision = self._bump_policy(c, actor)
            now = datetime.now(UTC); minutes = DIRECT_DURATIONS[code]; expires = None if minutes is None else now + timedelta(minutes=minutes)
            generation = int(previous["generation"] if previous else 0) + 1; stamp = now_iso()
            c.execute("""UPDATE owner_direct_override SET armed=1,duration_code=?,activated_at=?,expires_at=?,return_mode=?,generation=?,
                         command_active=0,command_instruction='',command_started_at=NULL,updated_at=?,updated_by=? WHERE id=1""",
                      (code, now.isoformat(), expires.isoformat() if expires else None, return_mode, generation, stamp, actor))
            c.execute("UPDATE control_state SET mode='autopilot',updated_at=?,updated_by=? WHERE id=1", (stamp, actor))
            self._append_audit(c, "owner.direct_override_armed", actor, {"duration": code, "expires_at": expires.isoformat() if expires else None, "return_mode": return_mode, "generation": generation, "policy_revision": revision})
        return self.snapshot()

    def begin_direct_command(self, instruction: str, actor: str = "owner-direct-command") -> dict[str, Any]:
        text = str(instruction or "").strip()
        if not text:
            raise ValueError("direct command instruction must not be empty")
        if len(text) > 12000:
            raise ValueError("direct command instruction is too long")
        self._expire()
        with self.connection() as c:
            row = c.execute("SELECT * FROM owner_direct_override WHERE id=1").fetchone(); control = c.execute("SELECT * FROM control_state WHERE id=1").fetchone()
            if not row or not bool(row["armed"]):
                raise ValueError("Owner Direct Override is not armed in Owner Control")
            if bool(row["command_active"]):
                raise ValueError("another Owner direct command is already active")
            if not control or bool(control["emergency_stop"]) or str(control["mode"]) != "autopilot":
                raise ValueError("Owner authority is not available for a direct command")
            revision = self._bump_policy(c, actor); generation = int(row["generation"]) + 1; stamp = now_iso()
            c.execute("UPDATE owner_direct_override SET generation=?,command_active=1,command_instruction=?,command_started_at=?,updated_at=?,updated_by=? WHERE id=1", (generation, text, stamp, stamp, actor))
            self._append_audit(c, "owner.direct_command_started", actor, {"generation": generation, "policy_revision": revision, "instruction": text, "instruction_hash": hashlib.sha256(text.encode()).hexdigest(), "window_expires_at": str(row["expires_at"] or "") or None})
        return {"generation": generation, "policy_revision": revision}

    def finish_direct_command(self, generation: int, actor: str = "direct-controller") -> dict[str, Any]:
        self._expire()
        with self.connection() as c:
            row = c.execute("SELECT * FROM owner_direct_override WHERE id=1").fetchone()
            if not row or not bool(row["command_active"]):
                pass
            elif int(row["generation"]) != int(generation):
                raise ValueError("direct command generation changed before completion")
            else:
                revision = self._bump_policy(c, actor); stamp = now_iso()
                c.execute("UPDATE owner_direct_override SET generation=generation+1,command_active=0,command_instruction='',command_started_at=NULL,updated_at=?,updated_by=? WHERE id=1", (stamp, actor))
                self._append_audit(c, "owner.direct_command_finished", actor, {"generation": int(generation), "policy_revision": revision})
        return self.direct_override_state()

    def clear_direct_override(self, actor: str = "owner-web", *, target_mode: str | None = None, reason: str = "Owner cleared direct override") -> dict[str, Any]:
        self._expire()
        with self.connection() as c:
            row = c.execute("SELECT * FROM owner_direct_override WHERE id=1").fetchone()
            if row and bool(row["armed"]):
                target = target_mode or str(row["return_mode"] or "observe")
                if target not in BASE_MODES:
                    raise ValueError("target mode must be autopilot, observe, or paused")
                self._deactivate(c, target_mode=target, actor=actor, event_type="owner.direct_override_cleared", reason=reason)
        return self.snapshot()

    def set_mode(self, mode: str, actor: str = "owner-web") -> dict[str, Any]:
        normalized = str(mode).lower().strip()
        if normalized not in BASE_MODES:
            raise ValueError("mode must be autopilot, observe, or paused")
        state = self.direct_override_state()
        if not state["armed"]:
            return super().set_mode(normalized, actor=actor)
        if normalized == "autopilot":
            blockers = _autopilot_blockers(self._document("policy")["body"], self._document("operator")["body"])
            if blockers:
                raise ValueError("autopilot readiness failed: " + "; ".join(blockers))
        with self.connection() as c:
            old = c.execute("SELECT mode FROM control_state WHERE id=1").fetchone()
            self._deactivate(c, target_mode=normalized, actor=actor, event_type="owner.direct_override_cleared", reason=f"Owner selected normal mode {normalized}")
            self._append_audit(c, "owner.mode_changed", actor, {"from": old["mode"] if old else None, "to": normalized})
        return self.snapshot()

    def system_pause(self, reason: str, actor: str = "controller") -> dict[str, Any]:
        if not self.direct_override_state()["armed"]:
            return super().system_pause(reason, actor=actor)
        with self.connection() as c:
            self._deactivate(c, target_mode="paused", actor=actor, event_type="owner.direct_override_revoked_by_system", reason=str(reason)[:2000])
            self._append_audit(c, "system.auto_paused", actor, {"previous_mode": "autopilot", "reason": str(reason)[:2000]})
        return self.snapshot()

    def emergency_stop(self, actor: str = "owner-web") -> dict[str, Any]:
        if not self.direct_override_state()["armed"]:
            return super().emergency_stop(actor=actor)
        with self.connection() as c:
            self._deactivate(c, target_mode="paused", actor=actor, event_type="owner.direct_override_revoked_by_emergency_stop", reason="Emergency Stop")
            stamp = now_iso(); c.execute("UPDATE control_state SET mode='paused',emergency_stop=1,updated_at=?,updated_by=? WHERE id=1", (stamp, actor))
            self._append_audit(c, "owner.emergency_stop", actor, {"previous_mode": "autopilot"})
        return self.snapshot()
