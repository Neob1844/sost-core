/*
 * SOST DEX — SWAP / TIMELOCK POLICY (single source of truth).
 * ===========================================================================
 * ONE place that defines the owner-APPROVED HTLC timelock policy for every
 * cross-chain pair, the staggered-timeout ENGINE that derives those values from
 * block time + confirmations + reorg margin + congestion + claim/refund safety,
 * the pre-sign VALIDATION (long leg MUST outlive the short leg by a safety gap),
 * the CANONICAL human-readable signing summary, and the HTLC CONTRACT PINNING
 * table. The dashboard + the devnet flow read these — no duplicated constants.
 *
 * SOST IS ALWAYS THE LONG LEG (SOST/ETH, SOST/USDC, SOST/BTC). The initiator
 * locks SOST for ~48h; the counterparty's short leg (EVM/BTC) refunds ~24h
 * EARLIER, so the counterparty can never both refund their leg AND still claim
 * SOST — the 24h safety gap is the atomic-swap safety invariant.
 *
 * NOTE ON ENVIRONMENTS: the canonical DURATIONS below are the MAINNET policy
 * (used to CONSTRUCT real swaps). A devnet runs the same staggered design with
 * SCALED block heights for fast testing (see DEVNET.*). This module expresses
 * both, clearly labelled. It does NOT deploy anything and does NOT claim mainnet
 * deployment — it is pure, dependency-free policy logic (web/lab only).
 *
 * Quote expiry (90s, SOSTDexQuotePolicy) is a SEPARATE clock from the HTLC
 * timelock and is intentionally NOT reused here.
 */
(function (root, factory) {
  var m = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = m;
  if (root) root.SOSTDexSwapPolicy = m;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var HOUR = 3600, DAY = 86400;

  // SOST consensus block time (TARGET_SPACING). EVM ~12s, BTC ~600s.
  var BLOCK_TIME_SECS = { SOST: 600, EVM: 12, ETH: 12, BTC: 600 };

  // ---- OWNER-APPROVED MAINNET POLICY (canonical durations) -------------------
  //   SOST long leg : 288 SOST blocks  = 288 * 600s = 172800s = 48h
  //   EVM short leg : 24h = 86400s      = 86400/12  = 7200 EVM blocks (block.number)
  //   BTC short leg : 144 BTC blocks     = 144 * 600s = 86400s = 24h (CLTV height)
  //   safety gap    : long - short       = 48h - 24h = 24h = 86400s (MINIMUM)
  var POLICY = {
    SOST_LONG_BLOCKS: 288,
    SOST_LONG_SECS: 288 * 600,          // 172800 = 48h
    EVM_SHORT_SECS: 24 * HOUR,          // 86400  = 24h
    EVM_SHORT_BLOCKS: (24 * HOUR) / 12, // 7200   blocks @ 12s (block.number)
    BTC_SHORT_BLOCKS: 144,
    BTC_SHORT_SECS: 144 * 600,          // 86400  = 24h
    MIN_SAFETY_GAP_SECS: 24 * HOUR      // 86400  = 24h minimum between the two legs
  };

  // Quote-lock lifetime is a DIFFERENT clock (pointer to the quote policy's 90s),
  // declared here only to document that it is independent of the HTLC timeout.
  var QUOTE_EXPIRY_SECS = 90;

  // ---- DEVNET SCALING (fast testing; same STAGGER, scaled heights) -----------
  // Matches the proven chain E2E (scripts/e2e_sost_eth_devnet.sh): SOST refund far
  // away (long), EVM/BTC refund nearer (short). Blocks are mined fast on devnet,
  // so these are HEIGHT offsets, not wall-clock. The DURATION validation always
  // uses the mainnet canonical seconds above (the policy being tested is mainnet).
  var DEVNET = {
    SOST_LONG_BLOCKS: 500,   // long leg height offset (e2e uses +500)
    EVM_SHORT_BLOCKS: 200,   // short leg height offset (e2e uses +200)
    BTC_SHORT_BLOCKS: 100
  };

  // ---- HTLC TIMEOUT ENGINE (section 6) ---------------------------------------
  // Per-chain component budget (in THAT chain's blocks) that a SHORT leg must
  // cover to be safe. The approved policy block-count must be >= this minimum:
  //
  //   short_min_blocks = confirmations + reorg_margin + congestion + claim_refund_safety
  //   long_leg(SOST)   = short_leg + SAFETY_GAP   (>= 24h)   => 48h = 288 blocks
  //
  // SOST is always the long leg. The components below are the real technical
  // facts (not a fabricated market value) that justify the owner-approved sizes.
  var COMPONENTS = {
    EVM: { confirmations: 12, reorg_margin: 24, congestion: 900, claim_refund_safety: 900 }, // blocks @12s
    BTC: { confirmations: 6,  reorg_margin: 2,  congestion: 6,   claim_refund_safety: 6 },    // blocks @600s
    SOST:{ confirmations: 6,  reorg_margin: 3,  congestion: 6,   claim_refund_safety: 6 }     // blocks @600s
  };
  function sumComponents(c) { return (c.confirmations | 0) + (c.reorg_margin | 0) + (c.congestion | 0) + (c.claim_refund_safety | 0); }

  function assert(cond, msg) { if (!cond) throw new Error(msg); }

  // short chain for a pair: SOST/ETH & SOST/USDC -> EVM; SOST/BTC -> BTC.
  function shortChainFor(pair) {
    var p = String(pair || '').toUpperCase();
    if (/\/BTC$/.test(p) || /^BTC\//.test(p)) return 'BTC';
    return 'EVM'; // ETH / USDC / ERC20
  }

  // Compute the staggered timelocks for a pair. `opts` = {env, sostTip, evmHead,
  // btcTip, pairBlocks?}. Returns both legs with height offsets, refund heights,
  // canonical timeout seconds, and the component breakdown. SOST = long leg.
  function computeTimelocks(pair, opts) {
    opts = opts || {};
    var env = (opts.env === 'devnet') ? 'devnet' : 'mainnet';
    var shortChain = shortChainFor(pair);
    var scaled = (env === 'devnet');

    var shortBlocks, shortSecs, shortHead, shortChainKey;
    if (shortChain === 'BTC') {
      shortBlocks = scaled ? DEVNET.BTC_SHORT_BLOCKS : POLICY.BTC_SHORT_BLOCKS;
      shortSecs = POLICY.BTC_SHORT_SECS;
      shortHead = (opts.btcTip != null) ? Number(opts.btcTip) : null;
      shortChainKey = 'BTC';
    } else {
      shortBlocks = scaled ? DEVNET.EVM_SHORT_BLOCKS : POLICY.EVM_SHORT_BLOCKS;
      shortSecs = POLICY.EVM_SHORT_SECS;
      shortHead = (opts.evmHead != null) ? Number(opts.evmHead) : null;
      shortChainKey = 'EVM';
    }
    var longBlocks = scaled ? DEVNET.SOST_LONG_BLOCKS : POLICY.SOST_LONG_BLOCKS;
    var longSecs = POLICY.SOST_LONG_SECS;
    var sostTip = (opts.sostTip != null) ? Number(opts.sostTip) : null;

    // Engine sanity: the policy short window must cover the component minimum.
    var shortMin = sumComponents(COMPONENTS[shortChainKey]);
    var policyShortBlocks = (shortChain === 'BTC') ? POLICY.BTC_SHORT_BLOCKS : POLICY.EVM_SHORT_BLOCKS;
    assert(policyShortBlocks >= shortMin,
      'policy short window (' + policyShortBlocks + ' blocks) below component minimum (' + shortMin + ')');

    return {
      pair: String(pair), env: env, devnetScaled: scaled,
      short: {
        chain: shortChainKey, blockTimeSecs: BLOCK_TIME_SECS[shortChainKey],
        refundBlocks: shortBlocks, refundHeight: (shortHead != null) ? (shortHead + shortBlocks) : null,
        timeoutSecs: shortSecs, components: COMPONENTS[shortChainKey], componentMinBlocks: shortMin
      },
      long: {
        chain: 'SOST', blockTimeSecs: BLOCK_TIME_SECS.SOST,
        refundBlocks: longBlocks, refundHeight: (sostTip != null) ? (sostTip + longBlocks) : null,
        timeoutSecs: longSecs, components: COMPONENTS.SOST
      },
      safetyGapSecs: longSecs - shortSecs,
      minSafetyGapSecs: POLICY.MIN_SAFETY_GAP_SECS
    };
  }

  // ---- PRE-SIGN VALIDATION (section 6) ---------------------------------------
  // MUST be called BEFORE signing/funding. Asserts long_timeout > short_timeout
  // AND safety_gap >= configured minimum; else throws a clear error (REJECT).
  // Accepts a computeTimelocks() result OR a bare {short:{timeoutSecs}, long:{timeoutSecs}}.
  function validateTimelocks(tl, minGapSecs) {
    assert(tl && tl.short && tl.long, 'timelocks: both short and long legs required');
    var s = Number(tl.short.timeoutSecs), l = Number(tl.long.timeoutSecs);
    var minGap = (minGapSecs != null) ? Number(minGapSecs)
               : (tl.minSafetyGapSecs != null ? Number(tl.minSafetyGapSecs) : POLICY.MIN_SAFETY_GAP_SECS);
    assert(isFinite(s) && s > 0, 'short-leg timeout must be a positive duration');
    assert(isFinite(l) && l > 0, 'long-leg timeout must be a positive duration');
    if (!(l > s)) {
      throw new Error('REVERSED TIMELOCK — the long leg (SOST, ' + l + 's) must expire AFTER the short leg (' + s + 's). Refusing to construct the swap.');
    }
    var gap = l - s;
    if (gap < minGap) {
      throw new Error('INSUFFICIENT SAFETY GAP — gap is ' + gap + 's (' + fmtDur(gap) + '), below the required ' + minGap + 's (' + fmtDur(minGap) + '). Refusing to construct the swap.');
    }
    return { ok: true, gapSecs: gap, shortSecs: s, longSecs: l };
  }

  // ---- display helpers (shown BEFORE funding) --------------------------------
  function fmtDur(secs) {
    secs = Math.max(0, Math.round(Number(secs) || 0));
    var h = secs / HOUR;
    return (Number.isInteger(h) ? h : h.toFixed(2)) + 'h';
  }
  function hours(secs) { return (Number(secs) / HOUR); }
  function shortLegRefundDisplay(tl) {
    var h = tl.short.refundHeight != null ? ('block ' + tl.short.refundHeight) : ('+' + tl.short.refundBlocks + ' ' + tl.short.chain + ' blocks');
    return 'SHORT LEG REFUND  ' + h + '  (~' + hours(tl.short.timeoutSecs) + 'h · ' +
      (tl.short.chain === 'BTC' ? (tl.short.refundBlocks + ' BTC blocks CLTV') : (tl.short.refundBlocks + ' EVM blocks @12s, block.number')) + ')';
  }
  function sostRefundDisplay(tl) {
    var h = tl.long.refundHeight != null ? ('height ' + tl.long.refundHeight) : ('+' + tl.long.refundBlocks + ' SOST blocks');
    return 'SOST REFUND  ' + h + '  (~' + hours(tl.long.timeoutSecs) + 'h · ' + tl.long.refundBlocks + ' SOST blocks)';
  }
  function safetyGapDisplay(tl) {
    return 'SAFETY GAP  ~' + hours(tl.safetyGapSecs) + 'h (min ' + hours(tl.minSafetyGapSecs) + 'h)';
  }

  // ---- RESUME: persist/reconcile the EXACT deadlines -------------------------
  // Store the constructed refund heights so a reload RESUMES on the exact same
  // deadlines (never re-derives new ones). reconcile recomputes blocks-remaining
  // against the current chain tips (chain truth), without changing the deadline.
  function deadlineRecord(tl) {
    return {
      pair: tl.pair, env: tl.env, devnetScaled: tl.devnetScaled,
      shortChain: tl.short.chain, shortRefundHeight: tl.short.refundHeight, shortTimeoutSecs: tl.short.timeoutSecs,
      longChain: tl.long.chain, longRefundHeight: tl.long.refundHeight, longTimeoutSecs: tl.long.timeoutSecs,
      safetyGapSecs: tl.safetyGapSecs
    };
  }
  function reconcileDeadlines(rec, tips) {
    tips = tips || {};
    var out = { shortRefundHeight: rec.shortRefundHeight, longRefundHeight: rec.longRefundHeight };
    var shortTip = (rec.shortChain === 'BTC') ? tips.btcTip : tips.evmHead;
    if (shortTip != null && rec.shortRefundHeight != null) {
      out.shortBlocksRemaining = rec.shortRefundHeight - Number(shortTip);
      out.shortRefundOpen = out.shortBlocksRemaining <= 0;
    }
    if (tips.sostTip != null && rec.longRefundHeight != null) {
      out.longBlocksRemaining = rec.longRefundHeight - Number(tips.sostTip);
      out.longRefundOpen = out.longBlocksRemaining <= 0;
    }
    return out;
  }

  // ---- CONTRACT PINNING (section 8) ------------------------------------------
  // The EXPECTED HTLC contract by environment + chainId + version. mainnet is
  // intentionally null (NOT DEPLOYED — must be set explicitly, never silently).
  // The devnet address is resolved from the pinned local config (dex-devnet-config.json).
  var PINNED_HTLC = {
    devnet:  { 31337: { v2: null } },  // filled by registerPin() from DEVNET.htlc_v2
    testnet: { },
    mainnet: { 1: { v2: null } }       // NOT DEPLOYED — null on purpose
  };
  function norm(a) { return String(a == null ? '' : a).trim().toLowerCase(); }
  function registerPin(env, chainId, version, address) {
    PINNED_HTLC[env] = PINNED_HTLC[env] || {};
    PINNED_HTLC[env][chainId] = PINNED_HTLC[env][chainId] || {};
    PINNED_HTLC[env][chainId][version || 'v2'] = address;
    return address;
  }
  // Resolve expected HTLC from (a) an explicit pin, else (b) the local config for devnet.
  function resolveExpectedHtlc(env, chainId, version, cfg) {
    version = version || 'v2';
    var byEnv = PINNED_HTLC[env] || {};
    var byChain = byEnv[chainId] || {};
    if (byChain[version]) return byChain[version];
    if (env === 'devnet' && cfg && cfg.htlc_v2) return cfg.htlc_v2; // pinned local config
    return null;
  }
  // CRITICAL guard: refuse to sign if the in-use address != the pinned expected one,
  // or if no expected address is pinned at all (never accept a silent remote address).
  function assertPinnedContract(inUseAddress, ctx) {
    ctx = ctx || {};
    var expected = (ctx.expected != null) ? ctx.expected
                 : resolveExpectedHtlc(ctx.env, ctx.chainId, ctx.version, ctx.cfg);
    if (!expected) {
      throw new Error('CRITICAL — no PINNED HTLC contract for ' + (ctx.env || '?') + '/chainId ' + (ctx.chainId || '?') + '. Refusing to sign against an unpinned contract.');
    }
    if (norm(inUseAddress) !== norm(expected)) {
      throw new Error('CRITICAL — HTLC contract MISMATCH. In use ' + inUseAddress + ' but pinned EXPECTED ' + expected + '. Refusing to sign (possible malicious/remote contract).');
    }
    return { ok: true, expected: expected };
  }

  // ---- CANONICAL HUMAN-READABLE SIGNING SUMMARY (section 3) ------------------
  // The exact, non-opaque summary shown in BOTH the dashboard AND the SOST wallet
  // before ANY signature. Built here so both read the identical object.
  function buildSigningSummary(p) {
    p = p || {};
    return {
      youPay: str(p.youPay),
      youReceive: str(p.youReceive),
      pair: str(p.pair),
      side: str(p.side),
      rate: str(p.rate),
      minimumReceived: str(p.minimumReceived),
      fees: str(p.fees != null ? p.fees : 'network fees only (no protocol fee in this preview)'),
      counterparty: str(p.counterparty),
      networkA: str(p.networkA),
      networkB: str(p.networkB),
      htlcContract: str(p.htlcContract),
      quoteExpiry: str(p.quoteExpiry),
      htlcTimelock: str(p.htlcTimelock),
      refundAvailableAt: str(p.refundAvailableAt),
      nonce: str(p.nonce)
    };
  }
  function str(v) { return (v == null) ? '' : String(v); }
  var SUMMARY_FIELDS = [
    ['youPay', 'YOU PAY'], ['youReceive', 'YOU RECEIVE'], ['pair', 'PAIR'], ['side', 'SIDE'],
    ['rate', 'RATE'], ['minimumReceived', 'MINIMUM RECEIVED'], ['fees', 'FEES'],
    ['counterparty', 'COUNTERPARTY'], ['networkA', 'NETWORK A'], ['networkB', 'NETWORK B'],
    ['htlcContract', 'HTLC CONTRACT ADDRESS'], ['quoteExpiry', 'QUOTE EXPIRY'],
    ['htlcTimelock', 'HTLC TIMELOCK'], ['refundAvailableAt', 'REFUND AVAILABLE AT'], ['nonce', 'NONCE']
  ];
  // Every required field present (non-empty) — a swap must never request an opaque signature.
  function summaryComplete(s) {
    if (!s) return false;
    for (var i = 0; i < SUMMARY_FIELDS.length; i++) { if (str(s[SUMMARY_FIELDS[i][0]]) === '') return false; }
    return true;
  }
  function formatSigningSummaryText(s) {
    return SUMMARY_FIELDS.map(function (f) { return f[1] + ': ' + str(s[f[0]]); }).join('\n');
  }

  return {
    HOUR: HOUR, DAY: DAY, BLOCK_TIME_SECS: BLOCK_TIME_SECS,
    POLICY: POLICY, DEVNET: DEVNET, COMPONENTS: COMPONENTS, QUOTE_EXPIRY_SECS: QUOTE_EXPIRY_SECS,
    shortChainFor: shortChainFor, computeTimelocks: computeTimelocks, validateTimelocks: validateTimelocks,
    shortLegRefundDisplay: shortLegRefundDisplay, sostRefundDisplay: sostRefundDisplay, safetyGapDisplay: safetyGapDisplay,
    deadlineRecord: deadlineRecord, reconcileDeadlines: reconcileDeadlines,
    PINNED_HTLC: PINNED_HTLC, registerPin: registerPin, resolveExpectedHtlc: resolveExpectedHtlc, assertPinnedContract: assertPinnedContract,
    buildSigningSummary: buildSigningSummary, summaryComplete: summaryComplete,
    SUMMARY_FIELDS: SUMMARY_FIELDS, formatSigningSummaryText: formatSigningSummaryText
  };
});
