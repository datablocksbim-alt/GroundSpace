"""GS-029: project creation should use a guarded ASUS folder picker, not a typed path."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ground_space.workspaces import WorkspaceRegistry

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "web" / "public" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "web" / "public" / "app.js").read_text(encoding="utf-8")


class ProjectFolderPickerTests(unittest.TestCase):
    def test_picker_is_primary_and_manual_path_field_hidden(self):
        self.assertIn('type="hidden" id="projectPath"', HTML)
        self.assertNotIn('<label for="projectPath">Local folder path</label>', HTML)
        for control in ("folderPicker", "folderEntries", "folderUp", "browseRoots",
                        "selectedProjectFolder", "changeProjectFolder", "saveProject"):
            self.assertIn('id="' + control + '"', HTML)
        self.assertIn('id="saveProject" disabled', HTML)
        self.assertIn("browseFolders(); // Open the ASUS folder browser immediately", JS)
        self.assertIn("if(!path){showDialogError", JS)

    def test_browse_only_allows_server_approved_folders(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            allowed = root / "allowed"
            allowed.mkdir()
            project = allowed / "Project One"
            project.mkdir()
            forbidden = root / "secrets"
            forbidden.mkdir()
            registry = WorkspaceRegistry(root / "state", [allowed])
            roots = registry.browse_folders()
            self.assertEqual(roots["folders"][0]["path"], str(allowed.resolve()))
            folders = registry.browse_folders(str(allowed))
            self.assertEqual([x["name"] for x in folders["folders"]], ["Project One"])
            self.assertEqual(registry.browse_folders(str(project))["current"], str(project.resolve()))
            with self.assertRaisesRegex(ValueError, "restricted"):
                registry.browse_folders(str(forbidden))
            with self.assertRaisesRegex(ValueError, "inside an allowed project root"):
                registry.add_project(str(allowed))
            with self.assertRaisesRegex(ValueError, "inside an allowed project root"):
                registry.add_project(str(forbidden))
            saved = registry.add_project(str(project))
            self.assertEqual(saved["scope"], "metadata_only")
            self.assertEqual(saved["name"], "Project One")


if __name__ == "__main__":
    unittest.main()
