/*
 * SOST Asset Draw — verifiable draw engine (Option 2, FUTURE / REGULATED).
 * ---------------------------------------------------------------------------
 * Adjudicates ONE asset among ticket holders by a deterministic, reproducible,
 * commit-then-reveal draw — the DTD *philosophy* (nobody can pick the winner
 * after the result is known) WITHOUT touching DTD / consensus / the node. It
 * lives entirely in the application layer.
 *
 * Flow: register asset (Asset Passport) -> issue tickets -> sell until the
 * target is covered (escrow, refundable while open) -> freeze (campaignHash) ->
 * announce a FUTURE entropy block height -> when that block exists, take its
 * hash as the seed -> deterministic winner index -> anyone can recompute.
 *
 * LEGAL: in Spain a paid-ticket + chance + asset-prize scheme is a *rifa*
 * (DGOJ / Ley 13/2011), not a classic auction; permanent rifas are not an
 * ordinary authorised activity today. This engine is FUTURE / REGULATED and is
 * never operated on real funds until a legal framework/authorisation exists.
 */
(function (root, factory) {
  var m = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = m;
  if (root) root.SOSTAssetDraw = m;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  async function sha256Hex(s) {
    if (typeof s !== 'string') s = JSON.stringify(s);
    var bytes = (typeof TextEncoder !== 'undefined') ? new TextEncoder().encode(s) : Buffer.from(s, 'utf8');
    if (typeof crypto !== 'undefined' && crypto.subtle) {
      var buf = await crypto.subtle.digest('SHA-256', bytes);
      return Array.from(new Uint8Array(buf)).map(function (b) { return b.toString(16).padStart(2, '0'); }).join('');
    }
    return require('crypto').createHash('sha256').update(Buffer.from(bytes)).digest('hex');
  }
  function canon(o) {
    if (o === null || typeof o !== 'object') { if (typeof o === 'number' && !Number.isInteger(o)) throw new Error('use strings for non-integers'); return JSON.stringify(o); }
    if (Array.isArray(o)) return '[' + o.map(canon).join(',') + ']';
    return '{' + Object.keys(o).sort().map(function (k) { return JSON.stringify(k) + ':' + canon(o[k]); }).join(',') + '}';
  }
  function assert(c, m) { if (!c) throw new Error(m); }

  var STATE = ['DRAFT', 'SELLING', 'SOLD_OUT', 'FROZEN', 'AWAITING_ENTROPY', 'DRAWN', 'SETTLED', 'FAILED_REFUNDED'];

  // build a campaign over an Asset Passport. price_ref_usdc is a REFERENCE; the
  // per-ticket SOST amount is quoted at purchase time by the oracle (not fixed here).
  function newCampaign(o) {
    assert(o.asset_passport_hash, 'asset_passport_hash required (register the asset first)');
    assert(o.target_tickets | 0, 'target_tickets required');
    return {
      id: o.id || null,
      asset_passport_hash: o.asset_passport_hash,
      target_tickets: o.target_tickets | 0,      // tickets needed to cover the minimum price
      price_ref_usdc: String(o.price_ref_usdc || '20'),
      network: o.network || 'devnet',
      close_height: o.close_height | 0,          // chain height at which sales close
      entropy_height: o.entropy_height | 0,      // FUTURE block whose hash seeds the draw (> close_height)
      tickets: [],                               // ticket ids in purchase order
      state: 'DRAFT', campaignHash: null, seed: null, winner_index: null, winner_ticket: null
    };
  }

  function sellTicket(c, ticketId, buyer) {
    assert(['DRAFT', 'SELLING'].indexOf(c.state) >= 0, 'not selling');
    assert(c.tickets.indexOf(ticketId) < 0, 'duplicate ticket id');
    c.state = 'SELLING';
    c.tickets.push(ticketId);
    if (c.tickets.length >= c.target_tickets) c.state = 'SOLD_OUT';   // target covered
    return c.tickets.length;
  }

  // FREEZE: only when the target is covered. Seals the ticket list + campaignHash.
  // Refund path: if not sold out by close_height, all escrows are refundable (FAILED_REFUNDED).
  async function freeze(c) {
    assert(c.state === 'SOLD_OUT', 'cannot freeze before target covered (all tickets sold)');
    assert(c.entropy_height > c.close_height, 'entropy_height must be a FUTURE block after close_height');
    c.campaignHash = await sha256Hex(canon({
      asset_passport_hash: c.asset_passport_hash, tickets: c.tickets.slice().sort(),
      target_tickets: c.target_tickets, price_ref_usdc: c.price_ref_usdc,
      close_height: c.close_height, entropy_height: c.entropy_height, network: c.network
    }));
    c.state = 'AWAITING_ENTROPY';
    return c.campaignHash;
  }

  function failIfUnsold(c, currentHeight) {
    if (c.state === 'SELLING' && currentHeight >= c.close_height && c.tickets.length < c.target_tickets) {
      c.state = 'FAILED_REFUNDED';   // deadline passed, target not covered -> everyone refunds
      return true;
    }
    return false;
  }

  // DRAW: seed = block hash at entropy_height (must be known only AFTER freeze).
  // winner index = int(sha256(campaignHash | entropyHex)) mod ticketCount. Reproducible.
  async function draw(c, entropyHex, entropyHeightSeen) {
    assert(c.state === 'AWAITING_ENTROPY', 'campaign not frozen/awaiting entropy');
    assert(/^[0-9a-fA-F]{16,}$/.test(entropyHex || ''), 'entropy must be a block hash hex');
    assert((entropyHeightSeen | 0) >= c.entropy_height, 'entropy block must be at/after the announced height (no picking after the fact)');
    c.seed = await sha256Hex(c.campaignHash + '|' + entropyHex.toLowerCase());
    var n = c.tickets.length;
    // 128-bit reduction from the seed, mod n (bias negligible for realistic n)
    var big = BigInt('0x' + c.seed.slice(0, 32));
    c.winner_index = Number(big % BigInt(n));
    c.winner_ticket = c.tickets[c.winner_index];
    c.state = 'DRAWN';
    return { winner_index: c.winner_index, winner_ticket: c.winner_ticket, seed: c.seed };
  }

  // anyone recomputes the winner from the frozen campaign + the revealed entropy.
  async function verify(campaignHash, ticketsInOrder, entropyHex) {
    var seed = await sha256Hex(campaignHash + '|' + String(entropyHex).toLowerCase());
    var idx = Number(BigInt('0x' + seed.slice(0, 32)) % BigInt(ticketsInOrder.length));
    return { winner_index: idx, winner_ticket: ticketsInOrder[idx], seed: seed };
  }

  return {
    STATES: STATE, sha256Hex: sha256Hex, canon: canon,
    newCampaign: newCampaign, sellTicket: sellTicket, freeze: freeze,
    failIfUnsold: failIfUnsold, draw: draw, verify: verify
  };
});
