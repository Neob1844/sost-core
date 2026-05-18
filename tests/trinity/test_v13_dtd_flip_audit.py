"""Tests for scripts/trinity/v13_dtd_flip_audit.py.

Two surfaces are exercised:

1. Functional — the auditor is run against the real /opt/sost tree
   (the live repo) and every gate must come up GREEN. If this test
   fails on main, the V11 Phase 2 cadence flip at block 12,100 has
   been weakened in consensus — that is the bug.

2. Negative — synthetic fake repo trees that violate each gate
   individually, asserting the auditor flags them as RED.

3. Static safety — the auditor source is read and checked against
   a token block-list (no subprocess, no network, no wallet, no
   signing, no gpg, no GitHub API, no Ethereum deploy).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    REPO_ROOT / "scripts" / "trinity" / "v13_dtd_flip_audit.py"
)


def _import_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "v13_dtd_flip_audit", str(SCRIPT),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def aud():
    return _import_script()


# ---------------------------------------------------------------------------
# 1) Functional — live tree must come up all-green
# ---------------------------------------------------------------------------


def test_audit_runs_clean_on_live_tree(aud, tmp_path):
    report = aud.build_audit(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T18:00:00+00:00",
    )
    assert report["schema"] == "trinity-v13-dtd-flip-audit/v0.1"
    assert report["all_green"] is True, (
        "DTD flip audit is RED on the live tree: "
        + json.dumps(report["gates"], indent=2)
    )
    assert report["safety_status"] == "ok"
    for k, v in report["safety_flags"].items():
        assert v is True, "safety flag false: " + k


def test_constants_match_expected_values(aud):
    report = aud.build_audit(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T18:00:00+00:00",
    )
    by_name = {i["name"]: i for i in report["constants"]["items"]}
    assert by_name["V11_PHASE2_HEIGHT"]["value"]        == 7100
    assert by_name["LOTTERY_HIGH_FREQ_WINDOW"]["value"] == 5000
    assert by_name["V13_HEIGHT"]["value"]               == 12000
    assert (
        by_name["LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW"]["value"]
        == 5
    )


def test_call_sites_are_all_safe(aud):
    report = aud.build_audit(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T18:00:00+00:00",
    )
    cs = report["call_sites"]
    assert cs["call_site_count"] >= 1
    for s in cs["call_sites"]:
        assert s["classification"] in ("named_const", "variable"), (
            "BAD call site: " + s["path"] + ":" + str(s["line"])
            + " second_arg=" + repr(s["second_arg"])
            + " classification=" + s["classification"]
        )


def test_miner_does_not_recompute_cadence(aud):
    report = aud.build_audit(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T18:00:00+00:00",
    )
    mi = report["miner_independence"]
    assert mi["miner_found"] is True
    assert mi["has_is_lottery_block_call"] is False
    assert mi["consumes_lottery_triggered"] is True
    assert mi["has_height_modulo_three"] is False


def test_cooldown_helper_is_decoupled(aud):
    report = aud.build_audit(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T18:00:00+00:00",
    )
    c = report["cooldown_helper"]
    assert c["helper_found"] is True
    assert c["returns_5_pre_v13"] is True
    assert c["returns_6_post_v13"] is True
    assert c["couples_to_is_lottery_block"] is False


def test_math_sanity_pattern(aud):
    report = aud.build_audit(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T18:00:00+00:00",
    )
    rows = {r["height"]: r["computed"]
            for r in report["math_sanity"]["heights"]}
    # Bootstrap final stretch.
    assert rows[12095] is True   # 12095%3=2
    assert rows[12096] is False  # 12096%3=0
    assert rows[12097] is True   # 12097%3=1
    assert rows[12098] is True   # 12098%3=2
    assert rows[12099] is False  # 12099%3=0  (LAST bootstrap block)
    # Permanent stretch.
    assert rows[12100] is False  # 12100%3=1  (FIRST permanent block)
    assert rows[12101] is False  # 12101%3=2
    assert rows[12102] is True   # 12102%3=0  (FIRST 1-of-3 firing)
    assert rows[12103] is False
    assert rows[12104] is False
    assert rows[12105] is True
    assert rows[12108] is True
    assert rows[12110] is False


def test_cli_returns_0_on_live_tree(aud, tmp_path):
    rc = aud.main([
        "--repo-root",   str(REPO_ROOT),
        "--out-json",    str(tmp_path / "audit.json"),
        "--out-md",      str(tmp_path / "audit.md"),
        "--pinned-time", "2026-05-18T18:00:00+00:00",
    ])
    assert rc == 0
    # Output files must exist and be valid.
    js = json.loads((tmp_path / "audit.json").read_text(encoding="utf-8"))
    assert js["all_green"] is True
    md = (tmp_path / "audit.md").read_text(encoding="utf-8")
    assert "# V13 DTD Flip Audit (block 12,100)" in md


# ---------------------------------------------------------------------------
# 2) Negative — synthetic fake repo trees that break each gate
# ---------------------------------------------------------------------------


def _make_minimal_fake_repo(tmp_path: Path, *,
                            params_h_text: str,
                            lottery_h_text: str,
                            extra_src: dict | None = None,
                            miner_text: str | None = None,
                            ) -> Path:
    rr = tmp_path / "fake-repo"
    (rr / "include" / "sost").mkdir(parents=True)
    (rr / "src").mkdir(parents=True)
    (rr / "include" / "sost" / "params.h").write_text(
        params_h_text, encoding="utf-8")
    (rr / "include" / "sost" / "lottery.h").write_text(
        lottery_h_text, encoding="utf-8")
    if miner_text is None:
        miner_text = (
            "// fake miner — consumes RPC field, no direct call.\n"
            "void f() { bool lottery_triggered = false; (void)lottery_triggered; }\n"
        )
    (rr / "src" / "sost-miner.cpp").write_text(
        miner_text, encoding="utf-8")
    if extra_src:
        for name, body in extra_src.items():
            (rr / "src" / name).write_text(body, encoding="utf-8")
    return rr


_GOOD_PARAMS_H = """
inline constexpr int64_t V11_PHASE2_HEIGHT = 7100;
inline constexpr int64_t LOTTERY_HIGH_FREQ_WINDOW = 5000;
inline constexpr int32_t LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW = 5;
inline constexpr int64_t V13_HEIGHT = 12000;
inline constexpr int32_t lottery_exclusion_window_at(int64_t height) {
    return (height >= V13_HEIGHT) ? 6
        : LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW;
}
"""

_GOOD_LOTTERY_H = """
inline bool is_lottery_block(int64_t height, int64_t phase2_height) {
    if (phase2_height == INT64_MAX) return false;
    if (height < phase2_height)     return false;
    const int64_t offset = height - phase2_height;
    if (offset < LOTTERY_HIGH_FREQ_WINDOW) return (height % 3) != 0;
    return (height % 3) == 0;
}
"""


def test_negative_wrong_phase2_height_constant(aud, tmp_path):
    rr = _make_minimal_fake_repo(
        tmp_path,
        params_h_text=_GOOD_PARAMS_H.replace(
            "V11_PHASE2_HEIGHT = 7100",
            "V11_PHASE2_HEIGHT = 7099",
        ),
        lottery_h_text=_GOOD_LOTTERY_H,
    )
    r = aud.build_audit(repo_root=rr,
                        pinned_time="2026-05-18T18:00:00+00:00")
    assert r["all_green"] is False
    assert r["gates"]["g1_constants_pinned"] is False


def test_negative_numeric_literal_call_site(aud, tmp_path):
    rr = _make_minimal_fake_repo(
        tmp_path,
        params_h_text=_GOOD_PARAMS_H,
        lottery_h_text=_GOOD_LOTTERY_H,
        extra_src={
            "shadow_caller.cpp": (
                "#include \"sost/lottery.h\"\n"
                "bool g(int64_t h){ return is_lottery_block(h, 7100); }\n"
            ),
        },
    )
    r = aud.build_audit(repo_root=rr,
                        pinned_time="2026-05-18T18:00:00+00:00")
    assert r["all_green"] is False
    assert r["gates"]["g3_no_literal_call_sites"] is False
    cs = r["call_sites"]["call_sites"]
    bad = [s for s in cs if s["classification"] == "literal"]
    assert any(b["second_arg"] == "7100" for b in bad)


def test_negative_miner_recomputes_cadence(aud, tmp_path):
    rr = _make_minimal_fake_repo(
        tmp_path,
        params_h_text=_GOOD_PARAMS_H,
        lottery_h_text=_GOOD_LOTTERY_H,
        miner_text=(
            "#include \"sost/lottery.h\"\n"
            "bool m(int64_t height){\n"
            "    bool lottery_triggered = is_lottery_block(height, 7100);\n"
            "    return lottery_triggered;\n"
            "}\n"
        ),
    )
    r = aud.build_audit(repo_root=rr,
                        pinned_time="2026-05-18T18:00:00+00:00")
    assert r["gates"]["g4_miner_no_shadow_logic"] is False
    assert r["miner_independence"]["has_is_lottery_block_call"] is True


def test_negative_miner_stray_modulo_three(aud, tmp_path):
    rr = _make_minimal_fake_repo(
        tmp_path,
        params_h_text=_GOOD_PARAMS_H,
        lottery_h_text=_GOOD_LOTTERY_H,
        miner_text=(
            "bool m(int64_t height){\n"
            "    bool lottery_triggered = (height % 3) == 0;\n"
            "    return lottery_triggered;\n"
            "}\n"
        ),
    )
    r = aud.build_audit(repo_root=rr,
                        pinned_time="2026-05-18T18:00:00+00:00")
    assert r["gates"]["g4_miner_no_shadow_logic"] is False
    assert r["miner_independence"]["has_height_modulo_three"] is True


def test_negative_cooldown_couples_to_is_lottery_block(aud, tmp_path):
    bad_params = _GOOD_PARAMS_H.replace(
        "return (height >= V13_HEIGHT) ? 6\n"
        "        : LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW;",
        "return is_lottery_block(height, V11_PHASE2_HEIGHT) ? 6 : 5;",
    )
    rr = _make_minimal_fake_repo(
        tmp_path,
        params_h_text=bad_params,
        lottery_h_text=_GOOD_LOTTERY_H,
    )
    r = aud.build_audit(repo_root=rr,
                        pinned_time="2026-05-18T18:00:00+00:00")
    assert r["gates"]["g5_cooldown_helper_correct"] is False
    assert (
        r["cooldown_helper"]["couples_to_is_lottery_block"] is True
    )


def test_audit_id_is_deterministic_for_same_inputs(aud, tmp_path):
    rr = _make_minimal_fake_repo(
        tmp_path,
        params_h_text=_GOOD_PARAMS_H,
        lottery_h_text=_GOOD_LOTTERY_H,
    )
    a1 = aud.build_audit(repo_root=rr,
                         pinned_time="2026-05-18T18:00:00+00:00")
    a2 = aud.build_audit(repo_root=rr,
                         pinned_time="2026-05-18T18:00:00+00:00")
    assert a1["audit_id"] == a2["audit_id"]
    assert re.match(r"^v13dtdaudit-[0-9a-f]{16}$", a1["audit_id"])


def test_classify_arg_table(aud):
    f = aud._classify_arg
    assert f("V11_PHASE2_HEIGHT")       == "named_const"
    assert f("sost::V11_PHASE2_HEIGHT") == "named_const"
    assert f("phase2_h")                == "variable"
    assert f("phase2_height")           == "variable"
    assert f("in.phase2_height")        == "variable"
    assert f("ctx.phase2_h")            == "variable"
    assert f("7100")                    == "literal"
    assert f("INT64_MAX")               == "literal"
    assert f("std::numeric_limits<int64_t>::max()") == "literal"
    assert f("foo(bar)")                == "complex"


# ---------------------------------------------------------------------------
# 3) Static safety — auditor source must not import dangerous APIs
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
    "api.github.com",
    "GITHUB_TOKEN",
    "X-GitHub-",
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


def test_auditor_has_no_forbidden_tokens():
    src = SCRIPT.read_text(encoding="utf-8")
    found = [t for t in _FORBIDDEN_TOKENS if t in src]
    assert not found, (
        "v13_dtd_flip_audit.py contains forbidden token(s): "
        + repr(found)
    )


def test_auditor_has_no_git_invocations():
    src = SCRIPT.read_text(encoding="utf-8")
    found = [t for t in _FORBIDDEN_GIT if t in src]
    assert not found, (
        "v13_dtd_flip_audit.py contains forbidden git argv "
        "literal(s): " + repr(found)
    )


def test_auditor_has_no_url_strings():
    src = SCRIPT.read_text(encoding="utf-8")
    urls = re.findall(r"https?://[a-zA-Z0-9._/-]+", src)
    assert not urls, "auditor must contain no URLs; found: " + repr(urls)


def test_auditor_uses_only_stdlib():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "import re" in src
    assert "import json" in src
    assert "import hashlib" in src
    assert "from pathlib import Path" in src
