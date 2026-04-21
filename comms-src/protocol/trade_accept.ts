/**
 * SOST Comms — Trade Accept Protocol
 *
 * Signed acceptance: taker commits to a specific offer.
 * Creates a deal_id from the combination of offer + accept.
 */

export interface TradeAccept {
  version: 1;
  type: "trade_accept";
  accept_id: string;
  offer_id: string;       // references the original offer
  deal_id: string;        // derived from offer_id + accept_id
  taker_sost_addr: string;
  taker_eth_addr: string;
  fill_amount_sost: string;  // can be partial fill
  fill_amount_gold: string;
  accepted_at: number;
  nonce: string;
  signature: string;
}

export function canonicalHash(accept: Omit<TradeAccept, "signature">): string {
  const fields = [
    accept.version,
    accept.type,
    accept.accept_id,
    accept.offer_id,
    accept.deal_id,
    accept.taker_sost_addr,
    accept.taker_eth_addr,
    accept.fill_amount_sost,
    accept.fill_amount_gold,
    accept.accepted_at,
    accept.nonce,
  ];
  const raw = fields.map(f => String(f)).join("|");
  const { createHash } = require("crypto");
  return createHash("sha256").update(raw).digest("hex");
}

export function deriveDealId(offer_id: string, accept_id: string): string {
  const { createHash } = require("crypto");
  return createHash("sha256")
    .update(`${offer_id}:${accept_id}`)
    .digest("hex")
    .substring(0, 16);
}

export function createAccept(params: {
  offer_id: string;
  taker_sost_addr: string;
  taker_eth_addr: string;
  fill_amount_sost: string;
  fill_amount_gold: string;
}): Omit<TradeAccept, "signature"> {
  const { randomBytes } = require("crypto");
  const accept_id = randomBytes(8).toString("hex");
  const deal_id = deriveDealId(params.offer_id, accept_id);
  return {
    version: 1,
    type: "trade_accept",
    accept_id,
    offer_id: params.offer_id,
    deal_id,
    taker_sost_addr: params.taker_sost_addr,
    taker_eth_addr: params.taker_eth_addr,
    fill_amount_sost: params.fill_amount_sost,
    fill_amount_gold: params.fill_amount_gold,
    accepted_at: Math.floor(Date.now() / 1000),
    nonce: randomBytes(16).toString("hex"),
  };
}
