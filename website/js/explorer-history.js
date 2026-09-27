/* SOST Explorer — paginated address history + reconciliation, READ-ONLY.
 *
 * Design goals (P8):
 *  - Paginated history with a HARD RPC cost budget per page; the reader refuses
 *    to exceed it rather than hammering the node (protects explorer/node health).
 *  - Reconciliation: sum(received) - sum(sent) must equal the node-reported
 *    balance; mismatches are surfaced, never hidden.
 *  - Rich per-output classification: transfer / change / coinbase(immature) /
 *    time-locked / atomic-swap HTLC state / Asset-Passport (capsule doc_ref) anchor.
 *  - No writes, no keys, no broadcast. RPC is injected (mockable in tests).
 *
 * Output-type codes mirror include/sost/transaction.h.
 */
(function (root) {
  "use strict";

  var OUT = {
    TRANSFER: 0x00, COINBASE_MINER: 0x01, COINBASE_GOLD: 0x02, COINBASE_POPC: 0x03,
    COINBASE_LOTTERY: 0x04, BOND_LOCK: 0x10, ESCROW_LOCK: 0x11,
    HTLC_LOCK: 0x12, HTLC_CLAIM_WITNESS: 0x13, BURN: 0x20, NODE_PROTOCOL: 0x30
  };
  var COINBASE_MATURITY = 1000; // mainnet (consensus_constants.h)

  function isCoinbaseType(t) {
    return t === OUT.COINBASE_MINER || t === OUT.COINBASE_GOLD || t === OUT.COINBASE_POPC || t === OUT.COINBASE_LOTTERY;
  }

  // Classify a single output for display. ctx = {tipHeight, confirmedHeight}
  function classifyOutput(out, addr, ctx) {
    var flags = [];
    var kind = "transfer";
    var t = out.type;
    if (isCoinbaseType(t)) {
      kind = "coinbase";
      var conf = (ctx.tipHeight - out.height) + 1;
      if (conf < COINBASE_MATURITY) flags.push("immature(" + conf + "/" + COINBASE_MATURITY + ")");
    } else if (t === OUT.HTLC_LOCK) {
      kind = "atomic_swap_htlc_lock";
      flags.push("htlc:locked");
    } else if (t === OUT.HTLC_CLAIM_WITNESS) {
      kind = "atomic_swap_htlc_claim";
      flags.push("htlc:claimed");
    } else if (t === OUT.BOND_LOCK) { kind = "bond_lock"; flags.push("locked:bond"); }
    else if (t === OUT.ESCROW_LOCK) { kind = "escrow_lock"; flags.push("locked:escrow"); }
    else if (t === OUT.BURN) { kind = "burn"; }
    // absolute time-lock (lock_until height) applies to any type
    if (out.lock_until != null && ctx.tipHeight < out.lock_until) {
      flags.push("timelocked(until " + out.lock_until + ")");
    }
    // Asset-Passport anchor: a capsule doc_ref payload on a TRANSFER output
    if (out.capsule && out.capsule.mode === "doc_ref") {
      flags.push("asset_passport:" + (out.capsule.doc_hash ? out.capsule.doc_hash.slice(0, 12) + "…" : "docref"));
    }
    // is this output "change" back to the same address on a tx it also spent from?
    if (kind === "transfer" && ctx.spentFromAddr && out.address === addr) flags.push("change?");
    return { kind: kind, flags: flags };
  }

  // rpc must implement: tipHeight()->n, addressTxids(addr,{limit,cursor})->{txids,nextCursor},
  //                     getTx(txid)->{txid,height,vin:[{address,amount,type}],vout:[{address,amount,type,height,lock_until,capsule}]}
  function makeHistoryReader(rpc, opts) {
    opts = opts || {};
    var pageSize = Math.min(opts.pageSize || 25, 100);      // hard cap
    var maxRpcPerPage = opts.maxRpcPerPage || (pageSize + 3); // budget: 1 list + N tx + tip + slack
    var maxTotalRpc = opts.maxTotalRpc || 5000;              // absolute session ceiling
    var totalRpc = 0;

    function spend(n) {
      totalRpc += n;
      if (totalRpc > maxTotalRpc) { var e = new Error("RPC session budget exceeded (" + totalRpc + ">" + maxTotalRpc + ")"); e.code = "RPC_BUDGET"; throw e; }
    }

    function page(address, cursor, filter) {
      var cost = 0;
      var tip = rpc.tipHeight(); cost++;
      var listing = rpc.addressTxids(address, { limit: pageSize, cursor: cursor || null }); cost++;
      var txids = listing.txids || [];
      if (txids.length > pageSize) txids = txids.slice(0, pageSize); // never fetch more than the page
      if (cost + txids.length > maxRpcPerPage) {
        // enforce the budget by trimming, and REPORT the truncation (no silent cap)
        var allowed = Math.max(0, maxRpcPerPage - cost);
        txids = txids.slice(0, allowed);
      }
      spend(cost + txids.length);

      var items = [];
      txids.forEach(function (txid) {
        var tx = rpc.getTx(txid); cost++;
        var spentFromAddr = (tx.vin || []).some(function (i) { return i.address === address; });
        var ctx = { tipHeight: tip, confirmedHeight: tx.height, spentFromAddr: spentFromAddr };
        var outs = (tx.vout || []).map(function (o) {
          var c = classifyOutput(o, address, ctx);
          return { address: o.address, amount: o.amount, type: o.type, kind: c.kind, flags: c.flags };
        });
        var relevant = outs.filter(function (o) { return o.address === address; })
          .concat((tx.vin || []).filter(function (i) { return i.address === address; }).map(function (i) { return { spent: true, amount: i.amount, address: i.address }; }));
        var item = { txid: tx.txid, height: tx.height, confirmations: tip - tx.height + 1, outputs: outs, involves: relevant };
        if (!filter || filter === "all" || outs.some(function (o) { return o.kind === filter || o.flags.some(function (f) { return f.indexOf(filter) === 0; }); })) items.push(item);
      });

      return {
        address: address,
        items: items,
        nextCursor: listing.nextCursor || null,
        rpc_cost: cost,
        rpc_budget: maxRpcPerPage,
        truncated: (listing.txids || []).length > txids.length,
        note: "read-only; page bounded to " + maxRpcPerPage + " RPC calls"
      };
    }

    // Reconcile the FULL history for an address, still under the global budget.
    function reconcile(address) {
      var tip = rpc.tipHeight(); spend(1);
      var received = 0, sent = 0, immature = 0, locked = 0, htlcOpen = 0;
      var cursor = null, guard = 0;
      do {
        var listing = rpc.addressTxids(address, { limit: 100, cursor: cursor }); spend(1);
        (listing.txids || []).forEach(function (txid) {
          var tx = rpc.getTx(txid); spend(1);
          (tx.vout || []).forEach(function (o) {
            if (o.address !== address) return;
            received += o.amount;
            var conf = tip - (o.height != null ? o.height : tx.height) + 1;
            if (isCoinbaseType(o.type) && conf < COINBASE_MATURITY) immature += o.amount;
            if (o.lock_until != null && tip < o.lock_until) locked += o.amount;
            if (o.type === OUT.BOND_LOCK || o.type === OUT.ESCROW_LOCK) locked += o.amount;
            if (o.type === OUT.HTLC_LOCK) htlcOpen += o.amount;
          });
          (tx.vin || []).forEach(function (i) { if (i.address === address) sent += i.amount; });
        });
        cursor = listing.nextCursor || null;
      } while (cursor && ++guard < 100000);

      var computed = received - sent;
      var info = rpc.addressInfo ? rpc.addressInfo(address) : null; if (info) spend(1);
      var reported = info ? info.balance : null;
      return {
        address: address,
        sum_received: round(received), sum_sent: round(sent),
        computed_balance: round(computed),
        reported_balance: reported != null ? round(reported) : null,
        matches: reported == null ? null : Math.abs(computed - reported) < 1e-6,
        immature: round(immature), locked: round(locked), htlc_open: round(htlcOpen),
        spendable_now: round(computed - immature - locked - htlcOpen)
      };
    }

    return { page: page, reconcile: reconcile, rpcUsed: function () { return totalRpc; }, OUT: OUT, COINBASE_MATURITY: COINBASE_MATURITY, classifyOutput: classifyOutput };
  }
  function round(x) { return Math.round(x * 1e8) / 1e8; }

  var API = { makeHistoryReader: makeHistoryReader, classifyOutput: classifyOutput, OUT: OUT, COINBASE_MATURITY: COINBASE_MATURITY };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else root.SOSTExplorerHistory = API;
})(typeof window !== "undefined" ? window : this);
