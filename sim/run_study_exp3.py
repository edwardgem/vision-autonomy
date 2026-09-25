"""Run the preregistered Experiment 3 study (EXPERIMENT_PLAN_3.md section 9), or the two pilots (section 10).

Study: for each study seed, the shift run then the stationary run (same seed = identical pre-shift segment), one fresh
agent per run, sequentially; the run's RLHF worker is stopped after each run. Then the preregistered top-up: per arm,
while fewer than min_eligible_per_arm runs are eligible (first model accepted and good class authorized before item
381 - pre-shift events only), run that arm's next top-up seed, up to 16 seeds per arm. A failed run STOPS the study.
No parameter is chosen or changed here.

Usage: python -m sim.run_study_exp3 [--pilot]
"""
import argparse, json, subprocess, sys, time
from pathlib import Path
from sim.amp_client import iso_now, ROOT
from analysis.exp3_analysis import analyse_run

CFG_REL = "config/exp3/experiment_exp3_v1.json"
CFG = json.loads((ROOT / CFG_REL).read_text())
S = CFG["streams"]
PATTERN = CFG["amp"]["agent_name_pattern"]
MON = json.loads((ROOT / CFG["amp"]["policy_template"]).read_text())["autonomy_ops"]["authority"]["monitoring"]


def completed(out, agent):
    for m in sorted(out.glob(f"*-{agent}-2*/manifest.json")):
        try:
            if "summary" in json.loads(m.read_text()):
                return m.parent
        except Exception:
            pass
    return None


def attempted(out, agent):
    return bool(list(out.glob(f"*-{agent}-2*/manifest.json")))


def run_cell(out, log, arm, seed):
    base = PATTERN.format(arm=arm, stream_seed=seed)
    n, agent = 1, base
    while True:                                   # fresh agent after an incomplete earlier attempt (as amendment v1.2)
        agent = base if n == 1 else f"{base}-r{n}"
        done = completed(out, agent)
        if done:
            log("run_skipped_already_complete", agent=agent, dir=str(done)); return done
        if not attempted(out, agent):
            break
        n += 1
    t0 = time.time(); log("run_start", agent=agent, arm=arm, seed=seed)
    with open(out / "console" / f"{agent}.log", "w") as cf:
        rc = subprocess.run([sys.executable, "-m", "sim.run_amp", "--config", CFG_REL, "--arm", arm, "--stream-seed", str(seed),
                             "--agent", agent, "--out-root", str(out)], stdout=cf, stderr=subprocess.STDOUT, cwd=str(ROOT)).returncode
    log("run_end", agent=agent, returncode=rc, minutes=round((time.time() - t0) / 60, 2))
    src = subprocess.run([sys.executable, "-m", "sim.ops_stop_workers", "--agents", agent, "--ops-dir", str(out.parent / "ops")],
                         capture_output=True, text=True, cwd=str(ROOT))
    log("worker_stopped_after_run", agent=agent, returncode=src.returncode, output=src.stdout[-400:])
    if src.returncode != 0 or "config.enabled -> 0" not in src.stdout:
        log("study_stopped_worker_not_stopped", agent=agent); print(f"STOPPED: worker of {agent} not stopped", flush=True); sys.exit(3)
    done = completed(out, agent)
    if rc != 0 or not done:
        log("study_stopped_on_failure", agent=agent, returncode=rc); print(f"STOPPED: run {agent} failed (rc={rc})", flush=True); sys.exit(2)
    return done


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--pilot", action="store_true"); a = ap.parse_args()
    out = ROOT / CFG["results_root"] / ("pilot" if a.pilot else "runs")
    (out / "console").mkdir(parents=True, exist_ok=True)
    def log(ev, **kw):
        with open(out / "study_log.jsonl", "a") as f:
            f.write(json.dumps({"ts": iso_now(), "event": ev, **kw}) + "\n")
    if a.pilot:
        log("pilot_start", seeds=S["pilot_seeds"])
        for arm in S["arms"]:
            run_cell(out, log, arm, S["pilot_seeds"][arm])
        log("pilot_done"); print("PILOT DONE", flush=True); return
    log("study_start", seeds=S["study_seeds"], arms=S["arms"])
    dirs = {arm: [] for arm in S["arms"]}
    for seed in S["study_seeds"]:
        for arm in S["arms"]:
            dirs[arm].append(run_cell(out, log, arm, seed))
    for arm in S["arms"]:                          # preregistered top-up (eligibility is pre-shift only)
        topup = list(S["topup_seeds"])
        while sum(analyse_run(d, MON)["eligible"] for d in dirs[arm]) < S["min_eligible_per_arm"] and topup:
            seed = topup.pop(0); log("topup_run", arm=arm, seed=seed)
            dirs[arm].append(run_cell(out, log, arm, seed))
        log("arm_done", arm=arm, runs=len(dirs[arm]), eligible=sum(analyse_run(d, MON)["eligible"] for d in dirs[arm]))
    log("study_done"); print("STUDY DONE", flush=True)


if __name__ == "__main__":
    main()
