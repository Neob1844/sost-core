/**
 * SOST Comms — Settlement Notice Protocol
 *
 * Notification that a deal has reached a terminal state.
 * Sent by the settlement daemon to both parties.
 */

export type SettlementOutcome = "settled" | "refunded" | "expired" | "disputed";

export interface SettlementNotice {
  version: 1;
  type: "settlement_notice";
  notice_id: string;
  deal_id: string;
  outcome: SettlementOutcome;
  eth_tx_hash: string | null;
  sost_txid: string | null;
  settlement_ref: string | null;
  detail: string;
  issued_at: number;
  signature: string;
}

export function canonicalHash(notice: Omit<SettlementNotice, "signature">): string {
  const fields = [
    notice.version,
    notice.type,
    notice.notice_id,
    notice.deal_id,
    notice.outcome,
    notice.eth_tx_hash || "",
    notice.sost_txid || "",
    notice.settlement_ref || "",
    notice.detail,
    notice.issued_at,
  ];
  const raw = fields.map(f => String(f)).join("|");
  const { createHash } = require("crypto");
  return createHash("sha256").update(raw).digest("hex");
}

export function createNotice(params: {
  deal_id: string;
  outcome: SettlementOutcome;
  eth_tx_hash?: string;
  sost_txid?: string;
  settlement_ref?: string;
  detail?: string;
}): Omit<SettlementNotice, "signature"> {
  const { randomBytes } = require("crypto");
  return {
    version: 1,
    type: "settlement_notice",
    notice_id: randomBytes(8).toString("hex"),
    deal_id: params.deal_id,
    outcome: params.outcome,
    eth_tx_hash: params.eth_tx_hash || null,
    sost_txid: params.sost_txid || null,
    settlement_ref: params.settlement_ref || null,
    detail: params.detail || "",
    issued_at: Math.floor(Date.now() / 1000),
  };
}
