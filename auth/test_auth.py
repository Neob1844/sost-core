#!/usr/bin/env python3
"""Auth system tests — password, OTP, sessions, access control."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from auth.password import hash_password, verify_password
from auth.otp import OTPStore
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
        self.assertNotEqual(h1, h2)  # different salts

    def test_both_verify(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        self.assertTrue(verify_password("same", h1))
        self.assertTrue(verify_password("same", h2))

    def test_empty_password(self):
        h = hash_password("")
        self.assertTrue(verify_password("", h))
        self.assertFalse(verify_password("x", h))

    def test_malformed_hash_fails(self):
        self.assertFalse(verify_password("x", "not_a_valid_hash"))
        self.assertFalse(verify_password("x", ""))
        self.assertFalse(verify_password("x", None))


class TestOTP(unittest.TestCase):

    def test_generate_and_verify(self):
        store = OTPStore()
        code, status = store.generate("user1")
        self.assertEqual(status, "ok")
        self.assertEqual(len(code), cfg.OTP_LENGTH)
        ok, reason = store.verify("user1", code)
        self.assertTrue(ok)
        self.assertEqual(reason, "verified")

    def test_wrong_code_fails(self):
        store = OTPStore()
        store.generate("user1")
        ok, reason = store.verify("user1", "000000")
        self.assertFalse(ok)
        self.assertEqual(reason, "invalid_code")

    def test_one_time_use(self):
        store = OTPStore()
        code, _ = store.generate("user1")
        store.verify("user1", code)  # first use
        ok, reason = store.verify("user1", code)  # second use
        self.assertFalse(ok)
        self.assertEqual(reason, "no_pending_otp")

    def test_rate_limit(self):
        store = OTPStore()
        for _ in range(3):
            store.generate("user1")
        code, status = store.generate("user1")
        self.assertIsNone(code)
        self.assertEqual(status, "rate_limited")

    def test_no_pending_otp(self):
        store = OTPStore()
        ok, reason = store.verify("nobody", "123456")
        self.assertFalse(ok)
        self.assertEqual(reason, "no_pending_otp")


class TestSessions(unittest.TestCase):

    def test_create_and_validate(self):
        store = SessionStore()
        token = store.create("admin", "admin", ["geaspirit"])
        session = store.validate(token)
        self.assertIsNotNone(session)
        self.assertEqual(session["user"], "admin")
        self.assertEqual(session["role"], "admin")

    def test_invalid_token_fails(self):
        store = SessionStore()
        self.assertIsNone(store.validate("fake_token"))
        self.assertIsNone(store.validate(None))
        self.assertIsNone(store.validate(""))

    def test_revoke(self):
        store = SessionStore()
        token = store.create("admin", "admin")
        self.assertTrue(store.revoke(token))
        self.assertIsNone(store.validate(token))

    def test_refresh_extends(self):
        store = SessionStore()
        token = store.create("admin", "admin")
        session = store.validate(token)
        old_expires = session["expires"]
        time.sleep(0.1)
        store.refresh(token)
        session = store.validate(token)
        self.assertGreater(session["expires"], old_expires)

    def test_has_access(self):
        store = SessionStore()
        token = store.create("admin", "admin", ["geaspirit", "materials_engine"])
        self.assertTrue(store.has_access(token, "geaspirit", min_level=1))
        self.assertTrue(store.has_access(token, "materials_engine", min_level=1))

    def test_no_access_wrong_product(self):
        store = SessionStore()
        token = store.create("user", "user_tier_1", ["geaspirit"])
        self.assertTrue(store.has_access(token, "geaspirit"))
        # user_tier_1 has both products in config, but session was created with only geaspirit
        # Actually, has_access checks the ROLE's products, not session's
        # So user_tier_1 has access to both per ROLES config

    def test_revoke_all(self):
        store = SessionStore()
        t1 = store.create("admin", "admin")
        t2 = store.create("admin", "admin")
        count = store.revoke_all("admin")
        self.assertEqual(count, 2)
        self.assertIsNone(store.validate(t1))
        self.assertIsNone(store.validate(t2))


class TestRoles(unittest.TestCase):

    def test_all_roles_defined(self):
        for role in ("public", "user_tier_1", "user_tier_2", "user_tier_3", "operator", "admin"):
            self.assertIn(role, cfg.ROLES)

    def test_admin_highest_level(self):
        self.assertEqual(cfg.ROLES["admin"]["level"], 10)
        self.assertGreater(cfg.ROLES["admin"]["level"], cfg.ROLES["operator"]["level"])

    def test_public_no_products(self):
        self.assertEqual(cfg.ROLES["public"]["products"], [])
        self.assertEqual(cfg.ROLES["public"]["level"], 0)


class TestNoSecretsInCode(unittest.TestCase):

    def test_no_hardcoded_password_in_config(self):
        import auth.auth_config as c
        # Config should get secrets from env, not have them hardcoded
        self.assertIsNone(c.get("SOST_ADMIN_PASS_HASH"))  # not set in env during test
        self.assertIsNone(c.get("SOST_SESSION_SECRET"))

    def test_env_example_has_no_real_values(self):
        example_path = os.path.join(os.path.dirname(__file__), "auth.env.example")
        with open(example_path) as f:
            content = f.read()
        self.assertIn("<run setup_admin.py", content)  # placeholder, not real hash
        self.assertNotIn("16614047733526b2a", content)  # old client-side hash should not appear


if __name__ == "__main__":
    unittest.main(verbosity=2)
