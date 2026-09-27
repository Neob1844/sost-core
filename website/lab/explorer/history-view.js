/* SOST Explorer — history renderer (lab). Turns SOSTExplorerHistory page/reconcile
 * output into DOM, with pagination + filter + a visible RPC-budget readout. Kept
 * separate from the live 9.7k-line explorer; this is the integration surface.
 */
(function (root) {
  "use strict";

  function flagBadge(f) {
    var cls = "fl";
    if (/immature|timelocked/.test(f)) cls += " warn";
    else if (/htlc/.test(f)) cls += " swap";
    else if (/asset_passport/.test(f)) cls += " passport";
    else if (/locked/.test(f)) cls += " lock";
    else if (/change/.test(f)) cls += " change";
    return '<span class="' + cls + '">' + f + "</span>";
  }

  function renderPage(container, pageResult, addr) {
    var rows = pageResult.items.map(function (it) {
      var outs = it.outputs.map(function (o) {
        return '<div class="out"><span class="kind">' + o.kind + "</span>" +
          '<span class="amt">' + o.amount + "</span>" +
          (o.flags.length ? '<span class="flags">' + o.flags.map(flagBadge).join("") + "</span>" : "") +
          "</div>";
      }).join("");
      return '<tr><td class="txid">' + it.txid + '</td><td class="h">' + it.height +
        '</td><td class="c">' + it.confirmations + "</td><td>" + outs + "</td></tr>";
    }).join("");
    container.innerHTML =
      '<div class="rpcbar">RPC cost this page: <b>' + pageResult.rpc_cost + " / " + pageResult.rpc_budget + "</b>" +
      (pageResult.truncated ? ' <span class="trunc">page truncated to stay within budget</span>' : "") + "</div>" +
      '<table class="hist"><thead><tr><th>txid</th><th>height</th><th>conf</th><th>outputs</th></tr></thead><tbody>' +
      (rows || '<tr><td colspan="4" class="empty">no matching transactions</td></tr>') + "</tbody></table>" +
      (pageResult.nextCursor != null ? '<button class="more" data-cursor="' + pageResult.nextCursor + '">Load more</button>' : "");
    return { rendered: pageResult.items.length, truncated: pageResult.truncated };
  }

  function renderReconcile(container, rec) {
    function money(x) { return x == null ? "—" : x; }
    container.innerHTML =
      '<div class="rec">' +
      row("Received", money(rec.sum_received)) + row("Sent", money(rec.sum_sent)) +
      row("Computed balance", money(rec.computed_balance)) + row("Node-reported", money(rec.reported_balance)) +
      '<div class="rr ' + (rec.matches === false ? "bad" : "good") + '">' +
      (rec.matches == null ? "no reported balance to compare" : (rec.matches ? "✓ reconciles" : "✗ MISMATCH")) + "</div>" +
      row("Immature", money(rec.immature)) + row("Locked", money(rec.locked)) + row("HTLC open", money(rec.htlc_open)) +
      row("Spendable now", money(rec.spendable_now)) + "</div>";
  }
  function row(k, v) { return '<div class="r"><span>' + k + '</span><b>' + v + "</b></div>"; }

  var API = { renderPage: renderPage, renderReconcile: renderReconcile, flagBadge: flagBadge };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  if (root) root.SOSTHistoryView = API;
})(typeof self !== "undefined" ? self : this);
