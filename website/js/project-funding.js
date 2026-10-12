/*
 * SOST Project Funding — fund a project that does NOT exist yet (Option 3,
 * FUTURE / REGULATORY-READY). ---------------------------------------------
 * You don't tokenize "a solar plant that doesn't exist"; you tokenize a
 * contractual RIGHT tied to the project to be built. Flow:
 *   Project Passport -> choose what funders receive -> all-or-nothing funding
 *   window -> if minimum reached: ACTIVE -> milestone-gated releases -> DELIVERED;
 *   else: FAILED -> refund.
 * Funds are released per verified MILESTONE, never all up front. This engine is
 * accounting/state only (no custody of real money here).
 *
 * LEGAL: offering debt / yield / revenue-share / equity / transferable units may
 * be a financial instrument or regulated crowdfunding even when called a "token".
 * MiCA excludes crypto-assets that are financial instruments; the EU crowdfunding
 * regime (ECSPR) covers loan/securities offers up to EUR 5M per project / 12 months
 * via an authorised provider (Spain: CNMV-authorised PSFP). Design target: SOST
 * supplies Project Passport + tokenization + DLT trail; an authorised provider
 * supplies the regulated layer. LAUNCH stays disabled until that framework exists.
 */
(function (root, factory) {
  var m = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = m;
  if (root) root.SOSTProjectFunding = m;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var MODELS = ['PRE_PURCHASE', 'DEBT', 'REVENUE_SHARE', 'EQUITY_SPV', 'CUSTOM'];
  var STATES = ['DRAFT', 'FUNDING', 'FUNDED', 'FAILED_REFUND', 'ACTIVE', 'DELIVERED', 'HALTED'];
  function assert(c, m) { if (!c) throw new Error(m); }

  // amounts are integer minor units of the reference currency (e.g. cents of EUR) as strings.
  function newProject(o) {
    assert(o.project_passport_hash, 'project_passport_hash required');
    assert(MODELS.indexOf(o.model) >= 0, 'invalid funding model');
    var target = BigInt(o.target || '0'), minimum = BigInt(o.minimum || o.target || '0');
    assert(target > 0n, 'target required'); assert(minimum > 0n && minimum <= target, 'minimum in (0, target]');
    var ms = (o.milestones || []).map(function (m, i) { return { i: i, pct: m.pct | 0, desc: m.desc || ('milestone ' + (i + 1)), released: false, verified: false }; });
    var sum = ms.reduce(function (a, m) { return a + (m.pct | 0); }, 0);
    assert(ms.length === 0 || sum === 100, 'milestone percentages must sum to 100');
    return {
      id: o.id || null, project_passport_hash: o.project_passport_hash,
      model: o.model, right_desc: o.right_desc || null,
      currency: o.currency || 'EUR', settlement_rail: o.settlement_rail || 'SOST', // or STABLE_REFERENCE
      target: target.toString(), minimum: minimum.toString(),
      token_symbol: o.token_symbol || 'PROJ-X', token_supply: String(o.token_supply || '0'),
      deadline: o.deadline | 0, committed: '0', released: '0',
      milestones: ms, state: 'DRAFT', funders: 0
    };
  }

  function commit(p, amount) {
    assert(['DRAFT', 'FUNDING'].indexOf(p.state) >= 0, 'not in funding window');
    p.state = 'FUNDING';
    p.committed = (BigInt(p.committed) + BigInt(amount)).toString();
    p.funders += 1;
    return p.committed;
  }
  function pct(p) { return Number((BigInt(p.committed) * 10000n) / BigInt(p.target)) / 100; }

  // all-or-nothing at the deadline: >= minimum -> FUNDED(->ACTIVE); else FAILED_REFUND.
  function closeWindow(p, nowSecs) {
    assert(p.state === 'FUNDING' || p.state === 'DRAFT', 'window not open');
    assert(nowSecs >= p.deadline || BigInt(p.committed) >= BigInt(p.target), 'window still open');
    if (BigInt(p.committed) >= BigInt(p.minimum)) { p.state = 'FUNDED'; }
    else { p.state = 'FAILED_REFUND'; }
    return p.state;
  }
  function activate(p) { assert(p.state === 'FUNDED', 'not funded'); p.state = 'ACTIVE'; return p.state; }

  function verifyMilestone(p, i) { assert(p.state === 'ACTIVE', 'project not active'); var m = p.milestones[i]; assert(m, 'no such milestone'); m.verified = true; return m; }

  // release the milestone's tranche ONLY when the milestone is verified and prior ones released (ordered).
  function release(p, i) {
    assert(p.state === 'ACTIVE', 'project not active');
    var m = p.milestones[i]; assert(m, 'no such milestone');
    assert(m.verified, 'milestone not verified'); assert(!m.released, 'already released');
    if (i > 0) assert(p.milestones[i - 1].released, 'previous milestone not released (ordered)');
    // tranche is a fraction of ACTUAL funds raised (committed), never of target:
    // an over-minimum-but-under-target project must not release more than was funded
    // (keeps the invariant funded = released + escrowed; see accounting()).
    var tranche = (BigInt(p.committed) * BigInt(m.pct)) / 100n;
    m.released = true;
    p.released = (BigInt(p.released) + tranche).toString();
    if (p.milestones.every(function (x) { return x.released; })) p.state = 'DELIVERED';
    return { tranche: tranche.toString(), released_total: p.released, state: p.state };
  }

  // honest accounting: funded vs released vs still-escrowed.
  function accounting(p) {
    var funded = BigInt(p.committed), released = BigInt(p.released);
    var escrowed = funded > released ? funded - released : 0n;
    return {
      funded: funded.toString(), released: released.toString(), escrowed: escrowed.toString(),
      pct_funded: pct(p), milestone: p.milestones.filter(function (m) { return m.released; }).length + '/' + p.milestones.length,
      note: p.settlement_rail === 'SOST'
        ? 'SOST-denominated: funders accept SOST price risk while escrowed (no fake stability).'
        : 'Stable-reference rail; SOST used for registry/fees/proof.'
    };
  }

  return {
    MODELS: MODELS, STATES: STATES, newProject: newProject, commit: commit, pct: pct,
    closeWindow: closeWindow, activate: activate, verifyMilestone: verifyMilestone,
    release: release, accounting: accounting
  };
});
