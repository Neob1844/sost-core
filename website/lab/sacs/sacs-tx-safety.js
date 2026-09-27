/* SACS — transaction-safety state machine (Delivery A, no consensus change).
 *
 * Tracks a deposit/payment through reorgs so wallets, the Explorer and exchanges never
 * present as final a transaction whose confirming block is no longer on the active chain.
 * Pure logic over an injected read-only chain view (wireable to the node RPC:
 * getblockcount / getblockhash / gettxout / getrawmempool). No node/consensus change.
 *
 * States (exact, per the SACS spec):
 *   PENDING            seen (mempool) or 0-conf, not yet in a confirmed block we trust
 *   CONFIRMED          in a canonical block with >= required confirmations
 *   REORGED            its confirming block is no longer on the active chain
 *   REENTERED_MEMPOOL  after a reorg, the tx is back in the mempool (still spendable-to-be)
 *   CONFLICTED         a different tx spending the same input is now confirmed
 *   REPLACED           an explicit replacement (same intent) confirmed instead
 *   UNKNOWN            insufficient chain data to decide (never invent certainty)
 *
 * A deep-reorg alert (from the SACS reorg monitor) suspends CREDITING regardless of conf count.
 */
(function (root) {
  "use strict";

  var S = { PENDING:"PENDING", CONFIRMED:"CONFIRMED", REORGED:"REORGED",
            REENTERED_MEMPOOL:"REENTERED_MEMPOOL", CONFLICTED:"CONFLICTED",
            REPLACED:"REPLACED", UNKNOWN:"UNKNOWN" };

  // chainView (all read-only, all node-RPC-backed in production):
  //   tipHeight()                      -> number
  //   blockHashAt(height)              -> hash|null            (getblockhash)
  //   txConfirmedIn(txid)              -> {height,hash}|null   (tx's confirming block, if any)
  //   inMempool(txid)                  -> bool                 (getrawmempool)
  //   conflictOf(txid)                 -> {txid,replacement:bool}|null  (a confirmed tx spending the same input)
  //   deepReorgActive()                -> bool                 (SACS monitor flag)
  //   dataComplete()                   -> bool                 (node synced + history available)
  function makeTracker(chainView, opts) {
    opts = opts || {};
    var cv = chainView;
    var deposits = Object.create(null); // txid -> record

    function track(txid, meta) {
      meta = meta || {};
      deposits[txid] = { txid: txid, amount: meta.amount || 0,
        confirmBlock: null, confirmHeight: null, status: S.PENDING, confirmations: 0, note: "",
        everConfirmed: false };
      return update(txid);
    }

    function update(txid) {
      var d = deposits[txid]; if (!d) return null;
      if (!cv.dataComplete()) { d.status = S.UNKNOWN; d.note = "node not synced / history incomplete"; return snap(d); }

      var conf = cv.txConfirmedIn(txid);       // where (if anywhere) the tx is currently mined
      var conflict = cv.conflictOf(txid);      // a confirmed double-spend of one of its inputs
      var tip = cv.tipHeight();

      if (conflict) {
        d.status = conflict.replacement ? S.REPLACED : S.CONFLICTED;
        d.confirmBlock = null; d.confirmHeight = null; d.confirmations = 0;
        d.note = (conflict.replacement ? "replaced by " : "conflicting tx ") + conflict.txid;
        return snap(d);
      }

      if (conf) {
        // is that block still on the active chain?
        var canonical = cv.blockHashAt(conf.height) === conf.hash;
        if (canonical) {
          d.confirmBlock = conf.hash; d.confirmHeight = conf.height;
          d.confirmations = tip - conf.height + 1;
          d.status = S.CONFIRMED; d.everConfirmed = true; d.note = "";
          return snap(d);
        }
        // confirmed in a block that is no longer canonical -> reorged out
      }

      // Not in a canonical block. Distinguish reorged-out vs still-pending using the
      // persistent everConfirmed flag (confirmBlock is cleared on the first reorg tick).
      if (d.everConfirmed) {
        d.confirmBlock = null; d.confirmHeight = null; d.confirmations = 0;
        d.status = cv.inMempool(txid) ? S.REENTERED_MEMPOOL : S.REORGED;
        d.note = d.status === S.REENTERED_MEMPOOL ? "back in mempool after reorg" : "dropped by reorg; not in mempool";
        return snap(d);
      }
      // never confirmed
      d.status = S.PENDING; d.note = "";
      return snap(d);
    }

    function updateAll() { return Object.keys(deposits).map(update); }

    // Exchange/wallet credit policy — configurable, NEVER a consensus rule.
    //   policy: { tiers:[{maxAmount, minConf}], defaultMinConf, suspendOnDeepReorg:true }
    function creditable(txid, policy) {
      policy = policy || {}; var d = deposits[txid];
      if (!d) return { credit:false, reason:"unknown deposit" };
      if (policy.suspendOnDeepReorg !== false && cv.deepReorgActive())
        return { credit:false, reason:"deep-reorg alert — crediting suspended" };
      if (d.status !== S.CONFIRMED)
        return { credit:false, reason:"not confirmed on the active chain (" + d.status + ")" };
      var need = requiredConf(d.amount, policy);
      if (d.confirmations < need)
        return { credit:false, reason:"needs " + need + " confirmations (" + d.confirmations + ")" };
      return { credit:true, reason:"confirmed with " + d.confirmations + "/" + need };
    }
    function requiredConf(amount, policy) {
      var tiers = (policy.tiers || []).slice().sort(function (a, b) { return a.maxAmount - b.maxAmount; });
      for (var i = 0; i < tiers.length; i++) if (amount <= tiers[i].maxAmount) return tiers[i].minConf;
      return policy.defaultMinConf != null ? policy.defaultMinConf : 30;
    }

    function snap(d) { return { txid:d.txid, amount:d.amount, status:d.status,
      confirmations:d.confirmations, confirmHeight:d.confirmHeight, note:d.note }; }
    function get(txid) { return deposits[txid] ? snap(deposits[txid]) : null; }

    return { track:track, update:update, updateAll:updateAll, creditable:creditable,
             requiredConf:requiredConf, get:get, STATES:S };
  }

  var API = { makeTracker: makeTracker, STATES: S };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  if (root) root.SACSTxSafety = API;
})(typeof self !== "undefined" ? self : this);
