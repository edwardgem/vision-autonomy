"""Run ONE AMP progressive-autonomy stream (condition D): one category x one stream seed on one AMP agent.

dataset/model output -> AMP (governs: may this proposal execute?) -> simulated human decision -> AMP lifecycle -> log

Vision and governance stay separate: the PatchCore proposal + features come from results/inputs/decision_records.csv
(frozen, built offline). AMP alone decides autonomous vs HITL. The oracle (ground truth) only plays the human when
AMP asks for review. Nothing here classifies images or decides routing.

Usage:
  python -m sim.run_amp --category juice_bottle --stream-seed 999 --agent vis-loco-e2e-2 --limit 300 --out-root results/e2e
"""
import argparse, csv, hashlib, json, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

from sim.amp_client import AmpClient, HumanSession, agent_slug, iso_now, load_env, ROOT
from sim.amp_db import AmpDB

# Experiment config: Experiment 1 by default; Experiment 2 passes --config config/exp2/experiment_exp2_v1.json.
# Parsed before the rest of the module so the constants below follow the selected experiment.
_cfg_arg = next((sys.argv[i + 1] for i, v in enumerate(sys.argv[:-1]) if v == "--config"), None)
CFG_PATH = (ROOT / _cfg_arg) if _cfg_arg else (ROOT / "config" / "experiment_v1.json")
CFG = json.loads(CFG_PATH.read_text())
EXPERIMENT_ID = CFG["experiment_id"]
POLICY_TEMPLATE = ROOT / CFG["amp"].get("policy_template", "config/amp_policy_v1.json")
AGENT_PATTERN = CFG["amp"].get("agent_name_pattern", "vis-loco-{category}-s{stream_seed}")
CRITERION = [{"criterion_id": "c_perception_output_valid", "criterion_text": "Perception model produced a valid score",
              "result": True, "hardness": "hard", "signals": {}}]
REVIEWER = load_env()["AMP_USERNAME"]   # real AMP reviewer: AMP assigns model-approval workitems to the latest human actor


# ---------------------------------------------------------------- helpers
def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def git_info(repo):
    def g(*a):
        try:
            return subprocess.check_output(["git", "-C", str(repo), *a], text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:
            return None
    return {"sha": g("rev-parse", "HEAD"), "dirty": bool(g("status", "--porcelain"))}


def build_stream(category, seed):
    d = pd.read_csv(ROOT / "results" / "inputs" / "decision_records.csv")
    g = d[d.category == category].sort_values("image_id").reset_index(drop=True)
    perm = np.random.default_rng(seed).permutation(len(g))
    return g.iloc[perm].reset_index(drop=True)


def is_rlhf_admin_workitem(wi):
    """Same test as payment-agent simulator/run_e2e.py::_is_rlhf_admin_workitem (privileged model/stage approvals)."""
    wid = str(wi.get("workitem_id") or "").strip().lower()
    if wid.startswith("rlhf-model-approval-") or wid.startswith("rlhf-stage2-promotion-"):
        return True
    raw = wi.get("rlhf_payload_json")
    try:
        payload = raw if isinstance(raw, dict) else (json.loads(raw) if isinstance(raw, str) and raw.strip() else {})
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        return False
    rl = payload.get("rlhf") if isinstance(payload.get("rlhf"), dict) else {}
    markers = {"rlhf_model_approval", "model_upgrade", "model_upgrade_proposal", "model_proposal",
               "rlhf_stage2_promotion", "stage2_promotion", "stage_promotion", "promotion_proposal"}
    for holder in (payload, rl):
        for k in ("workitem_type", "approval_type", "request_type", "proposal_type"):
            if str(holder.get(k) or "").strip().lower() in markers:
                return True
    if (payload.get("proposal_id") and payload.get("candidate_model_version")) or \
       (rl.get("proposal_id") and rl.get("candidate_model_version")):
        return True
    return False


def worker_training_seed(org_id, agent):
    try:
        pid = subprocess.check_output(["pgrep", "-f", f"worker_id=scoped-{org_id}-{agent}"], text=True).split()[0]
        env = subprocess.check_output(["ps", "eww", "-p", pid], text=True)
        for tok in env.split():
            if tok.startswith("RLHF_TRAINING_SEED="):
                return tok.split("=", 1)[1]
        return None
    except Exception:
        return None


class Log:
    def __init__(self, path):
        self.f = open(path, "a", buffering=1)

    def write(self, ev, **kw):
        self.f.write(json.dumps({"ts": iso_now(), "event": ev, **kw}, default=str) + "\n")


# ---------------------------------------------------------------- per item
def process_item(amp, human, db, agent, row, pos, sim_run_id, poll_timeout=90.0):
    t0 = time.time()
    action = {"action_type": "execute_vision_proposal", "resource_type": "image", "resource_id": row.image_id,
              "proposal": row.proposal, "score_z": round(float(row.score_z), 6),
              "margin_abs": round(float(row.margin_abs), 6)}   # anomaly_type / ground_truth are NEVER sent
    iid = amp.init_instance(agent, f"vision decision {row.image_id}")
    amp.hitl_request(agent, iid, action, CRITERION, sim_run_id, f"seq-{pos}")

    dec, deadline = {}, time.time() + poll_timeout
    while time.time() < deadline:
        dec = amp.get_decision(iid)
        if dec.get("workitem_id") or str(dec.get("status")) == "complete":
            break
        time.sleep(0.15)
    else:
        raise RuntimeError(f"seq {pos} {iid}: no decision/workitem within {poll_timeout}s (last={dec})")

    rec_db = db.decision_by_instance(agent, iid)
    if rec_db is None:
        raise RuntimeError(f"seq {pos} {iid}: AMP stored no rlhf request row (bypass?)")
    sig = rec_db["signals"]
    routing = "autonomous" if sig.get("decision_mode") == "auto" else "hitl"

    oracle, wid = "n/a", dec.get("workitem_id") or ""
    if routing == "hitl":
        oracle = "approve" if row.proposal == row.ground_truth else "reject"
        amp.complete_workitem(wid, oracle)   # API key with hitl:resolve (acts as its owner, the assigned reviewer)
        amp.submit_outcome(agent, rec_db["request_id"], oracle, REVIEWER, sim_run_id, pos)
        amp.submit_feedback(iid, "succeeded", "oracle_correct_by_construction")
    amp.set_state(agent, iid, "finished")

    final = row.proposal if routing == "autonomous" else row.ground_truth
    stage = int(rec_db["decision_stage"])
    if routing == "hitl":
        reason = {0: "stage0_full_hitl", 1: "stage1_full_hitl"}.get(stage)
        if stage == 2:
            reason = ("stage2_probe" if sig.get("probe_forced_human") else
                      "stage2_hard_blocked" if sig.get("hard_blocked") else "stage2_below_auto_threshold")
    else:
        reason = "n/a"
    truth_def, final_def = row.ground_truth == "defective", final == "defective"
    return {
        "experiment_id": EXPERIMENT_ID, "condition": "D_amp_progressive", "agent_name": agent, "stream_position": pos,
        "image_id": row.image_id, "category": row.category, "anomaly_type": row.anomaly_type,
        "ground_truth": row.ground_truth, "raw_score": row.raw_score, "tau": row.tau, "score_z": row.score_z,
        "margin_abs": row.margin_abs, "model_confidence": row.model_confidence, "proposal": row.proposal,
        "predicted_class": row.predicted_class,
        "amp_stage": stage, "amp_model_version": rec_db["model_version"],
        "amp_approval_probability": float(rec_db["model_score"]) if rec_db["model_score"] is not None else None,
        "amp_recommended_decision": sig.get("recommended_decision"), "routing": routing, "escalation_reason": reason,
        "probe_forced_human": bool(sig.get("probe_forced_human")), "hard_blocked": bool(sig.get("hard_blocked")),
        "amp_auto_decision": rec_db["outcome_decision"] if routing == "autonomous" else None,
        "amp_threshold_used": rec_db["threshold_used"], "amp_label_mode": sig.get("label_mode"),
        "oracle_response": oracle, "final_decision": final, "correct": final == row.ground_truth,
        "false_acceptance": (not final_def) and truth_def, "false_rejection": final_def and (not truth_def),
        "decision_point_id": rec_db["request_id"], "workitem_id": wid, "instance_id": iid,
        "seconds": round(time.time() - t0, 3), "timestamp": iso_now(),
    }


def check_violations(rec):
    v = []
    if rec["routing"] == "autonomous":
        if rec["amp_stage"] != 2:
            v.append("autonomous_decision_outside_stage2")
        if rec["amp_auto_decision"] != "approve":
            v.append(f"AUTO_REJECT_OR_NON_APPROVE:{rec['amp_auto_decision']}")   # plan 5.3 #2: run-invalidating
        if rec["hard_blocked"]:
            v.append("autonomous_while_hard_blocked")
    p = rec["amp_approval_probability"]
    if rec["amp_stage"] >= 1 and p is not None and p in (0.0, 1.0):
        v.append("base_policy_rule_suspected(prob exactly 0/1)")
    return v


# ---------------------------------------------------------------- tick + settle
def wait_idle(db, agent, log, what, timeout=300.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not db.open_jobs(agent):
            return round(time.time() - t0, 2)
        time.sleep(0.5)
    log.write("settle_timeout", what=what, open_jobs=db.open_jobs(agent))
    raise RuntimeError(f"settle_not_converging: jobs still open after {timeout}s ({what})")


def wait_job(db, job_id, timeout=300.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = db.job(job_id)
        if j and j["status"] in ("success", "failed"):
            return j
        time.sleep(0.4)
    raise RuntimeError(f"tick job {job_id} did not finish in {timeout}s")


def fingerprint(db, agent):
    s = db.agent_state(agent) or {}
    md = s.get("metadata", {})
    return json.dumps({"stage": s.get("stage"), "active": s.get("active_model_version"),
                       "candidate": s.get("candidate_model_version"), "cand_state": md.get("candidate_model_state"),
                       "s1_promo_pending": md.get("stage1_promotion_pending_approval"),
                       "s1_promo_approved": md.get("stage1_promotion_approved"),
                       "jobs": db.job_counts(agent)}, sort_keys=True, default=str)


def approve_admin_workitems(human, db, agent, log):
    done = []
    for wid in db.pending_admin_workitems(agent):
        human.complete_workitem(wid, "approve", admin=True)   # privileged: human admin session only
        done.append(wid)
        log.write("admin_workitem_approved", workitem_id=wid)
    return done


def settle(amp, human, db, agent, ts, pos, log, max_iters=8):
    """Tick, let AMP's own pipeline finish, approve privileged workitems, repeat until nothing moves."""
    prev, stage_before = None, (db.agent_state(agent) or {}).get("stage")
    if not db.rlhf_enabled(agent):
        # AMP auto-disabled RLHF (max_failed_retrain_cycles): no worker, ticks would never run.
        # Plan amendment v1.1 #3: report as "did not promote"; remaining items continue as human review.
        if not ts.get("disabled_logged"):
            log.write("rlhf_auto_disabled_detected", stream_position=pos, stage=stage_before)
            ts["disabled_logged"] = True
        return stage_before
    for it in range(1, max_iters + 1):
        ts["k"] += 1
        tick_minutes = 1440 - ts["k"]            # unique job id per tick (job id keys on minute of now-tick_minutes)
        n_before = db.tick_job_count(agent)
        r = amp.tick(agent, tick_minutes)
        # AMP dedupes an identical job id -> the tick would be silently skipped. Guard v2 (amendment v1.2): AMP's own
        # scheduler may also add a STAGE_TICK job concurrently, so require AT LEAST one new job (v1 required exactly one and
        # raised a false alarm on such a race), and never reuse a job id this run already issued.
        seen = ts.setdefault("job_ids", set())
        if r["job_id"] in seen or db.tick_job_count(agent) < n_before + 1:
            log.write("tick_job_id_collision", tick_index=ts["k"], job_id=r["job_id"])
            raise RuntimeError(f"tick_job_id_collision at tick {ts['k']} (re-run on a used agent? use a fresh agent)")
        seen.add(r["job_id"])
        j = wait_job(db, r["job_id"])
        idle_s = wait_idle(db, agent, log, f"after tick {ts['k']}")
        approved = approve_admin_workitems(human, db, agent, log)
        if approved:
            idle_s += wait_idle(db, agent, log, f"after admin approval {ts['k']}")
        fp = fingerprint(db, agent)
        log.write("tick", stream_position=pos, tick_index=ts["k"], iteration=it, tick_minutes=tick_minutes,
                  job_id=r["job_id"], tick_job_status=j["status"], approved_admin=approved, idle_wait_s=idle_s,
                  fingerprint=json.loads(fp))
        if j["status"] == "failed":
            log.write("tick_job_failed", job=j)
        if fp == prev and not approved:
            break
        prev = fp
    else:
        log.write("settle_max_iters", stream_position=pos)
    stage_after = (db.agent_state(agent) or {}).get("stage")
    if stage_after != stage_before:
        log.write("stage_transition", stream_position=pos, before=stage_before, after=stage_after)
    return stage_after


# ---------------------------------------------------------------- main
def run(a):
    env = load_env()
    amp, human, db = AmpClient(env), HumanSession(env), AmpDB(env["AMP_ORG_ID"])
    human.login()
    agent = a.agent or agent_slug(a.category, a.stream_seed, AGENT_PATTERN)
    stream = build_stream(a.category, a.stream_seed)
    if a.limit:
        stream = stream.iloc[:a.limit]
    run_id = f"{EXPERIMENT_ID}-{agent}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    out = Path(a.out_root) / run_id
    out.mkdir(parents=True, exist_ok=True)
    log = Log(out / "amp_events.jsonl")

    # -- agent + policy (idempotent: skip if RLHF already enabled for this agent)
    try:
        st = amp.rlhf_status(agent)
        ready = bool(st.get("agent_config") and st["agent_config"].get("enabled"))
    except Exception:
        ready = False
    if not ready:
        print("registering + installing policy for", agent, flush=True)
        amp.register_agent(agent, f"Vision LOCO {a.category} seed {a.stream_seed}")
        amp.install_policy(agent, POLICY_TEMPLATE)
        time.sleep(3)   # let the backend spawn the scoped RLHF worker
    st = amp.rlhf_status(agent)
    params = st["agent_config"]["params_json"]
    legacy_injected = amp.legacy_authority_injected
    params = json.loads(params) if isinstance(params, str) else params

    manifest = {
        "run_id": run_id, "experiment_id": EXPERIMENT_ID, "experiment_config": str(CFG_PATH.relative_to(ROOT)),
        "policy_template": str(POLICY_TEMPLATE.relative_to(ROOT)), "condition": "D_amp_progressive", "agent_name": agent,
        "category": a.category, "stream_seed": a.stream_seed, "n_items": len(stream), "limit": a.limit,
        "tick_every_items": a.tick_every, "tick_minutes_rule": "1440 - k (k = tick index; unique job id, window unaffected)",
        "started": iso_now(), "org_id": env["AMP_ORG_ID"], "reviewer_session_user": env["AMP_USERNAME"],
        "amp_testing_mode": st.get("amp_testing_mode"), "worker_training_seed": worker_training_seed(env["AMP_ORG_ID"], agent),
        "amp_rlhf_params": params,
        "legacy_authority_injected": legacy_injected,
        "git": {"vision-autonomy": git_info(ROOT), "amp-backend": git_info(ROOT.parent / "amp-backend"),
                "hitl-agent": git_info(ROOT.parent / "hitl-agent"), "rlhf": git_info(ROOT.parent / "rlhf")},
        "sha256": {"policy_template": sha256_file(POLICY_TEMPLATE),
                   "calibration": sha256_file(ROOT / "config" / "calibration_v1.json"),
                   "experiment_config": sha256_file(CFG_PATH),
                   "decision_records": sha256_file(ROOT / "results" / "inputs" / "decision_records.csv")},
        "python": sys.version.split()[0],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    print(f"run {run_id}: {len(stream)} items, seed-in-worker={manifest['worker_training_seed']}", flush=True)

    sim_run_id, recs, ts, last_settled = run_id, [], {"k": 0}, 0
    preexisting_requests, n_events_before = db.request_count(agent), len(db.events(agent))
    manifest["preexisting_requests_on_agent"] = preexisting_requests
    jf = open(out / "amp_decisions.jsonl", "w", buffering=1)
    try:
        for pos, row in enumerate(stream.itertuples(index=False), start=1):
            rec = process_item(amp, human, db, agent, row, pos, sim_run_id)
            recs.append(rec)
            jf.write(json.dumps(rec, default=str) + "\n")
            viol = check_violations(rec)
            if viol:
                log.write("violation", stream_position=pos, image_id=rec["image_id"], violations=viol)
                if any(v.startswith("AUTO_REJECT") for v in viol) and not a.continue_on_violation:
                    raise RuntimeError(f"PROTOCOL VIOLATION at seq {pos}: {viol} - stopping (plan 5.3 #2)")
            if pos % a.tick_every == 0:
                stage = settle(amp, human, db, agent, ts, pos, log)
                last_settled = pos
                print(f"  seq {pos:4d} stage={stage} human={sum(r['routing']=='hitl' for r in recs)} "
                      f"auto={sum(r['routing']=='autonomous' for r in recs)}", flush=True)
        if last_settled != len(stream):
            settle(amp, human, db, agent, ts, len(stream), log)
    finally:
        jf.close()

    # -- outputs
    df = pd.DataFrame(recs)
    df.to_csv(out / "amp_decisions.csv", index=False)
    ev = db.events(agent)
    with open(out / "amp_rlhf_events.jsonl", "w") as f:
        for e in ev:
            f.write(json.dumps(e, default=str) + "\n")
    tick_rows = sum(int((e["payload"].get("stats") or {}).get("total_requests", 0))
                    for e in ev[n_events_before:] if e["event_type"] == "STAGE_TICK_SUMMARY")
    new_reqs = db.request_count(agent) - preexisting_requests
    summary = {
        "items_sent": len(recs), "new_requests_in_amp_db": new_reqs, "requests_counted_in_tick_summaries": tick_rows,
        "reconcile_ok": len(recs) == new_reqs and (tick_rows == new_reqs or not db.rlhf_enabled(agent)),
        "by_stage_routing": {f"stage{k[0]}:{k[1]}": int(v) for k, v in df.groupby(["amp_stage", "routing"]).size().items()} if len(df) else {},
        "first_stage1_pos": int(df[df.amp_stage >= 1].stream_position.min()) if (df.amp_stage >= 1).any() else None,
        "first_stage2_pos": int(df[df.amp_stage >= 2].stream_position.min()) if (df.amp_stage >= 2).any() else None,
        "rlhf_auto_disabled_at_pos": next((json.loads(l)["stream_position"] for l in open(out / "amp_events.jsonl")
                                           if '"rlhf_auto_disabled_detected"' in l), None),
        "stage2_human_with_p_le_0.10": int(((df.amp_stage == 2) & (df.routing == "hitl") &
                                            (df.amp_approval_probability <= 0.10)).sum()) if len(df) else 0,
        "auto_rejects": int(((df.routing == "autonomous") & (df.amp_auto_decision != "approve")).sum()) if len(df) else 0,
        "failed_jobs": db.failed_jobs(agent), "admin_approvals": human.approvals,
        "mean_seconds_per_item": round(float(df.seconds.mean()), 3) if len(df) else None,
        "finished": iso_now(),
    }
    manifest["summary"] = summary
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    print(json.dumps({k: v for k, v in summary.items() if k != "admin_approvals"}, indent=1, default=str))
    print("outputs:", out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", required=True)
    ap.add_argument("--stream-seed", type=int, required=True)
    ap.add_argument("--agent", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--tick-every", type=int, default=CFG["amp"]["tick_every_items_per_agent"])
    ap.add_argument("--out-root", default=str(ROOT / CFG.get("results_root", "results") / "runs"))
    ap.add_argument("--config", default=None, help="experiment config (default config/experiment_v1.json)")
    ap.add_argument("--continue-on-violation", action="store_true")
    run(ap.parse_args())


if __name__ == "__main__":
    main()
