"""Operations helper (amendment v1.3): stop idle RLHF workers of finished / scratch vis-loco agents.

AMP keeps one scoped worker alive per agent whose pipeline is enabled (rlhf_agent_config.enabled=1) and respawns killed
ones, so the only supported way to stop a worker is AMP's own RLHF toggle (PUT /api/agent/<name>/policies/current/rlhf_enabled).
That flips `rlhf_enabled` in the agent's policy files and re-upserts its config row (values recomputed from the same policy);
it does not reset stage state and deletes nothing. Before each toggle this script snapshots the config row, state row and policy
files (sha256 + copies) under results/ops/, and afterwards verifies that ONLY the rlhf_enabled flag changed. Reversible with enabled=true.

Never touches agents that are not named vis-loco-* / vis-loco2-* / vis-auth-* / vis-exp3-* (e.g. invoice-payment-agent-5c58).
"""
import argparse, hashlib, json, os, re, shutil, subprocess, time
from pathlib import Path
from sim.amp_client import AmpClient, iso_now, ROOT

OPS = ROOT / "results" / "ops"
AGENTS_ROOT = Path(os.environ.get("AMP_AGENTS_ROOT", str(ROOT.parent / "agents")))  # platform agent directories, not in this repo


def running_worker_agents():
    out = subprocess.check_output(["ps", "-Ao", "command"], text=True)
    return sorted(set(re.findall(r"rlhf_worker\.js.*--agent_name=(\S+)", out)))


def q(db, fn, *a, tries=12):
    for i in range(tries):
        try:
            return fn(*a)
        except Exception as e:  # 'Too many connections' while the DB is saturated: back off and retry
            last = e
            time.sleep(2 + i)
    raise RuntimeError(f"db unavailable after retries: {last}")


def api_status(amp, agent, tries=8):
    last = None
    for i in range(tries):
        try:
            return amp.rlhf_status(agent)
        except Exception as e:
            last = e
            time.sleep(2 + i)
    raise RuntimeError(f"status unavailable: {last}")


def policy_files(org, agent):
    d = AGENTS_ROOT / org / agent / "policy"
    return sorted(d.glob("*.json")) if d.exists() else []


def file_state(p):
    return {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "rlhf_enabled": json.loads(p.read_text()).get("rlhf_enabled")}


def strip_flag(p):
    d = json.loads(p.read_text()); d.pop("rlhf_enabled", None)
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", nargs="*", help="explicit agent names (default: every running vis-loco-* worker)")
    ap.add_argument("--keep", nargs="*", default=[], help="agents to leave running")
    ap.add_argument("--ops-dir", default=None, help="where snapshots/log go (default results/ops = Experiment 1 record)")
    a = ap.parse_args()
    global OPS
    if a.ops_dir:
        OPS = Path(a.ops_dir)
    OPS.mkdir(parents=True, exist_ok=True)
    amp = AmpClient()
    targets = a.agents or running_worker_agents()
    targets = [t for t in targets if re.match(r"vis-(loco\d*|auth|exp3)-", t) and t not in a.keep]   # vis-loco-* (Exp 1), vis-loco2-* (Exp 2), vis-auth-* (engineering), vis-exp3-* (Exp 3)
    print("targets:", len(targets), targets)
    log = open(OPS / "toggle_log.jsonl", "a", buffering=1)
    for t in targets:
        pf = policy_files(amp.org_id, t)
        stt = api_status(amp, t)
        cfg = [stt["agent_config"]] if stt.get("agent_config") else []
        st = stt.get("state") or None
        pre = {"agent": t, "ts": iso_now(), "config_row": [{k: str(v) for k, v in r.items() if k != "params_json"} for r in cfg],
               "state": {k: str(st.get(k)) for k in ("stage", "active_model_version", "stage1_eval_rows", "last_processed_at")} if st else None,
               "policy_files": [file_state(p) for p in pf]}
        bak = OPS / "policy_backup" / t
        bak.mkdir(parents=True, exist_ok=True)
        for p in pf:
            shutil.copy2(p, bak / p.name)
        if cfg and int(cfg[0].get("enabled") or 0) == 0:
            log.write(json.dumps({"event": "already_disabled", **pre}) + "\n"); print(t, "already disabled"); continue
        strip_before = {str(p): strip_flag(p) for p in pf}
        r = amp.http.put(f"{amp.base}/api/agent/{t}/policies/current/rlhf_enabled", json={"enabled": False})
        ok = r.status_code == 200
        time.sleep(1)
        pst = api_status(amp, t)
        post_cfg = [pst["agent_config"]] if pst.get("agent_config") else []
        post_state = pst.get("state") or None
        only_flag = all(strip_flag(p) == strip_before[str(p)] for p in pf)
        post = {"http": r.status_code, "config_enabled": int(post_cfg[0]["enabled"]) if post_cfg else None,
                "state_unchanged": (st is None and post_state is None) or (st is not None and post_state is not None and
                                   all(str(st.get(k)) == str(post_state.get(k)) for k in ("stage", "active_model_version", "stage1_eval_rows", "last_processed_at"))),
                "only_rlhf_enabled_flag_changed_in_policy_files": only_flag,
                "policy_files_after": [file_state(p) for p in pf]}
        log.write(json.dumps({"event": "toggled_off", **pre, "post": post}) + "\n")
        print(t, "HTTP", r.status_code, "| config.enabled ->", post["config_enabled"], "| state unchanged:", post["state_unchanged"], "| only flag changed:", only_flag)
        if not (ok and post["config_enabled"] == 0 and post["state_unchanged"] and only_flag):
            print("STOP: unexpected effect for", t, post); return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
