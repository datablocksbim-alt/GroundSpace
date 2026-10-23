"""GS-023: Qwen/Codex/Granite handoffs preserve project and approval boundaries."""
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock

from ground_space.collaboration import CollaborationLedger
from ground_space.webapp import GroundSpaceApp


class HandoffTests(unittest.TestCase):
    def setUp(self):
        t=TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.path=Path(t.name)
        self.group={
          "id":"room1","project_id":"project1","conversation_id":"conversation1",
          "models":["qwen2.5-coder:3b","codex","granite4:3b"],
          "approval_modes":{"qwen2.5-coder:3b":"approve_for_me","codex":"manual",
                            "granite4:3b":"approve_for_me"},
        }
        self.tasks={}
        self.jobs={}
        self.app=GroundSpaceApp.__new__(GroundSpaceApp)
        self.app.lock=threading.RLock()
        self.app.conversations={}
        self.app.history_path=self.path/"history.json"
        self.app.collaboration_lock=threading.RLock()
        self.app.collaborations=CollaborationLedger(self.path/"flows.json")
        self.app.workspaces=SimpleNamespace(get_group=Mock(side_effect=lambda _:self.group))
        self.app.codex=SimpleNamespace(is_registered=Mock(return_value=True),
            submit=Mock(side_effect=self.submit_codex),
            get=Mock(side_effect=lambda key:self.jobs[key]))
        self.app.administrator=SimpleNamespace(status=Mock(side_effect=lambda key:self.tasks[key]))
        self.calls=[]
        self.app.submit_group=Mock(side_effect=self.submit_group)

    def submit_group(self,payload):
        self.calls.append(payload)
        model="Qwen" if "@qwen" in payload["prompt"].lower() else "Granite"
        key="GS-"+str(len(self.calls))
        self.tasks[key]={"task_id":key,"status":"queued",
            "result":{}}
        return {"task_ids":[key],"conversation_id":"conversation1"}

    def submit_codex(self,payload,*,group_auto_approval=False):
        key="CODEX-"+str(len(self.jobs)+1)
        self.jobs[key]={"id":key,"status":"pending_approval","answer":""}
        self.last_codex_payload=payload
        self.last_auto=group_auto_approval
        return self.jobs[key]

    def begin(self):
        return self.app.start_collaboration({"group_id":"room1","goal":"Build a safe Python inventory"})

    def test_proposal_first_no_automatic_file_changes(self):
        run=self.begin()
        self.assertEqual("proposal_pending",run["state"])
        self.assertEqual(1,len(self.calls))
        self.app.codex.submit.assert_not_called()
        self.assertIn("@qwen2.5-coder:3b",self.calls[0]["prompt"])
        self.assertEqual("project1",run["project_id"])
        with self.assertRaisesRegex(ValueError,"active collaboration"):
            self.begin()

    def test_owner_handoff_and_report_only_review(self):
        flow=self.begin()
        self.assertIn("waiting_for",self.app.advance_collaboration({"flow_id":flow["id"]}))
        self.assertFalse(self.jobs)
        self.tasks["GS-1"]["status"]="completed"
        self.tasks["GS-1"]["result"]={"answer":"Propose implementation steps; no edits."}
        result=self.app.advance_collaboration({"flow_id":flow["id"]})
        self.assertEqual("codex_pending",result["state"])
        self.assertEqual("workspace_write",self.last_codex_payload["scope"])
        self.assertEqual("project1",self.last_codex_payload["project_id"])
        self.assertFalse(self.last_auto)
        self.assertEqual("pending_approval",self.jobs["CODEX-1"]["status"])
        self.assertIn("waiting_for",self.app.advance_collaboration({"flow_id":flow["id"]}))
        self.assertEqual(1,len(self.calls))
        self.jobs["CODEX-1"].update(status="completed",answer="Updated inventory.py; unit tests passed")
        next_stage=self.app.advance_collaboration({"flow_id":flow["id"]})
        self.assertEqual("review_pending",next_stage["state"])
        self.assertIn("@granite4:3b",self.calls[-1]["prompt"])
        self.assertIn("cannot inspect the project files",self.calls[-1]["prompt"])
        self.assertIn("Updated inventory.py",self.calls[-1]["prompt"])
        self.assertIn("waiting_for",self.app.advance_collaboration({"flow_id":flow["id"]}))
        self.tasks["GS-2"]["status"]="completed"
        done=self.app.advance_collaboration({"flow_id":flow["id"]})
        self.assertEqual("completed",done["state"])
        self.assertEqual("completed",CollaborationLedger(self.path/"flows.json").read(flow["id"])["state"])
        self.assertEqual("completed",self.app.advance_collaboration({"flow_id":flow["id"]})["state"])

    def test_rejected_codex_marks_workflow_failed_and_allows_retry(self):
        flow=self.begin()
        self.tasks["GS-1"]["status"]="completed"
        self.app.advance_collaboration({"flow_id":flow["id"]})
        self.jobs["CODEX-1"]["status"]="rejected"
        result=self.app.advance_collaboration({"flow_id":flow["id"]})
        self.assertEqual("failed",result["state"])
        retry=self.begin()
        self.assertEqual("proposal_pending",retry["state"])

    def test_auto_code_requires_stored_codex_group_policy(self):
        self.group["approval_modes"]["codex"]="approve_for_me"
        flow=self.begin()
        self.tasks["GS-1"]["status"]="completed"
        self.app.advance_collaboration({"flow_id":flow["id"]})
        self.assertTrue(self.last_auto)

    def test_no_workflow_without_project_or_required_agents(self):
        self.group["project_id"]=None
        with self.assertRaisesRegex(ValueError,"registered project"):
            self.begin()
        self.group["project_id"]="project1"
        self.group["models"].remove("granite4:3b")
        with self.assertRaisesRegex(ValueError,"Qwen Coder, Codex and Granite"):
            self.begin()
        self.assertFalse(self.calls)

    def test_project_or_membership_changed_cannot_handoff(self):
        flow=self.begin()
        self.tasks["GS-1"]["status"]="completed"
        self.group["project_id"]="new-project"
        with self.assertRaisesRegex(ValueError,"project changed"):
            self.app.advance_collaboration({"flow_id":flow["id"]})
        self.group["project_id"]="project1"
        self.group["approval_modes"]["codex"]="disabled"
        with self.assertRaisesRegex(ValueError,"Codex was removed or disabled"):
            self.app.advance_collaboration({"flow_id":flow["id"]})
        self.app.codex.submit.assert_not_called()

    def test_private_persistence_rejects_corrupted_state(self):
        p=self.path/"bad.json"
        p.write_text('{"invalid":true}',encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"invalid"):
            CollaborationLedger(p)


if __name__=="__main__":
    unittest.main()
