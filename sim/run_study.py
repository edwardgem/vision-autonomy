"""Run the preregistered AMP study: stream seeds x categories, one fresh agent per run, sequentially.

Protocol (EXPERIMENT_PLAN.md sections 2, 5 + amendment v1.1): no parameter is chosen or changed here. A failed run STOPS the
study (no silent retries: a retry needs a fresh agent and a decision). The only adaptive rule is the preregistered,
time-only seed fallback: if seed 0 takes > 3 h wall time, run seeds 0, 1, 2 only.
"""
import json, subprocess, sys, time
from pathlib import Path
from sim.amp_client import agent_slug, iso_now, ROOT

CFG = json.loads((ROOT / "config" / "experiment_v1.json").read_text())
CATS = CFG["dataset"]["categories"]
SEEDS = list(CFG["streams"]["stream_seeds"])
FALLBACK_SEEDS = list(CFG["streams"]["fallback_stream_seeds"])
FALLBACK_HOURS = float(CFG["streams"]["fallback_if_seed_wall_time_gt_hours"])
OUT = ROOT / "results" / "runs"
LOG = OUT / "study_log.jsonl"


def log(ev, **kw):
    with open(LOG, "a", buffering=1) as f:
        f.write(json.dumps({"ts": iso_now(), "event": ev, **kw}) + "\n")


def completed(agent):
    for m in OUT.glob(f"*-{agent}-*/manifest.json"):
        try:
            if "summary" in json.loads(m.read_text()):
                return m.parent
        except Exception:
            pass
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "console").mkdir(exist_ok=True)
    seeds, t_study = list(SEEDS), time.time()
    log("study_start", seeds=seeds, categories=CATS)
    i = 0
    while i < len(seeds):
        seed, t_seed = seeds[i], time.time()
        for cat in CATS:
            agent = agent_slug(cat, seed)
            done = completed(agent)
            if done:
                log("run_skipped_already_complete", agent=agent, dir=str(done))
                continue
            t0 = time.time()
            log("run_start", agent=agent, seed=seed, category=cat)
            with open(OUT / "console" / f"{agent}.log", "w") as cf:
                rc = subprocess.run([sys.executable, "-m", "sim.run_amp", "--category", cat, "--stream-seed", str(seed),
                                     "--agent", agent, "--out-root", str(OUT)], stdout=cf, stderr=subprocess.STDOUT,
                                    cwd=str(ROOT)).returncode
            log("run_end", agent=agent, returncode=rc, minutes=round((time.time() - t0) / 60, 2))
            if rc != 0 or not completed(agent):
                log("study_stopped_on_failure", agent=agent, returncode=rc)
                print(f"STUDY STOPPED: run {agent} failed (rc={rc}); see {OUT}/console/{agent}.log", flush=True)
                sys.exit(2)
        hours = (time.time() - t_seed) / 3600
        log("seed_done", seed=seed, hours=round(hours, 3))
        if i == 0 and hours > FALLBACK_HOURS and seeds != FALLBACK_SEEDS:
            seeds = [s for s in FALLBACK_SEEDS]
            log("seed_fallback_applied", reason=f"seed 0 took {hours:.2f} h > {FALLBACK_HOURS} h (preregistered, time-only)",
                seeds=seeds)
        i += 1
    log("study_done", total_hours=round((time.time() - t_study) / 3600, 3))
    print("STUDY DONE", flush=True)


if __name__ == "__main__":
    main()
