"""GS-010: route only the explicitly selected local group participant."""

import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from ground_space.coordinator import (route_group_message, coordinator_instructions,
                                      specialist_instructions)
from ground_space.webapp import GroundSpaceApp, GroundSpaceHandler

MODELS = ["qwen2.5-coder:3b", "qwen3.5:4b", "granite3.3:2b"]


class CoordinatorRoutingTests(unittest.TestCase):
    def test_unaddressed_goes_only_to_coordinator(self):
        route = route_group_message("How are we progressing?", MODELS)
        self.assertEqual(route.models, (MODELS[0],))
        self.assertTrue(route.coordinator)

    def test_goal_is_forced_coordinator(self):
        route = route_group_message("@Qwen Build Codex", MODELS, force_coordinator=True)
        self.assertTrue(route.coordinator)
        self.assertEqual(len(route.models), 1)

    def test_qwen_speaks_for_itself(self):
        route = route_group_message("@Qwen examine Codex", MODELS)
        self.assertEqual(route.models, (MODELS[0],))
        self.assertFalse(route.coordinator)

    def test_exact_model_mention(self):
        self.assertEqual(route_group_message("@qwen3.5:4b hi", MODELS).models, (MODELS[1],))

    def test_explicit_multimodel_reply(self):
        route = route_group_message("@Qwen @Granite compare", MODELS)
        self.assertEqual(route.models, (MODELS[0], MODELS[2]))
        self.assertFalse(route.coordinator)

    def test_visible_ui_aliases_route_to_group_participants(self):
        self.assertEqual(route_group_message("@Qwen please review", MODELS).models, (MODELS[0],))
        self.assertEqual(route_group_message("@Granite please review", MODELS).models, (MODELS[2],))
        self.assertTrue(route_group_message("@Coordinator summarize", MODELS).coordinator)

    def test_unconnected_cloud_cannot_fallback(self):
        with self.assertRaisesRegex(ValueError, "not connected"):
            route_group_message("@Claude hi", MODELS)

    def test_unknown_and_ambiguous_fail(self):
        with self.assertRaises(ValueError):
            route_group_message("@missing hi", MODELS)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            route_group_message("@qwen3.5 hi", ["qwen3.5:4b", "qwen3.5:4b-64k"])

    def test_coordinator_can_delegate_to_explicit_specialists(self):
        route = route_group_message("@Coordinator @Qwen @Granite say hi", MODELS)
        self.assertEqual((MODELS[0], MODELS[2]), route.models)
        self.assertFalse(route.coordinator)

    def test_natural_coordinator_delegation_routes_individual_replies(self):
        route = route_group_message("@Coordinator ask Qwen and Granite to say hi", MODELS)
        self.assertEqual((MODELS[0], MODELS[2]), route.models)
        self.assertFalse(route.coordinator)

    def test_ministral_coordinator_preference(self):
        models = MODELS + ["ministral-3:8b"]
        self.assertEqual(route_group_message("hi", models).models, ("ministral-3:8b",))

    def test_proposed_tasks_are_not_execution_approval(self):
        prompt = coordinator_instructions("Build the Codex", group_models=MODELS, kind="goal", goal_id="NOTE-X")
        self.assertIn("status PROPOSED", prompt)
        self.assertIn("owner approval", prompt)
        self.assertIn("no tools", prompt)
        self.assertIn("Never simulate", prompt)

    def test_specialists_are_instructed_to_speak_only_for_themselves(self):
        prompt = specialist_instructions("Say hello", model=MODELS[0])
        self.assertIn(MODELS[0], prompt)
        self.assertIn("only as yourself", prompt)
        self.assertIn("simulated transcript", prompt)

class BootstrapAvailabilityTests(unittest.TestCase):
    def test_browser_poll_reuses_one_short_local_model_probe(self):
        app = GroundSpaceApp.__new__(GroundSpaceApp)
        app.lock = threading.RLock()
        app.ollama_endpoint = "http://127.0.0.1:1"
        app.conversations = {"test-room": [{"role": "user", "content": "hello"}]}
        app.tasks = Mock(return_value=[])
        app.workspaces = SimpleNamespace(snapshot=Mock(return_value={"groups": [], "projects": []}))
        app.agents = Mock(return_value=[])
        app.catalog = Mock(return_value={"registered": []})
        availability = {"available": False, "models": [], "reason": "offline"}

        with patch("ground_space.webapp.probe_ollama", return_value=availability) as probe:
            result = app.bootstrap()

        probe.assert_called_once_with("http://127.0.0.1:1", timeout=0.6)
        app.agents.assert_called_once_with(availability=availability)
        app.catalog.assert_called_once_with(availability=availability)
        self.assertEqual("hello", result["conversations"]["test-room"][0]["content"])
        self.assertEqual(0, result["paid_api_usage_aud"])


class HTTPDisconnectTests(unittest.TestCase):
    def test_disconnected_browser_is_handled_without_server_traceback(self):
        # Mimic a browser cancelling /api/bootstrap while bytes are being sent.
        handler = GroundSpaceHandler.__new__(GroundSpaceHandler)
        for error in (
            BrokenPipeError(32, "Broken pipe"),
            ConnectionResetError(10054, "Connection reset"),
            ConnectionAbortedError(10053, "Connection aborted"),
        ):
            with self.subTest(error=type(error).__name__):
                with patch("http.server.BaseHTTPRequestHandler.handle", side_effect=error):
                    self.assertIsNone(handler.handle())

    def test_unrelated_server_failure_still_surfaces(self):
        handler = GroundSpaceHandler.__new__(GroundSpaceHandler)
        with patch("http.server.BaseHTTPRequestHandler.handle", side_effect=ValueError("bad app state")):
            with self.assertRaisesRegex(ValueError, "bad app state"):
                handler.handle()


if __name__ == "__main__":
    unittest.main()
