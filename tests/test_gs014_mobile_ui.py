"""GS-014: chat-first responsive layout preserves Ground Space behavior and usable controls."""
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "web" / "public"


class ElementIDs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = {}
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.elements[attrs["id"]] = (tag, attrs)


class MobileChatUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (PUBLIC / "index.html").read_text(encoding="utf-8")
        cls.css = (PUBLIC / "app.css").read_text(encoding="utf-8")
        cls.js = (PUBLIC / "app.js").read_text(encoding="utf-8")
        cls.elements = ElementIDs()
        cls.elements.feed(cls.html)

    def test_mobile_drawer_accessible_and_optional_on_desktop(self):
        for key in ("agentRail", "mobileRailToggle", "mobileRailBackdrop", "closeMobileRail"):
            with self.subTest(key=key):
                self.assertIn(key, self.elements.elements)
        _, attrs = self.elements.elements["mobileRailToggle"]
        self.assertEqual("agentRail", attrs["aria-controls"])
        self.assertEqual("false", attrs["aria-expanded"])
        self.assertIn("mobile-rail-toggle,.mobile-rail-heading,.mobile-options-toggle{display:none}", self.css)
        self.assertIn("visibility:hidden", self.css)
        self.assertIn(".agent-rail.mobile-open", self.css)
        self.assertIn("setMobileRail(false)", self.js)
        self.assertIn("rail.inert=mobileViewport.matches&&!active", self.js)

    def test_mobile_chat_takes_screen_height_not_full_page_scroll(self):
        self.assertIn("height:var(--gs-mobile-viewport-height,100dvh)", self.css)
        self.assertIn("visualViewport?.addEventListener('resize',syncMobileViewportHeight)", self.js)
        self.assertIn("grid-template-rows:auto minmax(0,1fr)", self.css)
        self.assertIn("grid-template-rows:auto minmax(0,1fr) auto", self.css)
        self.assertIn("min-height:0;overflow-y:auto", self.css)
        self.assertIn(".chat-layout .active-agent-panel{display:none}", self.css)
        self.assertIn("safe-area-inset-bottom", self.css)
        self.assertIn("@media (max-width:760px)", self.css)

    def test_composer_and_metadata_remain_accessible(self):
        for key in ("chatOptions", "mobileOptionsToggle", "sendButton", "prompt", "modelSelect"):
            self.assertIn(key, self.elements.elements)
        self.assertIn("setMobileOptions", self.js)
        self.assertIn(".composer.options-open .chat-options{display:flex}", self.css)
        self.assertIn("font:16px/1.45", self.css)  # Prevent iOS input-focus zoom
        self.assertIn("copyButton(entry.task_id)", self.js)
        self.assertIn("message-id", self.css)
        self.assertIn("message-meta", self.js)

    def test_desktop_routes_and_project_selection_intact(self):
        for key in ("projectSelect", "projectList", "privateChannelMenu",
                    "groupDialog", "projectDialog", "view-agents", "view-tasks"):
            self.assertIn(key, self.elements.elements)
        self.assertNotIn("newGroupButton", self.elements.elements)
        self.assertNotIn("groupList", self.elements.elements)
        self.assertNotIn('aria-label="Group chats"', self.html)
        self.assertIn('data-new-project-group', self.js)
        self.assertIn('data-project-toggle', self.js)
        self.assertIn('data-group', self.js)
        for api_path in ("/api/groups/send", "/api/projects/add", "/api/bootstrap"):
            self.assertIn(api_path, self.js)
        self.assertIn(".chat-layout{max-width:1600px;grid-template-columns:260px minmax(0,1fr) 250px}", self.css)
        self.assertIn("mobileViewport.addEventListener('change',syncMobileLayout)", self.js)

    def test_no_duplicate_ids_or_script_injection(self):
        ids = re.findall(r'\bid="([^"]+)"', self.html)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertNotIn("innerHTML=event.target.value", self.js)


if __name__ == "__main__":
    unittest.main()
