"""Stage 1 governance tests: census freeze, on-chain votes, 2/3-of-full-census rule, finality, reorgs."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "ops"))

from sostbridge.common import build_open_note
from sostbridge.sostchain import FakeSostChain
from sostbridge.governance import (Proposal, EligibilityRules, ParticipantRecord, freeze_census, is_eligible,
                                   tally, required_yes, OPEN, CLOSED_FINALITY_PENDING, FINAL_PASS, FINAL_FAIL,
                                   gov_result_tuple)

SNAP, CLOSE, DEPTH = 100, 140, 10
IDS = ["sost1" + format(i, "040x") for i in range(1, 13)]   # 12 eligible identities
OUTSIDER = "sost1" + "f" * 40


def prop(**kw):
    base = dict(proposal_id="GRV2-004", source_vault="0x" + "11" * 20, source_asset="0x" + "22" * 20,
                successor_vault="0x" + "33" * 20, successor_asset="0x" + "44" * 20, successor_code_hash=b"\x55" * 32,
                snapshot_height=SNAP, close_height=CLOSE, timelock=7 * 86400, reason="XAUT protocol migration")
    base.update(kw)
    return Proposal(**base)


def vote_tx(voter, choice, tag, text=None, spender=None):
    t = text if text is not None else f"SOSTGOV1|GRV2-004|S{SNAP}|{choice}"
    return {"txid": FakeSostChain.txid_for(tag), "vin": [{"address": spender or voter, "amount": "0.01"}],
            "vout": [{"address": voter, "amount": "0.001", "payload_hex": build_open_note(t)}]}


def chain_to(h):
    c = FakeSostChain()
    c.mine(h)
    return c


def votes(c, pairs, start_tag="v"):
    c.add_block([vote_tx(v, ch, f"{start_tag}{i}") for i, (v, ch) in enumerate(pairs)])


def test_required_yes():
    assert [required_yes(n) for n in (1, 2, 3, 4, 12, 13)] == [1, 2, 2, 3, 8, 9]


def test_8_of_12_pass_and_final_tuple():
    c = chain_to(SNAP + 1)
    votes(c, [(IDS[i], "YES") for i in range(8)] + [(IDS[8], "NO"), (IDS[9], "NO")])
    c.mine(CLOSE + DEPTH - c.getblockcount())
    t = tally(c, prop(), IDS, DEPTH)
    assert (t.yes, t.no, t.abstain, t.no_vote, t.required_yes) == (8, 2, 0, 2, 8)
    assert t.state == FINAL_PASS and t.passed
    g = gov_result_tuple(t)
    assert g[1] == 12 and g[2] == 8 and g[5] == CLOSE + DEPTH


def test_7_of_12_fails_even_if_all_voters_say_yes():
    c = chain_to(SNAP + 1)
    votes(c, [(IDS[i], "YES") for i in range(7)])
    c.mine(CLOSE + DEPTH - c.getblockcount())
    t = tally(c, prop(), IDS, DEPTH)
    assert t.yes == 7 and t.no_vote == 5 and t.state == FINAL_FAIL


def test_8_yes_4_abstain_passes_abstain_not_yes():
    c = chain_to(SNAP + 1)
    votes(c, [(IDS[i], "YES") for i in range(8)] + [(IDS[i], "ABSTAIN") for i in range(8, 12)])
    c.mine(CLOSE + DEPTH - c.getblockcount())
    t = tally(c, prop(), IDS, DEPTH)
    assert (t.yes, t.abstain) == (8, 4) and t.state == FINAL_PASS
    c2 = chain_to(SNAP + 1)
    votes(c2, [(IDS[i], "YES") for i in range(7)] + [(IDS[i], "ABSTAIN") for i in range(7, 12)])
    c2.mine(CLOSE + DEPTH - c2.getblockcount())
    assert tally(c2, prop(), IDS, DEPTH).state == FINAL_FAIL


def test_changed_vote_last_wins_history_kept():
    c = chain_to(SNAP + 1)
    votes(c, [(IDS[0], "YES")], "a")
    c.mine(5)
    votes(c, [(IDS[0], "NO")], "b")
    t = tally(c, prop(), IDS, DEPTH)
    assert t.final_votes[IDS[0]] == "NO"
    assert [h["choice"] for h in t.history] == ["YES", "NO"]


def test_duplicate_same_vote_counted_once():
    c = chain_to(SNAP + 1)
    votes(c, [(IDS[0], "YES"), (IDS[0], "YES")], "d")
    assert tally(c, prop(), IDS, DEPTH).yes == 1


def test_ineligible_and_malformed_and_wrong_fields_ignored():
    c = chain_to(SNAP + 1)
    c.add_block([
        vote_tx(OUTSIDER, "YES", "o"),                                               # not in census
        vote_tx(IDS[1], "YES", "m", text="SOSTGOV1|GRV2-004|S100|MAYBE"),             # malformed
        vote_tx(IDS[2], "YES", "s", text="SOSTGOV1|GRV2-004|S99|YES"),                # wrong snapshot
        vote_tx(IDS[3], "YES", "p", text="SOSTGOV1|GRV2-005|S100|YES"),               # wrong proposal
        vote_tx(IDS[4], "YES", "x", spender=OUTSIDER),                                # does not spend from identity
        vote_tx(IDS[5], "YES", "u", text="hello world"),                               # unrelated capsule
    ])
    t = tally(c, prop(), IDS, DEPTH)
    assert t.yes == 0
    whys = sorted(i["why"] for i in t.ignored)
    assert len(t.ignored) == 5                                  # the unrelated capsule is not even a vote
    assert "voter not in the snapshot census" in whys and "malformed vote capsule" in whys


def test_vote_at_snapshot_or_after_close_not_counted():
    c = chain_to(SNAP - 1)
    votes(c, [(IDS[0], "YES")], "pre")                          # at the snapshot height: too early
    c.mine(CLOSE - c.getblockcount())
    votes(c, [(IDS[1], "YES")], "late")                         # after the close
    c.mine(DEPTH)
    t = tally(c, prop(), IDS, DEPTH)
    assert t.yes == 0


def test_finality_states():
    c = chain_to(SNAP + 1)
    votes(c, [(IDS[i], "YES") for i in range(8)])
    assert tally(c, prop(), IDS, DEPTH).state == OPEN
    c.mine(CLOSE - c.getblockcount())
    assert tally(c, prop(), IDS, DEPTH).state == CLOSED_FINALITY_PENDING
    c.mine(DEPTH)
    assert tally(c, prop(), IDS, DEPTH).state == FINAL_PASS


def test_reorg_removing_final_vote_changes_result():
    c = chain_to(SNAP + 1)
    votes(c, [(IDS[i], "YES") for i in range(7)], "a")
    c.mine(CLOSE - 1 - c.getblockcount())
    votes(c, [(IDS[7], "YES")], "b")                            # the 8th YES lands at the close
    h = c.getblockcount()
    assert tally(c, prop(), IDS, DEPTH).yes == 8
    c.reorg(h, [[]] + [[] for _ in range(DEPTH)])               # reorg around the close drops it
    t = tally(c, prop(), IDS, DEPTH)
    assert t.yes == 7 and t.state == FINAL_FAIL


def test_census_freeze_rules():
    rules = EligibilityRules(min_bind_age_blocks=50)
    recs = [
        ParticipantRecord(IDS[0], 10, True, 10, True),          # eligible
        ParticipantRecord(IDS[1], 2, True, 10, True),           # too few PoW blocks
        ParticipantRecord(IDS[2], 10, False, None, True),       # no NODE_BIND
        ParticipantRecord(IDS[3], 10, True, SNAP + 5, True),    # bound AFTER the snapshot
        ParticipantRecord(IDS[4], 10, True, SNAP - 10, True),   # binding too young
        ParticipantRecord(IDS[5], 10, True, 10, False),         # heartbeats missing
    ]
    assert freeze_census(recs, SNAP, rules) == [IDS[0]]


def test_proposal_hash_commits_to_every_material_field():
    base = prop().proposal_hash()
    for k, v in dict(proposal_id="GRV2-005", source_vault="0x" + "12" * 20, successor_vault="0x" + "34" * 20,
                     successor_asset="0x" + "45" * 20, successor_code_hash=b"\x56" * 32, snapshot_height=SNAP + 1,
                     close_height=CLOSE + 1, timelock=1, reason="other").items():
        assert prop(**{k: v}).proposal_hash() != base, k
