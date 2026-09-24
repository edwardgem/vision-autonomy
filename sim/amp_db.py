"""READ-ONLY views of AMP's own MySQL records (ground truth of what AMP decided). Never writes.

Used for (a) per-decision stage / model score / probe flag / routing exactly as AMP stored them,
(b) detecting that AMP's RLHF job queue for an agent is idle, (c) exporting the agent's event log.
Credentials are read from amp-backend/.env at runtime and are never printed or copied.
"""
import json
from pathlib import Path
import mysql.connector
from sim.amp_client import load_env

BACKEND_ENV = Path("/Users/edwardc/Projects/amp-backend/.env")


class AmpDB:
    def __init__(self, org_id):
        e = load_env(BACKEND_ENV)
        self._cfg = dict(host=e.get("MYSQL_HOST", "127.0.0.1"), port=int(e.get("MYSQL_PORT", "3306")),
                         database=e.get("MYSQL_DATABASE", "amp"), user=e["MYSQL_USER"], password=e["MYSQL_PASSWORD"])
        self.org_id = org_id

    def _q(self, sql, params=()):
        conn = mysql.connector.connect(**self._cfg)   # always closed (pool-leak rule)
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(sql, params)
            return cur.fetchall()
        finally:
            conn.close()

    @staticmethod
    def _j(v):
        return v if isinstance(v, dict) else (json.loads(v) if v else {})

    def decision_by_instance(self, agent, instance_id):
        rows = self._q(
            "SELECT ar.request_id, ar.created_at, ar.decision_stage, ar.model_version, ar.model_score, ar.threshold_used, "
            "ar.signals_json, ao.decision_mode, ao.decision AS outcome_decision, ao.auto_decision_reason "
            "FROM rlhf_approval_request ar LEFT JOIN rlhf_approval_outcome ao ON ao.request_id = ar.request_id "
            "WHERE ar.org_id=%s AND ar.agent_name=%s "
            "AND JSON_UNQUOTE(JSON_EXTRACT(ar.metadata_json,'$.agent_instance_id'))=%s "
            "ORDER BY ar.created_at DESC LIMIT 1", (self.org_id, agent, instance_id))
        if not rows:
            return None
        r = rows[0]
        r["signals"] = self._j(r.pop("signals_json"))
        return r

    def agent_state(self, agent):
        rows = self._q("SELECT * FROM rlhf_agent_state WHERE org_id=%s AND agent_name=%s", (self.org_id, agent))
        if not rows:
            return None
        r = rows[0]
        r["metadata"] = self._j(r.pop("metadata_json"))
        return r

    def rlhf_enabled(self, agent):
        rows = self._q("SELECT enabled FROM rlhf_agent_config WHERE org_id=%s AND agent_name=%s", (self.org_id, agent))
        return bool(rows and int(rows[0]["enabled"]))

    def pending_admin_workitems(self, agent):
        """Privileged RLHF workitems (model approval / stage 2 promotion) still pending for this agent.
        Looked up by id pattern so discovery does not depend on which user AMP assigned them to."""
        return [r["workitem_id"] for r in self._q(
            "SELECT workitem_id FROM workitems WHERE instance_id LIKE %s AND workitem_id LIKE 'rlhf-%%' "
            "AND status='Pending'", (agent + "-%",))]

    def job(self, job_id):
        rows = self._q("SELECT job_id, job_type, status, attempts, last_error FROM rlhf_jobs WHERE job_id=%s", (job_id,))
        return rows[0] if rows else None

    def open_jobs(self, agent):
        return self._q("SELECT job_id, job_type, status FROM rlhf_jobs WHERE org_id=%s AND agent_name=%s "
                       "AND status IN ('queued','running')", (self.org_id, agent))

    def failed_jobs(self, agent):
        return self._q("SELECT job_id, job_type, attempts, last_error FROM rlhf_jobs WHERE org_id=%s AND agent_name=%s "
                       "AND status='failed'", (self.org_id, agent))

    def job_counts(self, agent):
        """Pipeline jobs only (EXTRACT/TRAIN/EVAL/ACTIVATE/...); STAGE_TICK rows are excluded because our own ticks add them."""
        return {f"{r['job_type']}:{r['status']}": int(r["n"]) for r in self._q(
            "SELECT job_type, status, COUNT(*) n FROM rlhf_jobs WHERE org_id=%s AND agent_name=%s "
            "AND job_type <> 'STAGE_TICK' GROUP BY job_type, status", (self.org_id, agent))}

    def tick_job_count(self, agent):
        return int(self._q("SELECT COUNT(*) n FROM rlhf_jobs WHERE org_id=%s AND agent_name=%s AND job_type='STAGE_TICK'",
                           (self.org_id, agent))[0]["n"])

    def request_count(self, agent):
        return int(self._q("SELECT COUNT(*) n FROM rlhf_approval_request WHERE org_id=%s AND agent_name=%s",
                           (self.org_id, agent))[0]["n"])

    def events(self, agent):
        out = []
        for r in self._q("SELECT ts, event_type, payload_json FROM rlhf_events WHERE org_id=%s AND agent_name=%s "
                         "ORDER BY id", (self.org_id, agent)):
            out.append({"ts": str(r["ts"]), "event_type": r["event_type"], "payload": self._j(r["payload_json"])})
        return out
