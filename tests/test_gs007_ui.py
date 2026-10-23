"""Structural checks for GS-007 group chats and project selection UI."""
from __future__ import annotations

import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOID_TAGS = {"meta", "link", "input", "br", "hr", "img"}


class IDs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
    def handle_starttag(self, tag, attrs):
        value = dict(attrs).get("id")
        if value:
            self.ids.add(value)


class GS007UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "web" / "public" / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "web" / "public" / "app.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "web" / "public" / "app.css").read_text(encoding="utf-8")
        cls.parser = IDs()
        cls.parser.feed(cls.html)

    def test_group_creation_and_participant_controls(self):
        for key in ("groupDialog", "groupForm", "groupName", "groupProject",
                    "groupMemberOptions", "saveGroup", "editGroupButton",
                    "projectList", "addProjectButton"):
            with self.subTest(key=key):
                self.assertIn(key, self.parser.ids)
        self.assertIn("/api/groups/create", self.js)
        self.assertIn("/api/groups/update", self.js)
        self.assertIn("/api/groups/send", self.js)
        self.assertIn("data-new-project-group", self.js)

    def test_group_participants_are_visible_and_mentions_are_discoverable(self):
        self.assertIn('id="mentionMenu"', self.html)
        self.assertIn('data-mention', self.js)
        self.assertIn('groupMentionOptions', self.js)
        self.assertIn('@Coordinator', self.js)
        self.assertIn('@Qwen', self.js)
        self.assertIn('@Granite', self.js)
        self.assertIn('.member-option input[type="checkbox"]', self.css)
        self.assertIn('width:16px', self.css)

    def test_active_agent_panel_tracks_current_group(self):
        self.assertIn('activeAgentList', self.parser.ids)
        self.assertIn('activeAgentNote', self.parser.ids)
        self.assertIn('renderActiveAgents', self.js)
        self.assertIn("group.models.map", self.js)
        self.assertIn('Coordinator', self.js)
        self.assertIn('.active-agent-panel', self.css)

    def test_project_folder_picker_and_channel_switcher(self):
        for key in ("projectSelect", "projectDialog", "projectPath", "projectList",
                    "browseRoots", "folderPicker", "folderEntries", "folderUp"):
            with self.subTest(key=key):
                self.assertIn(key, self.parser.ids)
        self.assertIn("/api/projects/browse", self.js)
        self.assertIn("/api/projects/add", self.js)
        self.assertIn("conversationFor(agent,projectId)", self.js)

    def test_soft_multi_ai_replies_and_copy(self):
        self.assertIn("group-task-status", self.js)
        self.assertIn("member-label", self.js)
        self.assertIn("copyButton(groupTask.task_id)", self.js)
        self.assertIn(".group-room.active", self.css)
        self.assertIn(".workspace-dialog", self.css)
        self.assertIn(".message .member-label", self.css)
        self.assertIn("Copy response", self.js)


if __name__ == "__main__":
    unittest.main()
