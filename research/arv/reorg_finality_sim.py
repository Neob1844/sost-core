#!/usr/bin/env python3
"""C708: reorg / finality simulator for the SOST Atomic Reserve Vault (research only).

Every honest SOST node in this model applies the fork-choice rules of sost-node as they are
on mainnet today and in V17 (SACS V2 deferred, g_checkpoints[] empty):

  * a block whose parent is the active tip is connected (IBD is the same path, tip+1);
  * any other block with a known parent is admitted to the fork store, at any depth;
  * after each connect, fork blocks with height < tip - CAP are pruned (cleanup_old_forks);
  * a fork whose tip has STRICTLY more cumulative work triggers try_reorganize;
    it is refused when disconnect_count = tip_height - fork_point > CAP (Step 3);
  * a block whose parent is unknown waits as an orphan.

Simplification: every block carries the same work (difficulty constant), so cumulative work
= height + 1. This is NOT neutral: under cASERT both branches retarget, so real branches have
close heights and different work, and the real node starts syncing from a peer by advertised
HEIGHT. A heavier-but-shorter branch cannot be expressed here. Block delivery is also idealized:
every node is handed blocks in a chosen order, while the real node fetches by height (GETB) from
peers that advertise a higher height and has no fetch-by-hash. Results on fresh nodes and on
partition reconvergence are therefore "reachable orderings", not timing-faithful predictions.

The Ethereum-side relay (the light client a bridge contract would run) is modelled in three
variants:
  most_work   follows the heaviest valid header chain, no depth cap (plain SPV);
  cap_mirror  applies the same CAP as the nodes, against its own tip;
  anchor      cap_mirror + once a block is buried F deep in the relay view (and Ethereum has
              finalized that relay state) it becomes an ANCHOR that the relay never reorgs.
              Anchor-aware SOST nodes (a hypothetical hard fork that lets SOST read Ethereum
              finality, i.e. N2) refuse any chain that conflicts with a known anchor and adopt
              the anchored branch when they hold it, whatever the depth.

The bridge mints wSOST when the relay shows the deposit with >= K confirmations.

Each scenario is scored on four properties, kept strictly apart:
  LOCAL_NODE_SAFETY      a node that saw the deposit with >= K confirmations never loses it later
  NETWORK_CONVERGENCE    every honest node (synced and fresh) ends on the same tip
  GLOBAL_CANONICALITY    a single history is accepted by every honest node, fresh ones included,
                         and it is the history the relay follows
  BRIDGE_BACKING_SAFETY  every minted wSOST has its deposit on the relay's chain AND on the chain
                         of every honest node (the reserve exists in the economy's history)

Run:  python3 reorg_finality_sim.py            (prints the scenario table, exit 0 iff the
                                                 expected outcome of every scenario is reproduced)
"""
import itertools
import sys

CAP = 500          # MAX_REORG_DEPTH on mainnet
INF = 10 ** 9


class Block:
    __slots__ = ("id", "parent", "height", "deposit")
    _ids = itertools.count(1)

    def __init__(self, parent, height, deposit=False):
        self.id = next(Block._ids)
        self.parent = parent
        self.height = height
        self.deposit = deposit


GENESIS = Block(None, 0)


def chain(parent, n, deposit_at=None):
    """n blocks on top of `parent`; deposit_at = 1-based index of the block holding the deposit."""
    out, p = [], parent
    for i in range(1, n + 1):
        b = Block(p.id, p.height + 1, deposit=(i == deposit_at))
        out.append(b)
        p = b
    return out


class Node:
    def __init__(self, name, cap=CAP, prune=True, anchor_aware=False, k=None):
        self.name, self.cap, self.prune, self.anchor_aware, self.k = name, cap, prune, anchor_aware, k
        self.known = {GENESIS.id: GENESIS}
        self.active = [GENESIS.id]
        self.orphans = {}
        self.anchors = {}            # height -> block id (from the Ethereum-side anchor log)
        self.saw_final_deposit = False
        self.lost_final_deposit = False
        self.rejected_deeper = 0     # heavier chains refused by the cap (a conflict the node saw)

    # --- view helpers ---------------------------------------------------------------------
    def tip(self):
        return self.known[self.active[-1]]

    def deposit_conf(self):
        for bid in reversed(self.active):
            if self.known[bid].deposit:
                return self.tip().height - self.known[bid].height + 1
        return 0

    def _track(self):
        if self.k is None:
            return
        c = self.deposit_conf()
        if c >= self.k:
            self.saw_final_deposit = True
        elif self.saw_final_deposit and c == 0:
            self.lost_final_deposit = True

    def _conflicts_anchor(self, path_ids):
        if not self.anchors or path_ids is None:
            return False
        by_h = {self.known[i].height: i for i in path_ids}
        return any(h in by_h and by_h[h] != a for h, a in self.anchors.items())

    def _path_to(self, bid):
        """Ancestry genesis..bid, or None if an ancestor was pruned (a dead fragment)."""
        out = []
        while bid is not None:
            if bid not in self.known:
                return None
            out.append(bid)
            bid = self.known[bid].parent
        return list(reversed(out))

    # --- rules ----------------------------------------------------------------------------
    def receive(self, b):
        if b.id in self.known:
            return
        if b.parent not in self.known:
            self.orphans.setdefault(b.parent, []).append(b)
            return
        self.known[b.id] = b
        if self.anchor_aware and self._conflicts_anchor(self._path_to(b.id)):
            del self.known[b.id]           # never store a block that contradicts an anchor
            return
        if b.parent == self.active[-1]:
            self.active.append(b.id)
            self._prune()
        elif b.height > self.tip().height:  # strictly more cumulative work
            self._try_reorg(b.id)
        self._track()
        for child in self.orphans.pop(b.id, []):
            self.receive(child)

    def _try_reorg(self, tip_id, force=False):
        path = self._path_to(tip_id)
        if path is None:
            return False
        active_set = set(self.active)
        fp = max(i for i, bid in enumerate(path) if bid in active_set)
        disconnect = self.tip().height - fp
        if disconnect > self.cap and not force:
            self.rejected_deeper += 1
            return False
        self.active = path
        self._prune()
        return True

    def _prune(self):
        if not self.prune:
            return
        cutoff = self.tip().height - self.cap
        act = set(self.active)
        for bid in [i for i, b in self.known.items() if i not in act and b.height < cutoff]:
            del self.known[bid]

    def learn_anchors(self, anchor_log):
        """Anchor-aware node reads the Ethereum-finalized anchor log (N2). If its active chain
        contradicts an anchor it adopts the heaviest branch it holds that matches every anchor,
        whatever the depth: the anchor, not the cap, decides."""
        if not self.anchor_aware:
            return
        self.anchors.update(anchor_log)
        if not self._conflicts_anchor(self.active):
            return
        best = None
        for i, b in self.known.items():
            if best is not None and b.height <= self.known[best].height:
                continue
            p = self._path_to(i)
            if p is not None and not self._conflicts_anchor(p):
                best = i
        if best is not None:
            self._try_reorg(best, force=True)
        self._track()


class Relay(Node):
    """Ethereum-side SOST light client. mode: most_work | cap_mirror | anchor."""

    def __init__(self, mode, k, f=None):
        cap = INF if mode == "most_work" else CAP
        super().__init__("relay/" + mode, cap=cap, prune=(mode != "most_work"), k=k)
        self.mode, self.f = mode, f
        self.minted = False
        self.anchor_log = {}
        self.frozen = False

    def receive(self, b):
        before = self.rejected_deeper
        super().receive(b)
        if self.rejected_deeper > before and self.saw_final_deposit:
            self.frozen = True          # conflict proof: a heavier chain contradicts a final deposit
        if not self.minted and self.deposit_conf() >= self.k:
            self.minted = True
        if self.mode == "anchor":
            h = self.tip().height - self.f
            if h > 0 and h not in self.anchor_log:
                self.anchor_log[h] = self.active[h]
                self.anchors[h] = self.active[h]

    def _try_reorg(self, tip_id, force=False):
        if self.mode == "anchor" and self._conflicts_anchor(self._path_to(tip_id)):
            self.rejected_deeper += 1
            return False
        return super()._try_reorg(tip_id, force)


def feed(nodes, blocks):
    for b in blocks:
        for n in nodes:
            n.receive(b)


def score(honest, relay):
    tips = {n.tip().id for n in honest}
    conv = len(tips) == 1
    canon = conv and relay.tip().id in tips
    local = all(not n.lost_final_deposit for n in honest + [relay])
    # vacuous when nothing was minted: reported as N/A, never as YES
    backing = "N/A" if not relay.minted else \
        (relay.deposit_conf() > 0 and all(n.deposit_conf() > 0 for n in honest))
    return dict(LOCAL_NODE_SAFETY=local, NETWORK_CONVERGENCE=conv, GLOBAL_CANONICALITY=canon,
                BRIDGE_BACKING_SAFETY=backing, minted=relay.minted, frozen=relay.frozen)


# ---------------------------------------------------------------------------------------------
# scenarios
# ---------------------------------------------------------------------------------------------
BASE = 100  # shared history before the fork; the deposit is the first block after it


def s1_depth_sweep(d):
    """Synced node at honest d blocks above the fork point; attacker releases d+1 blocks without
    the deposit. Reorg accepted iff d <= CAP."""
    shared = chain(GENESIS, BASE)
    fork = shared[-1]
    honest_c = chain(fork, d, deposit_at=1)
    att = chain(fork, d + 1)
    n = Node("synced", k=1)
    feed([n], shared + honest_c)
    feed([n], att)
    return n.deposit_conf() == 0   # True = deposit erased


def s2_mint_race(k, d=CAP):
    """Majority attacker (q > 1/2, always ahead) withholds from the fork point and releases when the
    honest chain is d blocks above the fork point (the attacker picks d).
    The bridge mints when the relay (cap_mirror) shows >= k confirmations."""
    shared = chain(GENESIS, BASE)
    fork = shared[-1]
    synced = Node("synced", k=k)
    relay = Relay("cap_mirror", k=k)
    nodes = [synced, relay]
    feed(nodes, shared)
    honest_c = chain(fork, max(k, d) + 10, deposit_at=1)
    feed(nodes, honest_c[:d])                     # minted iff d >= k
    att = chain(fork, d + 50)                     # attacker is ahead (q > 1/2)
    feed(nodes, att)
    feed(nodes, honest_c[d:])                     # honest keeps mining on its view if it kept it
    return score([synced], relay)


def s3_late_release(relay_mode, anchor_nodes=False, f=60):
    """Bridge waited K = 501. The majority attacker releases a heavier chain later (honest 600 above
    the fork, attacker 900). Synced nodes refuse it. Three fresh nodes bootstrap afterwards:
    F1 hears honest first and finishes, F2 hears only the attacker (eclipse), F3 hears the
    attacker while it has synced 300 honest blocks past the fork."""
    k = CAP + 1
    shared = chain(GENESIS, BASE)
    fork = shared[-1]
    honest_c = chain(fork, 600, deposit_at=1)
    att = chain(fork, 900)
    synced = Node("synced", k=k, anchor_aware=anchor_nodes)
    relay = Relay(relay_mode, k=k, f=f)
    feed([synced, relay], shared + honest_c)
    if relay_mode == "anchor":
        synced.learn_anchors(relay.anchor_log)
    feed([synced, relay], att)
    fresh = []
    for name, order in (("F1", shared + honest_c + att),
                        ("F2", shared + att),
                        ("F3", shared + honest_c[:300] + att + honest_c[300:])):
        n = Node(name, k=k, anchor_aware=anchor_nodes)
        if relay_mode == "anchor":
            n.anchors = dict(relay.anchor_log)     # read from Ethereum before syncing
        feed([n], order)
        if anchor_nodes and n.deposit_conf() == 0:
            feed([n], shared + honest_c)           # anchor tells it which branch to fetch
        fresh.append(n)
    return score([synced] + fresh, relay)


def s4_partition(p_len, q_len, relay_side="P", anchors=False, f=60):
    """Two honest groups split after BASE. The deposit is in group P. P mines p_len, Q mines q_len.
    The relay sees only `relay_side` during the split. Then connectivity returns."""
    k = CAP + 1
    shared = chain(GENESIS, BASE)
    fork = shared[-1]
    pc = chain(fork, p_len, deposit_at=1)
    qc = chain(fork, q_len)
    P = Node("P", k=k, anchor_aware=anchors)
    Q = Node("Q", k=k, anchor_aware=anchors)
    relay = Relay("anchor" if anchors else "cap_mirror", k=k, f=f)
    feed([P, Q, relay], shared)
    feed([P], pc)
    feed([Q], qc)
    feed([relay], pc if relay_side == "P" else qc)
    if anchors:   # anchors come from Ethereum, reachable even while SOST p2p is partitioned
        P.learn_anchors(relay.anchor_log)
        Q.learn_anchors(relay.anchor_log)
    feed([P, Q, relay], pc + qc)        # reconnect: everyone hears both chains
    if anchors:
        for n in (P, Q):
            n.learn_anchors(relay.anchor_log)
    fresh = Node("fresh", k=k, anchor_aware=anchors)
    if anchors:
        fresh.anchors = dict(relay.anchor_log)
    feed([fresh], shared + qc + pc)     # a fresh node that happens to hear Q first
    return score([P, Q, fresh], relay)


def s5_shallow_in_anchor_window(f=60):
    """Anchoring only covers blocks buried >= F. A majority attacker can still reorg anything newer:
    the bridge must wait K >= F (plus Ethereum finality), never less."""
    shared = chain(GENESIS, BASE)
    fork = shared[-1]
    honest_c = chain(fork, f - 10, deposit_at=1)
    att = chain(fork, f)
    relay = Relay("anchor", k=f - 20, f=f)
    n = Node("synced", k=f - 20)
    feed([n, relay], shared + honest_c)
    feed([n, relay], att)
    return score([n], relay)


def s6_attacker_posts_first(f=60):
    """Relayers are permissionless. The majority attacker posts its private chain's HEADERS to the
    relay first and withholds the BODIES from SOST p2p. The relay anchors the attacker's chain.
    An anchor-aware synced node holds the honest chain with the deposit (600 deep) and none of
    the attacker's blocks: obeying the anchors it must abandon the deposit and cannot follow."""
    k = CAP + 1
    shared = chain(GENESIS, BASE)
    fork = shared[-1]
    honest_c = chain(fork, 600, deposit_at=1)
    att = chain(fork, 900)
    relay = Relay("anchor", k=k, f=f)
    synced = Node("synced", k=k, anchor_aware=True)
    feed([relay, synced], shared)
    feed([relay], att)                 # attacker headers reach Ethereum first
    feed([synced], honest_c)
    feed([relay], honest_c)            # honest headers arrive later: lighter, conflict with anchors
    synced.learn_anchors(relay.anchor_log)
    s = score([synced], relay)
    s["synced_tip_height"] = synced.tip().height
    return s


EXPECT = []


def check(name, got, want):
    ok = got == want
    EXPECT.append(ok)
    print(f"  [{'OK ' if ok else 'BAD'}] {name}: {got}" + ("" if ok else f"   expected {want}"))


def fmt(s):
    return {k: ("YES" if v is True else "NO" if v is False else v) for k, v in s.items()}


def main():
    print(f"C708 reorg/finality simulator — CAP={CAP}, constant work per block\n")
    print("S1 synced node vs heavier private chain, by depth d = disconnect_count")
    for d in (499, 500, 501):
        check(f"d={d} deposit erased on the synced node", s1_depth_sweep(d), d <= CAP)

    print("\nS2 majority attacker withholds and releases at the last reorgable moment (relay cap_mirror)")
    for k in (499, 500, 501):
        s = s2_mint_race(k)
        check(f"K={k} release d={CAP}: minted={s['minted']} BRIDGE_BACKING_SAFETY", s["BRIDGE_BACKING_SAFETY"],
              "N/A" if k > CAP else False)
    print("  K=501, the attacker picks its release point d:")
    for d in (499, 500, 501, 505, 700):
        s = s2_mint_race(CAP + 1, d)
        want = "N/A" if d < CAP + 1 else True
        check(f"K=501 d={d}: minted={s['minted']} BACKING on synced nodes", s["BRIDGE_BACKING_SAFETY"], want)
    print("  (synced nodes only: S3 shows the same mint is unbacked for fresh nodes)")

    print("\nS3 K=501, attacker releases a heavier chain later; fresh nodes bootstrap afterwards")
    s = s3_late_release("most_work")
    print("  relay most_work :", fmt(s))
    check("most_work: backing broken (relay follows the attacker)", s["BRIDGE_BACKING_SAFETY"], False)
    s = s3_late_release("cap_mirror")
    print("  relay cap_mirror:", fmt(s))
    check("cap_mirror: LOCAL_NODE_SAFETY holds", s["LOCAL_NODE_SAFETY"], True)
    check("cap_mirror: NETWORK_CONVERGENCE fails (fresh F2/F3 follow the attacker)", s["NETWORK_CONVERGENCE"], False)
    check("cap_mirror: BRIDGE_BACKING_SAFETY fails (deposit absent for part of the economy)", s["BRIDGE_BACKING_SAFETY"], False)
    check("cap_mirror: conflict detected -> automatic freeze", s["frozen"], True)
    s = s3_late_release("anchor", anchor_nodes=True)
    print("  relay anchor + anchor-aware nodes:", fmt(s))
    check("anchor: NETWORK_CONVERGENCE holds", s["NETWORK_CONVERGENCE"], True)
    check("anchor: BRIDGE_BACKING_SAFETY holds", s["BRIDGE_BACKING_SAFETY"], True)

    print("\nS4 honest partition, deposit in P, relay sees one side")
    for (pl, ql, side, want_conv) in ((300, 200, "P", True), (900, 600, "P", False), (600, 900, "P", False)):
        s = s4_partition(pl, ql, side)
        print(f"  P={pl} Q={ql} relay on {side}:", fmt(s))
        check(f"P={pl} Q={ql}: NETWORK_CONVERGENCE", s["NETWORK_CONVERGENCE"], want_conv)
    s = s4_partition(600, 900, "P", anchors=True)
    print("  P=600 Q=900 relay on P, ANCHOR:", fmt(s))
    check("anchor: partition reconverges on the anchored side without lifting the cap for anyone else",
          s["NETWORK_CONVERGENCE"], True)
    check("anchor: BRIDGE_BACKING_SAFETY holds", s["BRIDGE_BACKING_SAFETY"], True)

    print("\nS5 anchoring leaves a shallow window: K < F is unsafe even with anchors")
    s = s5_shallow_in_anchor_window()
    print("  ", fmt(s))
    check("K < F: BRIDGE_BACKING_SAFETY fails", s["BRIDGE_BACKING_SAFETY"], False)

    print("\nS6 attacker posts its private headers to the relay first, withholds bodies (anchor relay)")
    s = s6_attacker_posts_first()
    print("  ", fmt(s))
    check("anchoring breaks LOCAL_NODE_SAFETY of a node 600 blocks deep", s["LOCAL_NODE_SAFETY"], False)
    check("anchor-aware node is truncated to the fork point and cannot follow (halt)",
          s["synced_tip_height"], BASE)

    bad = EXPECT.count(False)
    print(f"\nRESULT: {len(EXPECT) - bad}/{len(EXPECT)} expected outcomes reproduced")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
