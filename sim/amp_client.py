"""Thin GOV REST client for the vision experiment.

Reuses the API sequence of payment-agent (simulator/run_e2e.py + gateway/hitl_bridge.py):
agent init -> hitl request (rlhf external criteria) -> poll decision / workitem -> complete workitem ->
rlhf outcome (+ feedback) -> stage ticks. Governance logic stays in GOV; nothing is decided here.
"""
import json, os, re, time
from datetime import datetime, timezone
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]


def load_env(path=ROOT / ".env"):
    env = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def iso_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def agent_slug(category, seed, pattern="vis-loco-{category}-s{stream_seed}"):
    """GOV agent names must match ^[a-z0-9][a-z0-9-]*$ (underscores in category names become hyphens).
    `pattern` comes from the experiment config (amp.agent_name_pattern); the default is Experiment 1's."""
    return pattern.format(category=category.replace('_', '-'), stream_seed=seed)


class AmpClient:
    def __init__(self, env=None, timeout=60.0):
        env = env or load_env()
        self.base = env["AMP_BACKEND_URL"].rstrip("/")
        self.key = env["AMP_API_KEY"]
        self.org_id = env["AMP_ORG_ID"]
        self.user = env["AMP_USERNAME"]
        self.http = httpx.Client(timeout=timeout, headers={"X-API-Key": self.key})
        self.legacy_authority_injected = None

    # -- low level -------------------------------------------------------
    def _req(self, method, path, ok=(200, 201, 202), **kw):
        last = None
        for attempt in range(3):
            try:
                r = self.http.request(method, self.base + path, **kw)
                break
            except httpx.HTTPError as exc:  # transient transport error
                last = exc
                time.sleep(1.0)
        else:
            raise RuntimeError(f"{method} {path} transport_error: {last}")
        if r.status_code not in ok:
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:400]}")
        return r.json() if r.content else {}

    # -- agent + policy setup ---------------------------------------------
    def register_agent(self, name, long_name):
        r = self.http.post(self.base + "/api/alp/agents/register-native",
                           json={"name": name, "long_name": long_name, "description": "vision-loco experiment agent"})
        if r.status_code == 409:
            return {"name": name, "already_registered": True}
        if r.status_code != 200:
            raise RuntimeError(f"register {name} -> {r.status_code}: {r.text[:300]}")
        return r.json()

    def install_policy(self, agent_name, policy_template_path):
        pol = json.loads(Path(policy_template_path).read_text())
        pol["org_id"], pol["agent_name"] = self.org_id, agent_name
        # Templates that predate the GOV authority-default migration (Experiments 1/2) carry no authority block.
        # GOV now resolves an absent block to the authority model, so - exactly as the migration does for existing
        # policies - such templates are installed as explicit legacy to keep the experiments reproducible.
        ops = pol.setdefault("autonomy_ops", {})
        self.legacy_authority_injected = "authority" not in ops
        if self.legacy_authority_injected:
            ops["authority"] = {"enabled": False}
        saved = self._req("POST", "/api/rlhf/policy/save", json={"agent_name": agent_name, "policy_json": pol})
        approved = self._req("POST", f"/api/agent/{agent_name}/policy/approve", json={
            "approver": self.user, "enableRlhf": True,
            "comment": "vision-loco-v1 pre-registered policy (EXPERIMENT_PLAN.md section 5)",
            "basePolicyRules": {"rejectOnHardFail": False, "approveOnAllPass": False}})
        return {"saved": saved.get("policy_version"), "approved": approved}

    def rlhf_status(self, agent_name):
        return self._req("GET", "/api/rlhf/status", params={"agent_name": agent_name})

    def bootstrap(self, agent_name, force_reset_state=False):
        return self._req("POST", "/api/rlhf/bootstrap", json={
            "org_id": self.org_id, "agent_name": agent_name,
            "enqueue_stage_tick": False, "force_reset_state": force_reset_state})

    # -- per item ------------------------------------------------------------
    def init_instance(self, agent_name, prompt):
        d = self._req("POST", "/api/agent/init", json={
            "agent_name": agent_name, "prompt": prompt, "auto_start": True, "config": {}, "metadata": {}})
        return d["instance_id"]

    def hitl_request(self, agent_name, instance_id, action_fields, criteria, sim_run_id, checkpoint_id):
        return self._req("POST", "/api/hitl/request", json={
            "caller_id": instance_id, "instance_id": instance_id, "org_id": self.org_id, "agent_name": agent_name,
            "hitl": {"enable": True, "when": "always", "who": self.user, "what": "approval", "where": "amp"},
            "rlhf": {"policy_values_source": "external", "action_fields": action_fields, "signal_fields": {},
                     "criteria": criteria, "run_mode": "sim", "sim_run_id": sim_run_id,
                     "sim_time": iso_now(), "checkpoint_id": checkpoint_id},
            "context": {"requested_by": self.user}})

    def get_decision(self, instance_id):
        return self._req("GET", "/api/hitl/get-decision", params={"caller_id": instance_id})

    def list_workitems(self):
        return self._req("GET", "/api/workitems").get("workitems", [])

    def complete_workitem(self, workitem_id, resolution):
        return self._req("PUT", f"/api/workitems/{workitem_id}/status",
                         json={"status": "Complete", "resolution": resolution})

    def submit_outcome(self, agent_name, decision_point_id, decision, reviewer, sim_run_id, seq):
        now = iso_now()
        return self._req("POST", "/api/rlhf/outcome", json={
            "org_id": self.org_id, "agent_name": agent_name, "decision_point_id": decision_point_id,
            "human": {"decision": decision, "user_id": reviewer, "role": "sim_human",
                      "comment": f"vision_oracle seq={seq}"},
            "run_mode": "sim", "sim_run_id": sim_run_id, "sim_time": now,
            "checkpoint_id": f"seq-{seq}", "completed_at": now})

    def submit_feedback(self, instance_id, outcome="succeeded", notes="oracle-correct"):
        return self._req("POST", "/api/rlhf/outcome/feedback", json={
            "org_id": self.org_id, "instance_id": instance_id, "outcome": outcome,
            "outcome_source": "agent_callback", "notes": notes})

    def set_state(self, agent_name, instance_id, state):
        r = self.http.post(self.base + "/api/agent/setState",
                           json={"agent_name": agent_name, "instance_id": instance_id, "state": state})
        return r.status_code

    def tick(self, agent_name, tick_minutes):
        return self._req("POST", "/api/rlhf/stage_tick/trigger", json={
            "org_id": self.org_id, "agent_name": agent_name, "tick_minutes": tick_minutes})


class HumanSession:
    """Human (superadmin) session, used ONLY for privileged RLHF model/stage-promotion approvals (decision D3).

    Ordinary oracle decisions go through the API key, which the PI granted `hitl:resolve` (2026-09-23). GOV never
    lets an API key resolve privileged RLHF approvals, so - with the PI's explicit authorization - those use a
    normal login session (cookie + double-submit CSRF header). Cookies are Secure-flagged, so they are sent
    explicitly rather than through the http cookie jar. One login only (failed attempts count toward lockout).
    """

    def __init__(self, env=None, timeout=60.0):
        env = env or load_env()
        self.base = env["AMP_BACKEND_URL"].rstrip("/")
        self.user, self._pw = env["AMP_USERNAME"], env["AMP_PASSWORD"]
        self.http = httpx.Client(timeout=timeout)
        self.token = self.csrf = None
        self.approvals = []  # audit trail of admin approvals

    def login(self):
        r = self.http.post(self.base + "/api/login", json={"username": self.user, "password": self._pw})
        if r.status_code != 200 or not r.json().get("success", True):
            raise RuntimeError(f"login failed: HTTP {r.status_code} {r.text[:120]} (not retrying: lockout risk)")
        self.token = r.headers.get("X-Session-Token") or r.cookies.get("amp_session")
        self.csrf = r.cookies.get("amp_csrf")
        if not self.token or not self.csrf:
            raise RuntimeError("login ok but session token / csrf cookie missing")
        return True

    def _headers(self):
        return {"Cookie": f"amp_session={self.token}; amp_csrf={self.csrf}", "X-CSRF-Token": self.csrf}

    def _req(self, method, path, ok=(200, 201, 202), **kw):
        r = self.http.request(method, self.base + path, headers=self._headers(), **kw)
        if r.status_code == 401:  # expired session: re-login once
            self.login()
            r = self.http.request(method, self.base + path, headers=self._headers(), **kw)
        if r.status_code not in ok:
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:400]}")
        return r.json() if r.content else {}

    def list_workitems(self):
        return self._req("GET", "/api/workitems").get("workitems", [])

    def complete_workitem(self, workitem_id, resolution, admin=False):
        out = self._req("PUT", f"/api/workitems/{workitem_id}/status",
                        json={"status": "Complete", "resolution": resolution})
        if admin:
            self.approvals.append({"workitem_id": workitem_id, "resolution": resolution, "at": iso_now()})
        return out
