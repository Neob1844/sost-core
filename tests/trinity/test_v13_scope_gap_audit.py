"""Tests for scripts/trinity/v13_scope_gap_audit.py.

Three layers:

1. Functional — the auditor runs against the real /opt/sost tree
   and reports all_green=True (every doc present with all
   load-bearing tokens AND every source-side fact matches the
   doc's claims). If this fails on main, either a doc has been
   weakened or a gate has actually closed (good news, update
   the doc).

2. Negative — synthetic fake trees that break each token check
   and each source-side fact check; the auditor must flag them.

3. Static safety — auditor source contains no forbidden token
   (no subprocess, no network, no wallet, no signing, no
   GitHub API, etc.).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    REPO_ROOT / "scripts" / "trinity" / "v13_scope_gap_audit.py"
)


def _import_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "v13_scope_gap_audit", str(SCRIPT),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def aud():
    return _import_script()


# ---------------------------------------------------------------------------
# 1) Functional — live tree
# ---------------------------------------------------------------------------


def test_audit_runs_clean_on_live_tree(aud):
    r = aud.build_audit(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T20:00:00+00:00",
    )
    assert r["schema"] == "trinity-v13-scope-gap-audit/v0.1"
    assert r["all_green"] is True, (
        "V13 scope gap audit is NOT all-green on the live tree.\n"
        "docs:    " + json.dumps([d for d in r["docs"]
                                  if not d["ok"]], indent=2) + "\n"
        "facts:   " + json.dumps({k: v for k, v in
                                  r["source_facts"].items()
                                  if not v["as_documented"]},
                                 indent=2)
    )
    for k, v in r["safety_flags"].items():
        assert v is True, "safety flag false: " + k


def test_each_required_doc_present_and_complete(aud):
    r = aud.build_audit(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T20:00:00+00:00",
    )
    by_path = {d["path"]: d for d in r["docs"]}
    for required in (
        "docs/V13_POPC_ESCROW_AUTO_ACTIVATION_GAPS.md",
        "docs/V13_GOLD_VAULT_GOVERNANCE_GATES.md",
        "docs/V13_BEACON_II_B_III_GAPS.md",
    ):
        assert required in by_path
        d = by_path[required]
        assert d["found"] is True, "missing doc: " + required
        assert d["all_tokens_present"] is True, (
            required + " missing tokens: "
            + repr(d["missing_tokens"])
        )


def test_source_facts_match_documentation(aud):
    r = aud.build_audit(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T20:00:00+00:00",
    )
    f = r["source_facts"]
    assert f["popc_activation_height_missing"]["as_documented"] is True
    assert f["gold_vault_address_pinned"]["as_documented"] is True
    assert f["classify_gv_spend_is_dead_code"]["as_documented"] is True
    assert f["bip9_signaling_primitives_exist"]["as_documented"] is True
    assert f["beacon_phase2a_gate_at_v13"]["as_documented"] is True
    assert f["beacon_p2p_gate_sentinel"]["as_documented"] is True
    assert f["test_gold_vault_count"]["as_documented"] is True
    assert f["test_phase2a_present"]["as_documented"] is True


def test_cli_returns_0_on_live_tree(aud, tmp_path):
    rc = aud.main([
        "--repo-root",   str(REPO_ROOT),
        "--out-json",    str(tmp_path / "audit.json"),
        "--out-md",      str(tmp_path / "audit.md"),
        "--pinned-time", "2026-05-18T20:00:00+00:00",
    ])
    assert rc == 0
    js = json.loads(
        (tmp_path / "audit.json").read_text(encoding="utf-8")
    )
    assert js["all_green"] is True
    md = (tmp_path / "audit.md").read_text(encoding="utf-8")
    assert "# V13 Scope Gap Audit" in md


def test_audit_id_deterministic(aud):
    a1 = aud.build_audit(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T20:00:00+00:00",
    )
    a2 = aud.build_audit(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T20:00:00+00:00",
    )
    assert a1["audit_id"] == a2["audit_id"]
    assert re.match(r"^v13gapaudit-[0-9a-f]{16}$", a1["audit_id"])


# ---------------------------------------------------------------------------
# 2) Negative — synthetic fake repos
# ---------------------------------------------------------------------------


def _make_minimal_fake_repo(tmp_path: Path) -> Path:
    """Build the smallest tree that the live-tree shape requires:
    include/sost/params.h, src/tx_validation.cpp, src/block_validation.cpp,
    include/sost/proposals.h, tests/test_gold_vault.cpp,
    tests/test_v13_beacon_phase2a.cpp, plus the three doc files.
    Every file matches the docs' claims so the audit comes up green
    before we tamper with one piece at a time."""
    rr = tmp_path / "fake"
    (rr / "include" / "sost").mkdir(parents=True)
    (rr / "src").mkdir(parents=True)
    (rr / "tests").mkdir(parents=True)
    (rr / "docs").mkdir(parents=True)

    (rr / "include" / "sost" / "params.h").write_text(
        "inline constexpr int64_t V13_HEIGHT = 12000;\n"
        "inline constexpr int64_t BEACON_PHASE2A_ACTIVATION_HEIGHT "
        "= V13_HEIGHT;\n"
        "inline constexpr int64_t BEACON_P2P_ACTIVATION_HEIGHT "
        "= INT64_MAX;\n"
        "constexpr char ADDR_GOLD_VAULT[] = \"sost1xxx\";\n",
        encoding="utf-8",
    )
    (rr / "src" / "tx_validation.cpp").write_text(
        "// no classify_gv_spend call here\n", encoding="utf-8")
    (rr / "src" / "block_validation.cpp").write_text(
        "// nothing\n", encoding="utf-8")
    (rr / "include" / "sost" / "proposals.h").write_text(
        "inline bool version_has_signal(int v, int b){return 0;}\n"
        "inline int count_version_signals(){return 0;}\n",
        encoding="utf-8",
    )
    (rr / "tests" / "test_gold_vault.cpp").write_text(
        "// " + "\n// ".join(
            "GV{:02d}_synthetic".format(i) for i in range(1, 18)
        ) + "\n",
        encoding="utf-8",
    )
    (rr / "tests" / "test_v13_beacon_phase2a.cpp").write_text(
        "void test_commands_must_be_empty(){}\n",
        encoding="utf-8",
    )

    # Write the three docs with all required tokens present.
    for rel, toks in {
        "docs/V13_POPC_ESCROW_AUTO_ACTIVATION_GAPS.md": [
            "POPC_ACTIVATION_HEIGHT", "12,000", "V14", "15,000",
            "Memory-Lock", "DEFERRED",
            "G-POPC-1", "G-POPC-2", "G-POPC-3", "G-POPC-4",
            "G-POPC-5", "G-POPC-6", "G-POPC-7", "G-POPC-8",
            "G-POPC-9", "SOSTEscrow.sol",
        ],
        "docs/V13_GOLD_VAULT_GOVERNANCE_GATES.md": [
            "12,000", "V14", "15,000",
            "67", "61", "90 %",
            "75 % → 95 % → 90 %",
            "Guardian", "10 blocks", "25,000",
            "G1", "G2", "G3", "G4", "G5", "G6",
            "ADDR_GOLD_VAULT", "classify_gv_spend",
            "Heritage Reserve", "Zodiac", "Reality.eth",
            "Sepolia",
        ],
        "docs/V13_BEACON_II_B_III_GAPS.md": [
            "12,000", "V14", "15,000",
            "Phase II-A", "Phase II-B", "Phase III",
            "BEACON_PHASE2A_ACTIVATION_HEIGHT",
            "BEACON_P2P_ACTIVATION_HEIGHT",
            "INT64_MAX", "DiscardDormant",
            "ECDSA", "Memory-Lock",
        ],
    }.items():
        (rr / rel).write_text(" ".join(toks) + "\n", encoding="utf-8")

    return rr


def test_negative_missing_doc(aud, tmp_path):
    rr = _make_minimal_fake_repo(tmp_path)
    (rr / "docs" / "V13_POPC_ESCROW_AUTO_ACTIVATION_GAPS.md").unlink()
    r = aud.build_audit(repo_root=rr,
                        pinned_time="2026-05-18T20:00:00+00:00")
    assert r["all_docs_ok"] is False
    assert r["all_green"] is False


def test_negative_missing_token_in_doc(aud, tmp_path):
    rr = _make_minimal_fake_repo(tmp_path)
    p = rr / "docs" / "V13_GOLD_VAULT_GOVERNANCE_GATES.md"
    txt = p.read_text(encoding="utf-8").replace("Guardian", "guard")
    p.write_text(txt, encoding="utf-8")
    r = aud.build_audit(repo_root=rr,
                        pinned_time="2026-05-18T20:00:00+00:00")
    by_path = {d["path"]: d for d in r["docs"]}
    d = by_path["docs/V13_GOLD_VAULT_GOVERNANCE_GATES.md"]
    assert "Guardian" in d["missing_tokens"]
    assert r["all_green"] is False


def test_negative_classify_gv_spend_appears_in_src(aud, tmp_path):
    """If the operator wires classify_gv_spend into tx_validation.cpp,
    the audit flips that fact and reports 'gap closing'. That's good
    news, but the audit must detect it so the doc gets updated."""
    rr = _make_minimal_fake_repo(tmp_path)
    (rr / "src" / "tx_validation.cpp").write_text(
        "bool f() { return classify_gv_spend() == 1; }\n",
        encoding="utf-8",
    )
    r = aud.build_audit(repo_root=rr,
                        pinned_time="2026-05-18T20:00:00+00:00")
    assert (r["source_facts"]
            ["classify_gv_spend_is_dead_code"]
            ["as_documented"]) is False
    assert r["all_green"] is False


def test_negative_popc_activation_height_appears(aud, tmp_path):
    """If the operator adds POPC_ACTIVATION_HEIGHT to params.h,
    the audit flips that fact and reports 'gap closing'."""
    rr = _make_minimal_fake_repo(tmp_path)
    p = rr / "include" / "sost" / "params.h"
    p.write_text(
        p.read_text(encoding="utf-8")
        + "\ninline constexpr int64_t POPC_ACTIVATION_HEIGHT = 12000;\n",
        encoding="utf-8",
    )
    r = aud.build_audit(repo_root=rr,
                        pinned_time="2026-05-18T20:00:00+00:00")
    assert (r["source_facts"]
            ["popc_activation_height_missing"]
            ["as_documented"]) is False


def test_negative_beacon_phase2a_gate_regressed(aud, tmp_path):
    """If BEACON_PHASE2A_ACTIVATION_HEIGHT stops being V13_HEIGHT,
    the audit detects a real regression."""
    rr = _make_minimal_fake_repo(tmp_path)
    p = rr / "include" / "sost" / "params.h"
    p.write_text(
        p.read_text(encoding="utf-8").replace(
            "BEACON_PHASE2A_ACTIVATION_HEIGHT = V13_HEIGHT",
            "BEACON_PHASE2A_ACTIVATION_HEIGHT = INT64_MAX",
        ),
        encoding="utf-8",
    )
    r = aud.build_audit(repo_root=rr,
                        pinned_time="2026-05-18T20:00:00+00:00")
    assert (r["source_facts"]
            ["beacon_phase2a_gate_at_v13"]
            ["as_documented"]) is False
    assert r["all_green"] is False


# ---------------------------------------------------------------------------
# 3) Static safety
# ---------------------------------------------------------------------------


_FORBIDDEN_TOKENS = (
    "shell=True", "shell = True",
    "os.system(", "os.popen(",
    "eval(", "exec(",
    "import requests", "from requests",
    "import urllib", "from urllib",
    "urlopen(", "urllib.request",
    "requests.post(", "requests.get(",
    "import httpx", "from httpx", "httpx.",
    "import aiohttp", "from aiohttp", "aiohttp.",
    "socket.socket(", "socket.create_connection(",
    "http.client.HTTPConnection",
    "api.github.com", "GITHUB_TOKEN", "X-GitHub-",
    "import github", "from github", "PyGithub",
    "ecdsa", "secp256k1",
    "sign_tx", "sign_transaction", "wallet.sign", "real_sign",
    "sendrawtransaction(", "broadcast(",
    "privkey", "private_key_hex",
    "anthropic", "openai", "langchain", "transformers", "llama_cpp",
    "web3.", "from web3", "import web3",
    "etherscan.io", "infura.io", "alchemy.com",
    "ETHERSCAN_API_KEY", "deploy_contract", "send_transaction",
    "import subprocess", "from subprocess", "subprocess.",
    "upload_release(",
    'subprocess.run(["gpg', "subprocess.run(['gpg",
)


_FORBIDDEN_GIT = (
    '"push"', "'push'",
    '"merge"', "'merge'",
    '"tag"', "'tag'",
    '"reset"', "'reset'",
    '"checkout"', "'checkout'",
    '"rm"', "'rm'",
    '"clean"', "'clean'",
    '"commit"', "'commit'",
    '"add"', "'add'",
    '"stash"', "'stash'",
    '"git"', "'git'",
)


def test_no_forbidden_tokens():
    src = SCRIPT.read_text(encoding="utf-8")
    found = [t for t in _FORBIDDEN_TOKENS if t in src]
    assert not found, (
        "v13_scope_gap_audit.py contains forbidden token(s): "
        + repr(found)
    )


def test_no_destructive_git_invocations():
    src = SCRIPT.read_text(encoding="utf-8")
    found = [t for t in _FORBIDDEN_GIT if t in src]
    assert not found, (
        "v13_scope_gap_audit.py contains forbidden git argv "
        "literal(s): " + repr(found)
    )


def test_no_url_strings():
    src = SCRIPT.read_text(encoding="utf-8")
    urls = re.findall(r"https?://[a-zA-Z0-9._/-]+", src)
    assert not urls, (
        "v13_scope_gap_audit.py must contain no URLs; found: "
        + repr(urls)
    )
