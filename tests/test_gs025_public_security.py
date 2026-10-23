"""GS-025: multi-user launch is fail-closed; rate limiting is not authentication."""
from __future__ import annotations

import os
import unittest
from unittest.mock import Mock,patch

from ground_space.security import (
    RequestRateLimit,assert_private_owner_mode,security_posture,require_verified_tenant
)
from ground_space.webapp import create_server,GroundSpaceApp
from ground_space.chatgpt_connection import CodexAppServerClient


class PublicReleaseGateTests(unittest.TestCase):
    def test_default_remains_private_owner(self):
        with patch.dict(os.environ,{},clear=False):
            for name in ("GROUND_SPACE_DEPLOYMENT_MODE","GROUND_SPACE_PUBLIC_USERS",
                         "GROUND_SPACE_ENABLE_MULTI_USER","GROUND_SPACE_PUBLIC_HOSTING"):
                os.environ.pop(name,None)
            assert_private_owner_mode()
            posture=security_posture()
            self.assertFalse(posture["public_ready"])
            self.assertFalse(posture["multi_user_accounts"])
            self.assertFalse(posture["per_user_os_sandbox"])

    def test_public_modes_all_rejected_before_listening(self):
        configs=[
            {"GROUND_SPACE_DEPLOYMENT_MODE":"public"},
            {"GROUND_SPACE_DEPLOYMENT_MODE":"multi_user"},
            {"GROUND_SPACE_PUBLIC_USERS":"1"},
            {"GROUND_SPACE_ENABLE_MULTI_USER":"true"},
            {"GROUND_SPACE_PUBLIC_HOSTING":"yes"},
        ]
        for config in configs:
            with self.subTest(config=config),patch.dict(os.environ,config,clear=False):
                with self.assertRaisesRegex(RuntimeError,"Public Ground Space is blocked"):
                    assert_private_owner_mode()
                with self.assertRaisesRegex(RuntimeError,"Public Ground Space is blocked"):
                    create_server(GroundSpaceApp.__new__(GroundSpaceApp),0)

    def test_service_is_loopback_only_and_has_rate_limiter(self):
        with patch.dict(os.environ,{"GROUND_SPACE_DEPLOYMENT_MODE":"owner_private",
                                   "GROUND_SPACE_PUBLIC_USERS":"0",
                                   "GROUND_SPACE_ENABLE_MULTI_USER":"0",
                                   "GROUND_SPACE_PUBLIC_HOSTING":"0"}):
            app=GroundSpaceApp.__new__(GroundSpaceApp)
            server=create_server(app,0)
            try:
                self.assertEqual("127.0.0.1",server.server_address[0])
                self.assertIsInstance(server.post_limiter,RequestRateLimit)
                self.assertTrue(server.post_limiter.allow("127.0.0.1"))
            finally:
                server.server_close()

    def test_limits_are_per_peer_and_decay(self):
        clock=[100.]
        limit=RequestRateLimit(limit=2,seconds=30,clock=lambda:clock[0])
        self.assertTrue(limit.allow("proxy"))
        self.assertTrue(limit.allow("proxy"))
        self.assertFalse(limit.allow("proxy"))
        self.assertTrue(limit.allow("other"))
        clock[0]+=31
        self.assertTrue(limit.allow("proxy"))

    def test_unauthenticated_multiuser_resources_are_denied(self):
        for subject,owner in [(None,"user1"),("user1",None),("user1","user2"),("","user1")]:
            with self.subTest(subject=subject,owner=owner),self.assertRaises(PermissionError):
                require_verified_tenant(subject,owner)
        require_verified_tenant("verified-user","verified-user")

    def test_owner_cli_login_does_not_become_public_login(self):
        client=CodexAppServerClient(executable="/fake/codex",popen=Mock())
        self.addCleanup(client.close)
        with patch.dict(os.environ,{"GROUND_SPACE_DEPLOYMENT_MODE":"public",
                                    "GROUND_SPACE_OWNER_CHATGPT_LINK_ENABLED":"1"}):
            with self.assertRaisesRegex(RuntimeError,"Public Ground Space is blocked"):
                client.start_device_login()
            client.popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
