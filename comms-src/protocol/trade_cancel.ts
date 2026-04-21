/**
 * SOST Comms — Trade Cancel Protocol
 *
 * Signed cancellation: either party can cancel before BOTH_LOCKED state.
 */

export interface TradeCancel {
  version: 1;
  type: "trade_cancel";
  cancel_id: string;
  target_id: string;      // offer_id or deal_id being cancelled
  target_type: "offer" | "deal";
  cancelled_by: string;   // SOST address of canceller
  reason: string;
  cancelled_at: number;
  nonce: string;
  signature: string;
}

export function canonicalHash(cancel: Omit<TradeCancel, "signature">): string {
  const fields = [
    cancel.version,
    cancel.type,
    cancel.cancel_id,
    cancel.target_id,
    cancel.target_type,
    cancel.cancelled_by,
    cancel.reason,
    cancel.cancelled_at,
    cancel.nonce,
  ];
  const raw = fields.map(f => String(f)).join("|");
  const { createHash } = require("crypto");
  return createHash("sha256").update(raw).digest("hex");
}

export function createCancel(params: {
  target_id: string;
  target_type: "offer" | "deal";
  cancelled_by: string;
  reason?: string;
}): Omit<TradeCancel, "signature"> {
  const { randomBytes } = require("crypto");
  return {
    version: 1,
    type: "trade_cancel",
    cancel_id: randomBytes(8).toString("hex"),
    target_id: params.target_id,
    target_type: params.target_type,
    cancelled_by: params.cancelled_by,
    reason: params.reason || "",
    cancelled_at: Math.floor(Date.now() / 1000),
    nonce: randomBytes(16).toString("hex"),
  };
}
