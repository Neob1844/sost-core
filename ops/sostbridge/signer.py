"""Native SOST release path behind a swappable signer interface.

Stage 1 uses ColdSingleSigner (one offline key, capped pilot) because SOST mainnet has no
operational native multisig. A future NativeMultisigSigner implements the same interface, so the
deposit / attestation / accounting code does not change. No production key exists anywhere in
this repository; tests and the devnet E2E generate disposable keys.

Release rules: one burn releases at most once (journal + chain check), the amount is the burned
amount minus the published fee allowance, the destination is exactly the sost address the holder
named in the burn, and the release carries the capsule WSOST-RELEASE:0x<burnId>.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional

from .common import release_note, fmt_sost, build_open_note, is_sost_address
from .ledger import scan_vault


@dataclass
class ReleaseRequest:
    burn_id: bytes
    dest: str
    amount: int          # stocks actually sent (burn amount - fee allowance)


class ReleaseSigner(ABC):
    """Signs AND submits one native SOST release; returns its txid. Implementations decide where the
    key lives (cold single key now, native multisig later)."""

    @abstractmethod
    def execute_release(self, req: ReleaseRequest) -> str:
        ...


class ColdSingleSigner(ReleaseSigner):
    """Single key held in a dedicated vault wallet file (Stage 1 / capped pilot).

    Uses `sost-cli send --from-address <vault> --capsule-mode open-note`. LIMITATION (documented):
    the current `sost-cli createtx` (build + sign without broadcast) does not accept a capsule, so a
    fully air-gapped signature of a capsule-bearing release needs a future CLI feature. Stage 1 runs
    the signer on the signing machine with the node reachable; the key never leaves that wallet file."""

    def __init__(self, cli: str, wallet: str, vault: str, node: str, extra: Optional[List[str]] = None):
        self.cli, self.wallet, self.vault, self.node, self.extra = cli, wallet, vault, node, extra or []

    def execute_release(self, req: ReleaseRequest) -> str:
        cmd = [self.cli, "--wallet", self.wallet, "--node", self.node, *self.extra, "--yes",
               "--from-address", self.vault, "--capsule-mode", "open-note",
               "--capsule-text", release_note(req.burn_id), "send", req.dest, fmt_sost(req.amount)]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        text = out.stdout + out.stderr
        m = re.findall(r"\b([0-9a-f]{64})\b", text)
        if out.returncode != 0 or not m:
            raise RuntimeError("release send failed: " + text[-500:])
        return m[-1]


class NativeMultisigSigner(ReleaseSigner):
    """Placeholder for the target model (future, explicitly activated native multisig)."""

    def execute_release(self, req: ReleaseRequest) -> str:
        raise NotImplementedError("native multisig is not active on SOST; requires a future consensus upgrade")


class FakeChainSigner(ReleaseSigner):
    """Test signer for FakeSostChain: mines the release in a new block."""

    def __init__(self, chain, vault: str, fee: int = 2000):
        self.chain, self.vault, self.fee = chain, vault, fee

    def execute_release(self, req: ReleaseRequest) -> str:
        from .sostchain import FakeSostChain
        bal = scan_vault(self.chain, self.vault, 0).vault_balance
        note = release_note(req.burn_id)
        txid = FakeSostChain.txid_for(f"release:{note}:{len(self.chain.blocks)}")
        self.chain.add_block([{
            "txid": txid,
            "vin": [{"address": self.vault, "amount": fmt_sost(bal)}],
            "vout": [{"address": req.dest, "amount": fmt_sost(req.amount), "payload_hex": build_open_note(note)},
                     {"address": self.vault, "amount": fmt_sost(bal - req.amount - self.fee)}],
        }])
        return txid


class ReleaseJournal:
    """Persistent burn_id -> txid record. A burn already journaled is never signed again, even if
    its release is still in a mempool the indexer cannot see."""

    def __init__(self, path: str):
        self.path = path
        self.data: Dict[str, str] = {}
        if os.path.exists(path):
            with open(path) as f:
                self.data = json.load(f)

    def seen(self, burn_id: bytes) -> bool:
        return ("0x" + burn_id.hex()) in self.data

    def record(self, burn_id: bytes, txid: str):
        self.data["0x" + burn_id.hex()] = txid
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=1, sort_keys=True)
        os.replace(tmp, self.path)


class ReleaseProcessor:
    def __init__(self, signer: ReleaseSigner, journal: ReleaseJournal, rpc, vault: str, start_height: int, fee_allowance: int):
        self.signer, self.journal = signer, journal
        self.rpc, self.vault, self.start, self.fee_allowance = rpc, vault, start_height, fee_allowance

    def process(self, eth) -> List[str]:
        """Release every burn that has no release on chain and is not journaled. Returns txids."""
        scan = scan_vault(self.rpc, self.vault, self.start)
        done = {r.burn_id for r in scan.releases}
        out = []
        for b in eth.burn_events():
            if b.burn_id in done or self.journal.seen(b.burn_id):
                continue
            if not is_sost_address(b.sost_address) or b.amount <= self.fee_allowance:
                continue                       # flagged by the indexer; never guess a destination
            self.journal.record(b.burn_id, "PENDING")      # journal BEFORE signing: a crash cannot double-release
            txid = self.signer.execute_release(ReleaseRequest(b.burn_id, b.sost_address, b.amount - self.fee_allowance))
            self.journal.record(b.burn_id, txid)
            out.append(txid)
        return out
