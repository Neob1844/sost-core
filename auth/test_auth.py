#!/usr/bin/env python3
"""Auth system tests — password, TOTP, sessions, access control."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from auth.password import hash_password, verify_password
from auth.otp import TOTPManager
from auth.sessions import SessionStore
from auth import auth_config as cfg


class TestPasswordHashing(unittest.TestCase):

    def test_hash_and_verify(self):
        h = hash_password("test_password_123")
        self.assertIn(":", h)
        self.assertTrue(verify_password("test_password_123", h))

    def test_wrong_password_fails(self):
        h = hash_password("correct_password")
        self.assertFalse(verify_password("wrong_password", h))

    def test_different_hashes_for_same_password(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        self.assertNotEqual(h1, h2)

    def test_both_verify(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        self.assertTrue(verify_password("same", h1))
        self.assertTrue(verify_password("same", h2))

    def test_malformed_hash_fails(self):
        self.assertFalse(verify_password("x", "not_a_valid_hash"))
        self.assertFalse(verify_password("x", ""))
        self.assertFalse(verify_password("x", None))


class TestTOTP(unittest.TestCase):

    def test_generate_secret(self):
        secret = TOTPManager.generate_secret()
        self.assertIsInstance(secret, str)
        self.assertGreater(len(secret), 16)

    def test_verify_correct_code(self):
        import pyotp
        secret = TOTPManager.generate_secret()
        mgr = TOTPManager(secret)
        totp = pyotp.TOTP(secret)
        code = totp.now()
        ok, reason = mgr.verify(code)
        self.assertTrue(ok)
        self.assertEqual(reason, "verified")

    def test_verify_wrong_code(self):
        secret = TOTPManager.generate_secret()
        mgr = TOTPManager(secret)
        ok, reason = mgr.verify("000000")
        self.assertFalse(ok)
        self.assertEqual(reason, "invalid_code")

    def test_verify_tolerance(self):
        import pyotp
        secret = TOTPManager.generate_secret()
        mgr = TOTPManager(secret)
        totp = pyotp.TOTP(secret)
        # Current code should work
        code = totp.now()
        ok, _ = mgr.verify(code)
        self.assertTrue(ok)

    def test_not_configured(self):
        mgr = TOTPManager(None)
        self.assertFalse(mgr.is_configured())
        ok, reason = mgr.verify("123456")
        self.assertFalse(ok)
        self.assertEqual(reason, "2fa_not_configured")

    def test_provisioning_uri(self):
        secret = TOTPManager.generate_secret()
        mgr = TOTPManager(secret)
        uri = mgr.get_provisioning_uri("admin", "SOST")
        self.assertIn("otpauth://totp/", uri)
        self.assertIn("SOST", uri)

    def test_rate_limit(self):
        secret = TOTPManager.generate_secret()
        mgr = TOTPManager(secret)
        for _ in range(5):
            mgr.verify("000000", "user1")
        ok, reason = mgr.verify("000000", "user1")
        self.assertFalse(ok)
        self.assertEqual(reason, "too_many_attempts")


class TestSessions(unittest.TestCase):

    def test_create_and_validate(self):
        store = SessionStore()
        token = store.create("admin", "admin", ["product_a"])
        session = store.validate(token)
        self.assertIsNotNone(session)
        self.assertEqual(session["user"], "admin")

    def test_invalid_token(self):
        store = SessionStore()
        self.assertIsNone(store.validate("fake"))
        self.assertIsNone(store.validate(None))

    def test_revoke(self):
        store = SessionStore()
        token = store.create("admin", "admin")
        self.assertTrue(store.revoke(token))
        self.assertIsNone(store.validate(token))

    def test_refresh(self):
        store = SessionStore()
        token = store.create("admin", "admin")
        old = store.validate(token)["expires"]
        time.sleep(0.05)
        store.refresh(token)
        self.assertGreater(store.validate(token)["expires"], old)

    def test_has_access_denies_when_no_products_are_entitled(self):
        # This used to assert that an admin token granted access to geaspirit and
        # materials_engine. Those are unrelated products that never asked this gateway for
        # anything, so their entitlements were removed and no role now carries a product.
        #
        # has_access reads the products of the ROLE in config, not of the token, so with no
        # products configured it denies everything. That is the correct current behaviour and
        # is what this test pins. The mechanism itself is now vestigial for SOST: nothing in
        # the codebase calls it except the /access endpoint. It is left in place rather than
        # ripped out of a running service, and should be removed deliberately if SOST never
        # gates a product of its own.
        store = SessionStore()
        token = store.create("admin", "admin", ["product_a"])
        self.assertIsNotNone(store.validate(token))          # the session itself is valid
        self.assertFalse(store.has_access(token, "product_a"))
        self.assertFalse(store.has_access(token, "anything"))

    def test_revoke_all(self):
        store = SessionStore()
        t1 = store.create("admin", "admin")
        t2 = store.create("admin", "admin")
        self.assertEqual(store.revoke_all("admin"), 2)


class TestRoles(unittest.TestCase):

    def test_all_defined(self):
        for r in ("public", "user_tier_1", "user_tier_2", "user_tier_3", "operator", "admin"):
            self.assertIn(r, cfg.ROLES)

    def test_admin_highest(self):
        self.assertEqual(cfg.ROLES["admin"]["level"], 10)


class TestNoSecrets(unittest.TestCase):

    def test_no_hardcoded_secrets(self):
        self.assertIsNone(cfg.get("SOST_ADMIN_PASS_HASH"))
        self.assertIsNone(cfg.get("SOST_2FA_SECRET"))

    def test_env_example_clean(self):
        path = os.path.join(os.path.dirname(__file__), "auth.env.example")
        with open(path) as f:
            c = f.read()
        self.assertIn("<run setup_admin.py", c)
        self.assertNotIn("16614047733526b2a", c)


if __name__ == "__main__":
    unittest.main(verbosity=2)
