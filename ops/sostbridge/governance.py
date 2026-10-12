"""SOST participant governance (Stage 1 research model) — proposals, census, on-chain votes, tally.

Votes are ordinary SOST transactions from the eligible identity to itself carrying an open-note
capsule:   SOSTGOV1|<proposal_id>|S<snapshot_height>|YES|NO|ABSTAIN
No consensus change and no new message-signing tool: spending from the identity proves key control.

Rules (exact):
  * census = identities eligible at the snapshot, frozen; one identity = one vote
  * valid vote: every input spends from the identity, an output pays the identity carrying the
    capsule, proposal id and snapshot match, confirmed at a height in (snapshot, close]
  * the LAST valid vote confirmed before the close wins; earlier votes stay in the audit history
  * approval: YES >= ceil(2/3 x census) — never 2/3 of the votes cast; ABSTAIN is never YES
  * states: OPEN -> CLOSED_FINALITY_PENDING -> FINAL_PASS | FINAL_FAIL (configurable finality depth)

SOST votes do not execute Ethereum. Guardians submit the final tally to Gold Reserve V2; the
contract checks the 2/3 arithmetic and the frozen proposal hash, and anyone can recount from chain.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from eth_abi import encode as abi_encode
from eth_utils import keccak, to_checksum_address

from .common import parse_open_note, is_sost_address
from .sostchain import iter_canonical_txs

OPEN, CLOSED_FINALITY_PENDING, FINAL_PASS, FINAL_FAIL = "OPEN", "CLOSED_FINALITY_PENDING", "FINAL_PASS", "FINAL_FAIL"
VOTE_RE = re.compile(r"^SOSTGOV1\|([A-Za-z0-9\-]{1,31})\|S([0-9]{1,12})\|(YES|NO|ABSTAIN)$")
PROPOSAL_VERSION = 1


def bytes32_text(s: str) -> bytes:
    b = s.encode()
    if len(b) > 32:
        raise ValueError("id longer than 32 bytes")
    return b + b"\x00" * (32 - len(b))


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    source_vault: str
    source_asset: str
    successor_vault: str
    successor_asset: str
    successor_code_hash: bytes
    snapshot_height: int
    close_height: int
    timelock: int
    reason: str
    version: int = PROPOSAL_VERSION

    def reason_hash(self) -> bytes:
        return keccak(text=self.reason)

    def proposal_hash(self) -> bytes:
        """Identical to ReserveBase.proposalHash: commits to every material field."""
        return keccak(abi_encode(
            ["string", "bytes32", "address", "address", "address", "address", "bytes32", "uint64", "uint64", "uint64", "bytes32", "uint32"],
            ["SOSTGOV1-GRV2-MIGRATION", bytes32_text(self.proposal_id), to_checksum_address(self.source_vault),
             to_checksum_address(self.source_asset), to_checksum_address(self.successor_vault),
             to_checksum_address(self.successor_asset), self.successor_code_hash, self.snapshot_height,
             self.close_height, self.timelock, self.reason_hash(), self.version]))

    def as_tuple(self):
        return (bytes32_text(self.proposal_id), to_checksum_address(self.source_vault), to_checksum_address(self.source_asset),
                to_checksum_address(self.successor_vault), to_checksum_address(self.successor_asset),
                self.successor_code_hash, self.snapshot_height, self.close_height, self.timelock,
                self.reason_hash(), self.version)


# ---------------------------------------------------------------- census
@dataclass(frozen=True)
class EligibilityRules:
    """Explicit governance eligibility (derived from, but not identical to, Jackpot V2)."""
    min_pow_blocks: int = 3            # SbPoW blocks in the window before the snapshot
    pow_window: int = 2016
    require_node_bind: bool = True
    require_heartbeats: bool = True
    min_bind_age_blocks: int = 576     # research value (2 epochs); to be set by simulation


@dataclass(frozen=True)
class ParticipantRecord:
    address: str
    pow_blocks: int                    # in the window ending at the snapshot
    node_bound: bool
    bind_height: Optional[int]
    heartbeats_ok: bool


def is_eligible(r: ParticipantRecord, snapshot: int, rules: EligibilityRules) -> bool:
    if not is_sost_address(r.address):
        return False
    if r.pow_blocks < rules.min_pow_blocks:
        return False
    if rules.require_node_bind:
        if not r.node_bound or r.bind_height is None or r.bind_height > snapshot:
            return False
        if snapshot - r.bind_height < rules.min_bind_age_blocks:
            return False
    if rules.require_heartbeats and not r.heartbeats_ok:
        return False
    return True


def freeze_census(records: List[ParticipantRecord], snapshot: int, rules: EligibilityRules) -> List[str]:
    return sorted({r.address for r in records if is_eligible(r, snapshot, rules)})


def census_hash(census: List[str]) -> bytes:
    return keccak(text="\n".join(sorted(census)))


# ---------------------------------------------------------------- votes
@dataclass
class Vote:
    voter: str
    choice: str
    txid: str
    height: int
    order: int                          # position in block, for deterministic ordering


@dataclass
class Tally:
    proposal_id: str
    proposal_hash: str
    snapshot: int
    close: int
    tip: int
    state: str
    census: int
    required_yes: int
    yes: int
    no: int
    abstain: int
    no_vote: int
    passed: bool
    final_votes: Dict[str, str]
    history: List[dict]
    ignored: List[dict]
    tally_hash: str
    final_height: int

    def to_json(self):
        return json.dumps(asdict(self), indent=2, sort_keys=True)


def required_yes(census: int) -> int:
    return (2 * census + 2) // 3          # ceil(2/3 * census)


def parse_vote_text(text: Optional[str]):
    if not text:
        return None
    m = VOTE_RE.match(text)
    if not m:
        return None
    return m.group(1), int(m.group(2)), m.group(3)


def tally(rpc, proposal: Proposal, census: List[str], finality_depth: int) -> Tally:
    tip = rpc.getblockcount()
    census_set = set(census)
    history: List[Vote] = []
    ignored: List[dict] = []
    end = min(proposal.close_height, tip)
    order = 0
    for h, bh, tx in iter_canonical_txs(rpc, proposal.snapshot_height + 1, end):
        order += 1
        vin = tx.get("vin", []) or []
        for o in tx.get("vout", []) or []:
            text = parse_open_note(o.get("payload_hex"))
            if not text or not text.startswith("SOSTGOV1"):
                continue
            pv = parse_vote_text(text)
            entry = {"txid": tx["txid"], "height": h, "text": text}
            if pv is None:
                ignored.append({**entry, "why": "malformed vote capsule"}); continue
            pid, snap, choice = pv
            if pid != proposal.proposal_id:
                ignored.append({**entry, "why": "different proposal"}); continue
            if snap != proposal.snapshot_height:
                ignored.append({**entry, "why": "wrong snapshot"}); continue
            voter = o.get("address")
            if not vin or any(i.get("address") != voter for i in vin):
                ignored.append({**entry, "why": "transaction does not spend only from the voting identity"}); continue
            if voter not in census_set:
                ignored.append({**entry, "why": "voter not in the snapshot census"}); continue
            history.append(Vote(voter, choice, tx["txid"], h, order))
    # votes after the close are never scanned; report them for transparency if visible
    final: Dict[str, Vote] = {}
    for v in sorted(history, key=lambda v: (v.height, v.order)):
        final[v.voter] = v                     # last valid vote before close wins
    yes = sum(1 for v in final.values() if v.choice == "YES")
    no = sum(1 for v in final.values() if v.choice == "NO")
    ab = sum(1 for v in final.values() if v.choice == "ABSTAIN")
    req = required_yes(len(census))
    passed = len(census) > 0 and yes >= req
    if tip < proposal.close_height:
        state = OPEN
    elif tip < proposal.close_height + finality_depth:
        state = CLOSED_FINALITY_PENDING
    else:
        state = FINAL_PASS if passed else FINAL_FAIL
    final_votes = {k: v.choice for k, v in sorted(final.items())}
    th = keccak(text=json.dumps({"proposal": proposal.proposal_hash().hex(), "census": sorted(census), "votes": final_votes},
                                sort_keys=True))
    return Tally(proposal.proposal_id, "0x" + proposal.proposal_hash().hex(), proposal.snapshot_height,
                 proposal.close_height, tip, state, len(census), req, yes, no, ab, len(census) - len(final),
                 passed, final_votes, [asdict(v) for v in history], ignored, "0x" + th.hex(),
                 proposal.close_height + finality_depth)


def gov_result_tuple(t: Tally):
    """GovResult for ReserveBase.queueMigration (only meaningful when state is FINAL_PASS)."""
    if t.state not in (FINAL_PASS, FINAL_FAIL):
        raise ValueError("tally not final")
    return (bytes.fromhex(t.proposal_hash[2:]), t.census, t.yes, t.no, t.abstain, t.final_height, bytes.fromhex(t.tally_hash[2:]))
