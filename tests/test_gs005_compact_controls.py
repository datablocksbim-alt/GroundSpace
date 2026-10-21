"""Regression tests for the compact inline AI composer controls."""
from __future__ import annotations

import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VOID_TAGS = {"meta", "link", "input", "br", "hr", "img"}


class ControlParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.controls = {}
        self.labels = {}

    def handle_starttag(self, tag, attributes):
        props = dict(attributes)
        if tag == "select":
            self.controls[props.get("id")] = list(self.stack)
        if tag == "label" and props.get("for"):
            self.labels[props["for"]] = props
        if tag not in VOID_TAGS:
            self.stack.append((tag, props.get("id"), props.get("class", "")))

    def handle_endtag(self, tag):
        while self.stack:
            if self.stack.pop()[0] == tag:
                break


class CompactComposerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.markup = (ROOT / "web" / "public" / "index.html").read_text(encoding="utf-8")
        cls.css = (ROOT / "web" / "public" / "app.css").read_text(encoding="utf-8")
        cls.parser = ControlParser()
        cls.parser.feed(cls.markup)

    def test_capability_model_and_profile_share_one_toolbar(self):
        for control in ("requestType", "modelSelect", "performanceSelect"):
            self.assertIn(control, self.parser.controls)
            classes = [item[2] for item in self.parser.controls[control]]
            self.assertIn("composer-foot", classes)
            self.assertIn(control, self.parser.labels)
        self.assertLess(self.markup.index('id="requestType"'),
                        self.markup.index('id="modelSelect"'))
        self.assertLess(self.markup.index('id="modelSelect"'),
                        self.markup.index('id="performanceSelect"'))
        self.assertEqual(1, self.markup.count('id="modelControls"'))

    def test_model_and_profile_belong_to_same_compact_group(self):
        for control in ("modelSelect", "performanceSelect"):
            ancestors = self.parser.controls[control]
            self.assertTrue(any(item[1] == "modelControls" for item in ancestors))
            self.assertTrue(any("chat-options" in item[2] for item in ancestors))

    def test_hidden_administrator_controls_and_responsiveness(self):
        self.assertIn("#requestType[hidden]{display:none}", self.css)
        self.assertIn(".model-controls[hidden]{display:none}", self.css)
        self.assertIn("@media(max-width:760px)", self.css)
        self.assertIn("@media(max-width:480px)", self.css)


if __name__ == "__main__":
    unittest.main()
