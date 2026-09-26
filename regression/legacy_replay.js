#!/usr/bin/env node
/*
 * Experiment 1/2 LEGACY REPLAY REGRESSION.
 * Re-evaluates recorded Experiment 1 and 2 study runs with the CURRENT GOV (rlhf dist) legacy code and
 * requires exact agreement:
 *   A. routing: every recorded decision re-routed from its recorded (stage, P, threshold, hard_blocked, probe flag)
 *   B. gates:   every recorded Stage 1 tick: cumulative agreement accumulated tick-by-tick (per the run's basis)
 *               and the four gate booleans recomputed and compared with GOV's recorded decision_debug
 *   C. SQL:     every recorded tick window re-queried with aggregateWindowStats; all recorded stats fields must match
 * Usage: node regression/legacy_replay.js [--no-sql]      (exit 0 = pass)
 */
const fs = require('fs');
const path = require('path');
const RLHF = '/workspace/rlhf/dist/src';
const { legacyStage2Candidate, evaluateLegacyStage1Gates } = require(`${RLHF}/services/rlhf/legacy_governance`);
const ROOT = path.resolve(__dirname, '..');
const RUN_ROOTS = [path.join(ROOT, 'results/runs'), path.join(ROOT, 'results/exp2/runs')];
const noSql = process.argv.includes('--no-sql');

function readJsonl(p) { return fs.readFileSync(p, 'utf8').split('\n').filter(Boolean).map(JSON.parse); }
function completeRuns() {
  const out = [];
  for (const root of RUN_ROOTS) {
    for (const d of fs.readdirSync(root)) {
      const mp = path.join(root, d, 'manifest.json');
      if (!fs.existsSync(mp)) continue;
      const m = JSON.parse(fs.readFileSync(mp, 'utf8'));
      if (!m.summary) continue;                           // aborted attempts are not replayed
      out.push({ dir: path.join(root, d), m });
    }
  }
  return out;
}

const report = { runs: 0, A: { decisions: 0, mismatches: [] }, B: { ticks: 0, mismatches: [] }, C: { windows: 0, mismatches: [] } };
const policyTemplates = {};
function policyFor(m) {
  const p = m.policy_template || 'config/amp_policy_v1.json';
  if (!policyTemplates[p]) policyTemplates[p] = JSON.parse(fs.readFileSync(path.join(ROOT, p), 'utf8'));
  return policyTemplates[p];
}

async function main() {
  const runs = completeRuns();
  report.runs = runs.length;
  let pool = null, repo = null;
  if (!noSql) {
    const env = Object.fromEntries(fs.readFileSync('/workspace/gov-backend/.env', 'utf8').split('\n')
      .filter((l) => l.includes('=') && !l.trim().startsWith('#')).map((l) => [l.slice(0, l.indexOf('=')).trim(), l.slice(l.indexOf('=') + 1).trim()]));
    const { createMySQLPool } = require(`${RLHF}/db/mysql_client`);
    const { ApprovalRepo } = require(`${RLHF}/db/repos/ApprovalRepo`);
    pool = createMySQLPool({ host: '127.0.0.1', port: Number(env.MYSQL_PORT || 3306), database: env.MYSQL_DATABASE || 'amp', user: env.MYSQL_USER, password: env.MYSQL_PASSWORD });
    repo = new ApprovalRepo(pool);
  }
  for (const { dir, m } of runs) {
    const pol = policyFor(m);
    const auto = pol.action_governance.automation;
    const rejectThreshold = Number(auto.auto_reject_threshold ?? auto.auto_execute_threshold);
    // ---- A. routing
    const rows = readJsonl(path.join(dir, 'amp_decisions.jsonl'));
    for (const r of rows) {
      report.A.decisions += 1;
      const p = r.amp_approval_probability;
      const c = legacyStage2Candidate({
        stage: Number(r.amp_stage), hardBlocked: !!r.hard_blocked, labelMode: r.amp_label_mode || 'binary', classProbs: null,
        modelScore: (p === null || p === undefined || Number.isNaN(p)) ? null : Number(p),
        approveThreshold: Number(r.amp_threshold_used ?? auto.auto_execute_threshold), rejectThreshold
      });
      let routing = 'hitl', autoDecision = null;
      if (c.kind === 'approve_candidate') { routing = r.probe_forced_human ? 'hitl' : 'autonomous'; autoDecision = routing === 'autonomous' ? 'approve' : null; }
      else if (c.kind === 'auto_reject') { routing = 'autonomous'; autoDecision = 'reject'; }
      if (routing !== r.routing || (routing === 'autonomous' && autoDecision !== r.amp_auto_decision)) {
        report.A.mismatches.push({ run: m.agent_name, pos: r.stream_position, recorded: [r.routing, r.amp_auto_decision], replay: [routing, autoDecision] });
      }
    }
    // ---- B. gates (tick-by-tick) and C. SQL
    const ev = readJsonl(path.join(dir, 'amp_rlhf_events.jsonl')).filter((e) => e.event_type === 'STAGE_TICK_SUMMARY');
    const params = m.amp_rlhf_params || {};
    const basis = params.stage1_agreement_basis === 'recommendation' ? 'recommendation' : 'execution_threshold';
    let cumCount = 0, cumAgree = 0;
    for (const e of ev) {
      const pl = e.payload, st = pl.stats || {}, dbg = pl.decision_debug || {};
      if (!noSql && pl.window_start && pl.window_end) {
        report.C.windows += 1;
        const fresh = await repo.aggregateWindowStats(m.org_id, m.agent_name, pl.window_start, pl.window_end);
        for (const [k, v] of Object.entries(st)) {
          if (Number(fresh[k]) !== Number(v)) report.C.mismatches.push({ run: m.agent_name, window: pl.window_end, field: k, recorded: v, replay: fresh[k] });
        }
      }
      if (pl.stage !== 1) continue;
      const c = basis === 'recommendation' ? [st.stage1_recommendation_count, st.stage1_recommendation_agree_count] : [st.stage1_recommend_count, st.stage1_recommend_agree_count];
      cumCount += Number(c[0] || 0); cumAgree += Number(c[1] || 0);
      if (dbg.stage1_primary_met === undefined) continue;            // tick without gate evaluation
      report.B.ticks += 1;
      const g = evaluateLegacyStage1Gates({
        stage1EvalRows: Number(pl.stage1_eval_rows || 0), stage1EvalMinRows: Number(params.stage1_eval_min_human_rows || 200),
        agreementRate: cumCount > 0 ? cumAgree / cumCount : null, agreementMin: Number(params.stage1_eval_min_agreement_rate || 0.7),
        recentRows: Number(dbg.stage1_recent_rows || 0), recentRate: dbg.stage1_recent_rate ?? null,
        recentWindowRows: Number(params.stage1_recent_window_rows || 50), recentMinRate: Number(params.stage1_recent_min_agreement_rate || 0.65),
        repeatedFailures7d: Number(dbg.repeated_failures_7d || 0), maxSafetyAlerts7d: Number(params.stage2_promotion_blocking_safety_alerts_7d_max || 0),
        testingMode: !!dbg.stage1_safety_ignored_in_testing_mode
      });
      const rec = { primaryMet: dbg.stage1_primary_met, sampleSizeMet: dbg.stage1_sample_size_met, stabilityMet: dbg.stage1_stability_met, safetyMet: dbg.stage1_safety_met, allMet: dbg.stage1_hard_gates_all_met };
      for (const k of Object.keys(rec)) {
        if (Boolean(rec[k]) !== Boolean(g[k])) report.B.mismatches.push({ run: m.agent_name, window: pl.window_end, gate: k, recorded: rec[k], replay: g[k], cum: [cumAgree, cumCount] });
      }
    }
  }
  if (pool) await pool.end();
  const pass = !report.A.mismatches.length && !report.B.mismatches.length && !report.C.mismatches.length;
  const out = { pass, runs: report.runs, A: { decisions: report.A.decisions, mismatches: report.A.mismatches.length },
    B: { ticks: report.B.ticks, mismatches: report.B.mismatches.length }, C: noSql ? 'skipped' : { windows: report.C.windows, mismatches: report.C.mismatches.length },
    examples: { A: report.A.mismatches.slice(0, 5), B: report.B.mismatches.slice(0, 5), C: noSql ? [] : report.C.mismatches.slice(0, 5) } };
  console.log(JSON.stringify(out, null, 1));
  process.exit(pass ? 0 : 1);
}
main().catch((e) => { console.error(e); process.exit(2); });
