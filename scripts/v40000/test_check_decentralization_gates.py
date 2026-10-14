#!/usr/bin/env python3
"""Unit tests for check_decentralization_gates.py. Fixtures only, no network.

Run: python3 -I scripts/v40000/test_check_decentralization_gates.py
"""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
FIX = os.path.join(HERE, "fixtures")
sys.path.insert(0, HERE)

import check_decentralization_gates as cdg  # noqa: E402


def load(name):
    with open(os.path.join(FIX, name), "r", encoding="utf-8") as f:
        return json.load(f)


def synth_blocks(n, shares, start=30000):
    """shares: list of (address, count) repeated round-robin to n blocks."""
    seq = []
    for addr, cnt in shares:
        seq += [addr] * cnt
    return [{"height": start + i, "miner_address": seq[i % len(seq)]} for i in range(n)]


class Net16(unittest.TestCase):
    def test_masked(self):
        self.assertEqual(cdg.net16_of("203.0.xxx.xxx:19333"), "203.0.0.0/16")

    def test_unmasked(self):
        self.assertEqual(cdg.net16_of("198.51.100.7:19333"), "198.51.0.0/16")

    def test_no_port(self):
        self.assertEqual(cdg.net16_of("10.1.xxx.xxx"), "10.1.0.0/16")

    def test_hostname_is_none(self):
        # mask_addr applied to a DNS seed entry yields this shape
        self.assertIsNone(cdg.net16_of("seed-eu.sostcore.xxx.xxx:19333"))

    def test_out_of_range_octet(self):
        self.assertIsNone(cdg.net16_of("300.1.xxx.xxx:1"))

    def test_garbage(self):
        self.assertIsNone(cdg.net16_of(""))
        self.assertIsNone(cdg.net16_of("::1"))


class Peers(unittest.TestCase):
    def setUp(self):
        self.pi = load("getpeerinfo.json")
        self.amap = cdg.load_asn_map(load("asn_map.json"))

    def test_counts(self):
        r = cdg.measure_peers(self.pi)
        self.assertEqual(r["total"], 4)
        self.assertEqual(r["outbound"], 2)
        self.assertEqual(r["inbound"], 2)
        self.assertEqual(r["version_acked"], 3)
        self.assertEqual(r["non_ip_addrs"], 1)
        self.assertEqual(r["distinct_16"], 2)
        self.assertAlmostEqual(r["largest_16_share"], 2 / 3)
        self.assertNotIn("distinct_asns", r)

    def test_asn_mapping(self):
        r = cdg.measure_peers(self.pi, self.amap)
        self.assertEqual(r["distinct_asns"], 2)
        self.assertEqual(r["providers"], ["ExampleHost-A", "ExampleHost-B"])
        self.assertEqual(r["regions"], ["EU", "NA"])
        self.assertEqual(r["unmapped"], 0)

    def test_ambiguous_16(self):
        # 192.0.0.0/16 overlaps two entries with different ASNs -> ambiguous, not counted
        r = cdg.measure_peers([{"addr": "192.0.xxx.xxx:19333", "direction": "outbound"}], self.amap)
        self.assertEqual(r["ambiguous"], 1)
        self.assertEqual(r["distinct_asns"], 0)

    def test_unmapped(self):
        r = cdg.measure_peers([{"addr": "100.64.xxx.xxx:19333", "direction": "outbound"}], self.amap)
        self.assertEqual(r["unmapped"], 1)

    def test_peer_provenance_fields(self):
        r = cdg.measure_peers([
            {"addr": "seed-eu.sostcore.xxx.xxx:19333", "direction": "outbound", "source": "dns", "subnet16": "212.132"},
            {"addr": "203.0.xxx.xxx:19333", "direction": "outbound", "source": "gossip", "subnet16": "203.0"},
            {"addr": "198.51.xxx.xxx:40000", "direction": "inbound"},
        ])
        self.assertEqual(r["non_ip_addrs"], 0)
        self.assertEqual(r["distinct_16"], 3)
        self.assertEqual(r["provenance_reported"], 2)
        self.assertEqual(r["by_source"], {"dns": 1, "gossip": 1})

    def test_empty(self):
        r = cdg.measure_peers([])
        self.assertEqual(r["total"], 0)
        self.assertIsNone(r["largest_16_share"])


class Producers(unittest.TestCase):
    def test_fixture(self):
        r = cdg.measure_producers(load("blocks.json"))
        self.assertEqual(r["blocks"], 20)
        self.assertEqual(r["distinct_producers"], 3)
        self.assertEqual(r["top_producer"], "sost1aaaa")
        self.assertAlmostEqual(r["top_share"], 0.70)
        self.assertEqual((r["from_height"], r["to_height"]), (30400, 30419))

    def test_merge_groups_entities(self):
        r = cdg.measure_producers(load("blocks.json"), {"sost1bbbb": "E1", "sost1cccc": "E1"})
        self.assertEqual(r["distinct_producers"], 2)
        self.assertEqual(r["counts"]["E1"], 6)

    def test_pubkey_fallback_and_unknown(self):
        r = cdg.measure_producers([{"height": 1, "miner_pubkey": "02ab"}, {"height": 2}])
        self.assertEqual(r["counts"], {"02ab": 1, "UNKNOWN": 1})
        self.assertEqual(r["unknown_producer_blocks"], 1)

    def test_g7_short_window_not_measured(self):
        g = cdg.evaluate(None, cdg.measure_producers(load("blocks.json")), None)
        self.assertEqual(g["G7_PRODUCERS"]["status"], "NOT_MEASURED")

    def test_g7_current_like_fails(self):
        # 2 producers, top 68.8 % (the recorded V16 window shape)
        b = synth_blocks(2016, [("A", 688), ("B", 312)])
        g = cdg.evaluate(None, cdg.measure_producers(b), None)
        self.assertEqual(g["G7_PRODUCERS"]["status"], "NOT_MET")

    def test_g7_pass(self):
        b = synth_blocks(2016, [("A", 40), ("B", 20), ("C", 15), ("D", 15), ("E", 10)])
        g = cdg.evaluate(None, cdg.measure_producers(b), None)
        self.assertEqual(g["G7_PRODUCERS"]["status"], "MET")

    def test_g7_top_exactly_half_fails(self):
        b = synth_blocks(2016, [("A", 5), ("B", 2), ("C", 1), ("D", 1), ("E", 1)])
        g = cdg.evaluate(None, cdg.measure_producers(b), None)
        self.assertEqual(g["G7_PRODUCERS"]["status"], "NOT_MET")

    def test_fetch_blocks_uses_only_readonly_calls(self):
        calls = []
        chain = {h: {"height": h, "miner_address": "A"} for h in range(0, 11)}

        def fake(method, *params):
            calls.append(method)
            if method == "getblockcount":
                return 10
            if method == "getblockhash":
                return "h%d" % params[0]
            if method == "getblock":
                return chain[int(params[0][1:])]
            raise AssertionError(method)

        got = cdg.fetch_blocks(fake, 3)
        self.assertEqual([b["height"] for b in got], [8, 9, 10])
        self.assertEqual(set(calls), {"getblockcount", "getblockhash", "getblock"})


class Seeds(unittest.TestCase):
    def test_parse_snippet(self):
        src = ('static const char* const DEFAULT_SEEDS[] = {\n  "a.sostcore.com",\n'
               '  "b.example.org", // "c.commented.out"\n};')
        self.assertEqual(cdg.parse_default_seeds(src), ["a.sostcore.com", "b.example.org"])

    def test_parse_none(self):
        self.assertEqual(cdg.parse_default_seeds("int x;"), [])

    def test_real_source_current_state(self):
        # Records the tree as audited: 4 compiled-in seeds, all under sostcore.com.
        path = os.path.join(REPO, "src", "sost-node.cpp")
        if not os.path.exists(path):
            self.skipTest("source not present")
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            ds = cdg.parse_default_seeds(f.read())
        self.assertEqual(len(ds), 4)
        r = cdg.measure_seeds(ds)
        self.assertEqual(r["default_seeds_project_domain"], 4)
        g = cdg.evaluate(None, None, r)
        self.assertEqual(g["G4_INDEPENDENT_SEEDS"]["status"], "NOT_MET")

    def test_domain_match(self):
        self.assertTrue(cdg.under_project_domain("seed.sostcore.com"))
        self.assertTrue(cdg.under_project_domain("SOSTCORE.COM."))
        self.assertFalse(cdg.under_project_domain("notsostcore.com"))
        self.assertFalse(cdg.under_project_domain("sostcore.com.evil.org"))

    def test_registry_rules(self):
        r = cdg.measure_seeds(["seed-eu.sostcore.com"], load("seed_registry.json"))
        self.assertEqual(r["independent_seeds"], 2)
        self.assertEqual(r["independent_hosts"], ["seed.example-a.org:19333", "198.51.100.20:19333"])
        reasons = {x["host"]: x["reason"] for x in r["rejected"]}
        self.assertEqual(reasons["seed-eu.sostcore.com"], "project domain")
        self.assertEqual(reasons["seed.example-c.net"], "ASN already counted")
        self.assertEqual(reasons["seed.example-d.net"], "no evidence")
        self.assertEqual(reasons["seed.example-e.net"], "operator already counted")
        g = cdg.evaluate(None, None, r)
        self.assertEqual(g["G4_INDEPENDENT_SEEDS"]["status"], "NOT_MET")

    def test_registry_three_pass(self):
        reg = {"project": {"operator": "p", "asns": ["1"]}, "seeds": [
            {"host": "a.org", "operator": "x", "asn": "2", "evidence": "e"},
            {"host": "b.org", "operator": "y", "asn": "3", "evidence": "e"},
            {"host": "c.org", "operator": "z", "asn": "4", "evidence": "e"}]}
        g = cdg.evaluate(None, None, cdg.measure_seeds([], reg))
        self.assertEqual(g["G4_INDEPENDENT_SEEDS"]["status"], "MET")


class GatesAndCli(unittest.TestCase):
    def test_connectivity_fixture_fails(self):
        g = cdg.evaluate(cdg.measure_peers(load("getpeerinfo.json")), None, None)
        self.assertEqual(g["PEER_CONNECTIVITY"]["status"], "NOT_MET")
        self.assertEqual(g["G6_PEER_VIEW_ASN_REGION"]["status"], "NOT_MEASURED")

    def test_g6_peer_view_pass_is_labelled_insufficient(self):
        peers = [{"addr": a, "direction": "outbound"} for a in
                 ("203.0.xxx.xxx:1", "198.51.xxx.xxx:1", "192.0.xxx.xxx:1")]
        amap = cdg.load_asn_map([
            {"prefix": "203.0.0.0/16", "asn": 1, "region": "EU"},
            {"prefix": "198.51.0.0/16", "asn": 2, "region": "NA"},
            {"prefix": "192.0.0.0/16", "asn": 3, "region": "APAC"}])
        g = cdg.evaluate(cdg.measure_peers(peers, amap), None, None)
        self.assertEqual(g["G6_PEER_VIEW_ASN_REGION"]["status"], "MET")
        self.assertIn("NOT sufficient", g["G6_PEER_VIEW_ASN_REGION"]["detail"])
        self.assertEqual(g["PEER_CONNECTIVITY"]["status"], "MET")

    def test_summary(self):
        self.assertEqual(cdg.summarize({}), "NOT_MEASURED")
        self.assertEqual(cdg.summarize({"a": {"met": True}, "b": {"met": None}}), "INCOMPLETE")
        self.assertEqual(cdg.summarize({"a": {"met": True}, "b": {"met": False}}), "NO")
        self.assertEqual(cdg.summarize({"a": {"met": True}}), "YES")

    def test_cli_fixture_mode_strict(self):
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "r.json")
            buf, err = io.StringIO(), io.StringIO()
            with redirect_stdout(buf), redirect_stderr(err):
                rc = cdg.main(["--fixture-dir", FIX, "--asn-map", os.path.join(FIX, "asn_map.json"),
                               "--source", os.path.join(REPO, "src", "sost-node.cpp"),
                               "--seed-registry", os.path.join(FIX, "seed_registry.json"),
                               "--json-out", out, "--strict"])
            self.assertEqual(rc, 1)
            with open(out) as f:
                rep = json.load(f)
            self.assertEqual(rep["DECENTRALIZATION_GATES_MET_MEASURABLE_SUBSET"], "NO")
            self.assertEqual(rep["peers"]["total"], 4)
            self.assertIn("MEASURABLE SUBSET: NO", buf.getvalue())

    def test_password_file_must_be_private(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "pw")
            with open(p, "w") as f:
                f.write("secret\n")
            os.chmod(p, 0o644)
            with self.assertRaises(cdg.RpcError):
                cdg.read_password_file(p)
            os.chmod(p, 0o600)
            self.assertEqual(cdg.read_password_file(p), "secret")

    def test_run_with_fake_rpc(self):
        def fake(method, *params):
            if method == "getpeerinfo":
                return load("getpeerinfo.json")
            if method == "getblockcount":
                return 4
            if method == "getblockhash":
                return str(params[0])
            if method == "getblock":
                return {"height": int(params[0]), "miner_address": "A"}
            raise AssertionError(method)
        args = cdg.build_parser().parse_args(["--last", "5"])
        rep = cdg.run(args, fake)
        self.assertEqual(rep["producers"]["blocks"], 5)
        self.assertEqual(rep["peers"]["outbound"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=1)
