/**
 * SOST Comms — Trade Offer Protocol
 *
 * Signed offer message: maker publishes intent to buy/sell SOST for gold.
 */

export interface TradeOffer {
  version: 1;
  type: "trade_offer";
  offer_id: string;
  pair: "SOST/XAUT" | "SOST/PAXG";
  side: "buy" | "sell";  // from maker perspective
  amount_sost: string;   // decimal string, e.g. "100.00000000"
  amount_gold: string;   // decimal string, e.g. "0.050000000000000000"
  price: string;         // gold per SOST, e.g. "0.0005"
  maker_sost_addr: string;
  maker_eth_addr: string;
  expires_at: number;    // unix timestamp
  settlement_mode: "escrow_bilateral";
  nonce: string;         // unique, prevents replay
  created_at: number;
  signature: string;     // ed25519 signature over canonical hash
}

export function canonicalHash(offer: Omit<TradeOffer, "signature">): string {
  const fields = [
    offer.version,
    offer.type,
    offer.offer_id,
    offer.pair,
    offer.side,
    offer.amount_sost,
    offer.amount_gold,
    offer.price,
    offer.maker_sost_addr,
    offer.maker_eth_addr,
    offer.expires_at,
    offer.settlement_mode,
    offer.nonce,
    offer.created_at,
  ];
  const raw = fields.map(f => String(f)).join("|");
  // SHA-256 of canonical string
  return sha256(raw);
}

export function createOffer(params: {
  pair: TradeOffer["pair"];
  side: TradeOffer["side"];
  amount_sost: string;
  amount_gold: string;
  price: string;
  maker_sost_addr: string;
  maker_eth_addr: string;
  ttl_seconds?: number;
}): Omit<TradeOffer, "signature"> {
  const now = Math.floor(Date.now() / 1000);
  return {
    version: 1,
    type: "trade_offer",
    offer_id: generateId(),
    pair: params.pair,
    side: params.side,
    amount_sost: params.amount_sost,
    amount_gold: params.amount_gold,
    price: params.price,
    maker_sost_addr: params.maker_sost_addr,
    maker_eth_addr: params.maker_eth_addr,
    expires_at: now + (params.ttl_seconds || 3600),
    settlement_mode: "escrow_bilateral",
    nonce: generateNonce(),
    created_at: now,
  };
}

export function isExpired(offer: TradeOffer): boolean {
  return Math.floor(Date.now() / 1000) > offer.expires_at;
}

// Utility stubs — replace with real crypto
function sha256(input: string): string {
  // In production: use crypto.createHash('sha256')
  const { createHash } = require("crypto");
  return createHash("sha256").update(input).digest("hex");
}

function generateId(): string {
  const { randomBytes } = require("crypto");
  return randomBytes(8).toString("hex");
}

function generateNonce(): string {
  const { randomBytes } = require("crypto");
  return randomBytes(16).toString("hex");
}
