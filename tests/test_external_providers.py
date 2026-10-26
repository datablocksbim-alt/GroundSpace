"""External provider discovery must never ingest or expose credentials."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ground_space.providers import provider_catalog


class ExternalProviderTests(unittest.TestCase):
    def test_unconnected_providers_are_honest_and_write_locked(self):
        with patch("ground_space.providers.shutil.which", return_value=None):
            records = provider_catalog()
        self.assertEqual({"anthropic", "google", "xai", "openrouter", "deepseek"},
                         {item["id"] for item in records})
        self.assertTrue(all(item["status"] == "login_required" for item in records))
        self.assertTrue(all(not item["full_write_option"] for item in records))
        self.assertTrue(all(not item["credentials_stored_by_ground_space"] for item in records))

    def test_opencode_accounts_enable_only_matching_provider(self):
        def which(name):
            return "C:/tools/opencode.cmd" if name == "opencode" else None
        completed = SimpleNamespace(returncode=0, stdout="Anthropic account: work", stderr="")
        with patch("ground_space.providers.shutil.which", side_effect=which):
            records = provider_catalog(run=lambda *args, **kwargs: completed)
        indexed = {item["id"]: item for item in records}
        self.assertEqual("connected", indexed["anthropic"]["status"])
        self.assertTrue(indexed["anthropic"]["full_write_option"])
        self.assertEqual("login_required", indexed["xai"]["status"])

    def test_direct_cli_installation_does_not_claim_authentication(self):
        def which(name):
            return "C:/tools/claude.exe" if name == "claude" else None
        with patch("ground_space.providers.shutil.which", side_effect=which):
            indexed = {item["id"]: item for item in provider_catalog()}
        self.assertEqual("login_required", indexed["anthropic"]["status"])
        self.assertTrue(indexed["anthropic"]["cli_installed"])
        self.assertIsNone(indexed["anthropic"]["connection"])


if __name__ == "__main__":
    unittest.main()
