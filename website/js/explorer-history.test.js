var H = require("./explorer-history.js");
var pass = 0, fail = 0;
function ok(n, c) { if (c) pass++; else { fail++; console.log("  FAIL:", n); } }

// ---- mock chain ----
var TIP = 2000;
var A = "sost1alice", B = "sost1bob";
var TXS = {
  // coinbase to A at height 1500 -> 501 confirmations < 1000 => immature
  cb: { txid: "cb", height: 1500, vin: [], vout: [{ address: A, amount: 50, type: 0x01, height: 1500 }] },
  // A receives 30 (mature transfer) at height 100
  t1: { txid: "t1", height: 100, vin: [{ address: "sost1x", amount: 30, type: 0x00 }], vout: [{ address: A, amount: 30, type: 0x00, height: 100 }] },
  // A spends 20 to B, 10 change back to A (change?), carries an asset-passport doc_ref
  t2: { txid: "t2", height: 200, vin: [{ address: A, amount: 30, type: 0x00 }],
        vout: [{ address: B, amount: 20, type: 0x00, height: 200, capsule: { mode: "doc_ref", doc_hash: "abcdef0123456789" } },
               { address: A, amount: 10, type: 0x00, height: 200 }] },
  // A locks 5 in an HTLC (atomic swap) at height 300
  t3: { txid: "t3", height: 300, vin: [{ address: A, amount: 5, type: 0x00 }], vout: [{ address: A, amount: 5, type: 0x12, height: 300 }] },
  // A has a bond-lock 8 (locked) at height 400
  t4: { txid: "t4", height: 400, vin: [{ address: A, amount: 8, type: 0x00 }], vout: [{ address: A, amount: 8, type: 0x10, height: 400 }] }
};
var ORDER = ["cb", "t1", "t2", "t3", "t4"];
function mockRpc(counter) {
  return {
    tipHeight: function () { counter.n++; return TIP; },
    addressTxids: function (addr, o) {
      counter.n++;
      var start = o.cursor ? Number(o.cursor) : 0;
      var slice = ORDER.slice(start, start + (o.limit || 25));
      var next = start + slice.length < ORDER.length ? String(start + slice.length) : null;
      return { txids: slice, nextCursor: next };
    },
    getTx: function (id) { counter.n++; return TXS[id]; },
    addressInfo: function () { counter.n++; return { balance: 70 }; } // 50cb+10change+5htlc+8bond-3? see below
  };
}

// 1. classification: coinbase immature
var c1 = H.classifyOutput({ type: 0x01, height: 1500 }, A, { tipHeight: TIP });
ok("coinbase kind", c1.kind === "coinbase");
ok("coinbase immature flagged", c1.flags.some(function (f) { return /immature/.test(f); }));

// 2. mature coinbase (old enough)
var c2 = H.classifyOutput({ type: 0x01, height: 500 }, A, { tipHeight: TIP });
ok("mature coinbase not flagged immature", !c2.flags.some(function (f) { return /immature/.test(f); }));

// 3. HTLC lock -> atomic swap state
var c3 = H.classifyOutput({ type: 0x12 }, A, { tipHeight: TIP });
ok("htlc lock kind", c3.kind === "atomic_swap_htlc_lock" && c3.flags.indexOf("htlc:locked") >= 0);

// 4. Asset-Passport doc_ref anchor detected
var c4 = H.classifyOutput({ type: 0x00, capsule: { mode: "doc_ref", doc_hash: "deadbeefcafebabe" } }, A, { tipHeight: TIP });
ok("asset passport anchor flagged", c4.flags.some(function (f) { return f.indexOf("asset_passport:") === 0; }));

// 5. time-lock flag
var c5 = H.classifyOutput({ type: 0x00, lock_until: 9999 }, A, { tipHeight: TIP });
ok("timelock flagged", c5.flags.some(function (f) { return /timelocked/.test(f); }));

// 6. pagination + cost budget
var cnt = { n: 0 };
var reader = H.makeHistoryReader(mockRpc(cnt), { pageSize: 2, maxRpcPerPage: 4 });
var p1 = reader.page(A, null, "all");
ok("page returns items", p1.items.length > 0 && p1.items.length <= 2);
ok("page has nextCursor", p1.nextCursor !== null);
ok("page cost within budget", p1.rpc_cost <= p1.rpc_budget);

// 7. filter by kind (only asset_passport)
var cnt2 = { n: 0 };
var reader2 = H.makeHistoryReader(mockRpc(cnt2), { pageSize: 100, maxRpcPerPage: 200 });
var pAll = reader2.page(A, null, "all");
ok("full page sees all 5 txs", pAll.items.length === 5);
var pAP = reader2.page(A, null, "asset_passport");
ok("asset_passport filter narrows", pAP.items.length === 1 && pAP.items[0].txid === "t2");

// 8. change detection
var t2item = pAll.items.find(function (x) { return x.txid === "t2"; });
ok("change output flagged", t2item.outputs.some(function (o) { return o.address === A && o.flags.indexOf("change?") >= 0; }));

// 9. reconciliation math
// received by A: 50(cb)+30(t1)+10(t2 change)+5(t3 htlc)+8(t4 bond) = 103
// sent by A (vin): 30(t2)+5(t3)+8(t4) = 43  => computed 60
var cnt3 = { n: 0 };
var rec = H.makeHistoryReader(mockRpc(cnt3), {}).reconcile(A);
ok("sum_received", rec.sum_received === 103);
ok("sum_sent", rec.sum_sent === 43);
ok("computed_balance", rec.computed_balance === 60);
ok("immature counted (50 coinbase)", rec.immature === 50);
ok("locked counted (8 bond)", rec.locked === 8);
ok("htlc_open counted (5)", rec.htlc_open === 5);
// spendable = 60 - 50 - 8 - 5 = -3  (over-committed illustration; still computed honestly)
ok("spendable_now = computed - immature - locked - htlc", rec.spendable_now === (60 - 50 - 8 - 5));

// 10. reconcile flags mismatch vs reported balance
ok("reported balance present", rec.reported_balance === 70);
ok("mismatch surfaced (60 != 70)", rec.matches === false);

// 11. session RPC budget is enforced (throws, not silently continues)
var threw = false;
try {
  var tiny = H.makeHistoryReader(mockRpc({ n: 0 }), { maxTotalRpc: 2 });
  tiny.page(A, null, "all"); tiny.page(A, "2", "all"); tiny.page(A, "4", "all");
} catch (e) { threw = e.code === "RPC_BUDGET"; }
ok("session RPC budget enforced", threw);

console.log("EXPLORER-HISTORY TESTS: PASS=" + pass + " FAIL=" + fail);
process.exit(fail ? 1 : 0);
