"""GS-024: device-code connection requires owner opt-in; never handles tokens."""
from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

from ground_space.chatgpt_connection import CodexAppServerClient


class DeviceLoginTests(unittest.TestCase):
    def setUp(self):
        self.client=CodexAppServerClient(executable="/fake/codex",popen=Mock())
        self.addCleanup(self.client.close)

    def test_disabled_by_default_and_no_cli_started(self):
        with patch.dict(os.environ,{},clear=False):
            os.environ.pop("GROUND_SPACE_OWNER_CHATGPT_LINK_ENABLED",None)
            self.assertFalse(self.client.enabled())
            self.assertFalse(self.client.status()["connected"])
            with self.assertRaisesRegex(ValueError,"disabled"):
                self.client.start_device_login()
            self.client.popen.assert_not_called()

    def test_device_code_request_is_fixed_and_only_returns_safe_fields(self):
        reply={"type":"chatgptDeviceCode","loginId":"UUID-123",
               "verificationUrl":"https://auth.openai.com/codex/device",
               "userCode":"ABCD-1234","accessToken":"private-do-not-expose"}
        with patch.dict(os.environ,{"GROUND_SPACE_OWNER_CHATGPT_LINK_ENABLED":"1"}),\
             patch.object(self.client,"_ensure"),\
             patch.object(self.client,"_rpc",return_value=reply) as rpc:
            result=self.client.start_device_login()
        rpc.assert_called_once_with("account/login/start",{"type":"chatgptDeviceCode"})
        self.assertEqual("pending",self.client.login_state)
        self.assertEqual("ABCD-1234",result["user_code"])
        self.assertEqual("https://auth.openai.com/codex/device",result["verification_url"])
        self.assertNotIn("accessToken",result)
        self.assertNotIn("private-do-not-expose",str(result))

    def test_invalid_provider_link_and_codes_fail_closed(self):
        good={"loginId":"L-1","verificationUrl":"https://auth.openai.com/codex/device","userCode":"ABCD-1234"}
        changes=[
            {"verificationUrl":"http://auth.openai.com/codex/device"},
            {"verificationUrl":"https://evil.example.net/login"},
            {"verificationUrl":"https://auth.openai.com.evil.com/codex/device"},
            {"verificationUrl":"https://user:password@auth.openai.com/codex/device"},
            {"verificationUrl":"https://auth.openai.com:444/codex/device"},
            {"userCode":"<script>"},
            {"userCode":""},
            {"loginId":""},
        ]
        for values in changes:
            with self.subTest(values=values),self.assertRaises(ValueError):
                self.client.safe_device_response({**good,**values})

    def test_status_only_shows_account_type_and_plan(self):
        response={"account":{"type":"chatgpt","planType":"plus",
                  "email":"private@example.com","accessToken":"private-key"},
                  "requiresOpenaiAuth":True}
        with patch.dict(os.environ,{"GROUND_SPACE_OWNER_CHATGPT_LINK_ENABLED":"1"}),\
             patch.object(self.client,"_ensure"),\
             patch.object(self.client,"_rpc",return_value=response):
            item=self.client.status()
        self.assertTrue(item["connected"])
        self.assertEqual("chatgpt",item["auth_mode"])
        self.assertEqual("plus",item["plan_type"])
        self.assertNotIn("email",item)
        self.assertNotIn("accessToken",item)

    def test_no_cloned_multi_user_identity_claims(self):
        with patch.dict(os.environ,{"GROUND_SPACE_OWNER_CHATGPT_LINK_ENABLED":"1"}),\
             patch.object(self.client,"_ensure"),\
             patch.object(self.client,"_rpc",return_value={"account":None}):
            item=self.client.status()
        self.assertFalse(item["connected"])
        self.assertEqual("single_owner_codex_cli",item["scope"])


if __name__=="__main__":
    unittest.main()
