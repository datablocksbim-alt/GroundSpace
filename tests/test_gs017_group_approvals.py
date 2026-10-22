"""GS-017: group-level per-model approval enforcement and owner decisions."""
from __future__ import annotations

import copy
import json
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ground_space.workspaces import WorkspaceRegistry
from ground_space.webapp import GroundSpaceApp


class FakeQueue:
    def __init__(self, tasks):
        self.tasks=tasks
    def transition(self, task, status, **updates):
        assert status=="queued"
        updated={**task, **updates}
        self.tasks[task["task_id"]]=updated
        return copy.deepcopy(updated)


class FakeAdministrator:
    def __init__(self):
        self.tasks={}
        self.queue=FakeQueue(self.tasks)
        self.audit=SimpleNamespace(append=Mock())
    def submit(self,payload,*,worker_id,required_permissions,execution_timeout_seconds,approved,approval_source):
        id="GS-"+str(len(self.tasks)+1)
        task={"task_id":id,"source":"ground_space","status":"queued",
              "payload":dict(payload),"requested_worker":worker_id,
              "required_permissions":list(required_permissions),
              "approval":{"status":"approved" if approved else "pending",
                          "owner":approval_source or "owner"}}
        self.tasks[id]=task
        return copy.deepcopy(task)
    def status(self, task_id):
        return copy.deepcopy(self.tasks[task_id])
    def approve(self, task_id, *, owner):
        record=self.tasks[task_id]
        record["approval"]={"status":"approved","owner":owner}
        return copy.deepcopy(record)


class GroupApprovalTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir=Path(tmp.name)
        self.registry=WorkspaceRegistry(self.dir / "private", [self.dir])
        self.models=["qwen2.5-coder:3b","granite4:3b"]
        self.app=GroundSpaceApp.__new__(GroundSpaceApp)
        self.app.workspaces=self.registry
        self.app.lock=threading.RLock()
        self.app.group_dispatch_lock=threading.Lock()
        self.app.ollama_endpoint="http://127.0.0.1:1"
        self.app.registered_models=list(self.models)
        self.app.codex=SimpleNamespace(is_registered=Mock(return_value=False))
        self.app.administrator=FakeAdministrator()
        self.app.conversations={}
        self.app.history_path=self.dir/"private"/"conversations.json"
        self.app._register_worker=Mock()
        self.app.worker_id=GroundSpaceApp.worker_id

    def create(self, modes=None):
        body={"name":"Development","models":self.models,"project_id":None}
        if modes is not None: body["approval_modes"]=modes
        return self.app.create_group(body)

    def test_legacy_group_defaults_to_previous_automatic_readonly_behavior(self):
        group=self.create()
        self.assertEqual({model:"approve_for_me" for model in self.models},group["approval_modes"])
        with patch("ground_space.webapp.probe_ollama",return_value={"available":False,"models":[]}),patch("ground_space.webapp.threading.Thread") as threads:
            res=self.app.submit_group({"group_id":group["id"],"prompt":"Hello"})
        self.assertEqual(1,len(res["task_ids"]))
        task=self.app.administrator.status(res["task_ids"][0])
        self.assertEqual("approved",task["approval"]["status"])
        self.assertEqual(["read","propose"],task["required_permissions"])
        threads.assert_called_once()

    def test_individual_modes_persist_and_are_per_group(self):
        first=self.create({"qwen2.5-coder:3b":"manual","granite4:3b":"disabled"})
        second=self.create({"qwen2.5-coder:3b":"approve_for_me","granite4:3b":"manual"})
        restored=WorkspaceRegistry(self.dir/"private", [self.dir])
        self.assertEqual("manual",restored.get_group(first["id"])["approval_modes"][self.models[0]])
        self.assertEqual("approve_for_me",restored.get_group(second["id"])["approval_modes"][self.models[0]])

    def test_manual_group_reply_waits_until_owner_approves(self):
        group=self.create({"qwen2.5-coder:3b":"manual","granite4:3b":"approve_for_me"})
        with patch("ground_space.webapp.probe_ollama",return_value={"available":False,"models":[]}),patch("ground_space.webapp.threading.Thread") as threads:
            res=self.app.submit_group({"group_id":group["id"],"prompt":"How are we doing?"})
            threads.assert_not_called()
            task=self.app.administrator.status(res["task_ids"][0])
            self.assertEqual("pending",task["approval"]["status"])
            updated=self.app.decide_group_task({"group_id":group["id"],"task_id":task["task_id"]},approve=True)
            threads.assert_called_once()
            self.assertEqual("approved",updated["approval"]["status"])
            with self.assertRaisesRegex(ValueError,"pending"):
                self.app.decide_group_task({"group_id":group["id"],"task_id":task["task_id"]},approve=True)

    def test_rejection_is_persisted_and_cannot_be_executed(self):
        group=self.create({"qwen2.5-coder:3b":"manual"})
        with patch("ground_space.webapp.probe_ollama",return_value={"available":False,"models":[]}),patch("ground_space.webapp.threading.Thread") as threads:
            res=self.app.submit_group({"group_id":group["id"],"prompt":"Check"})
            item=self.app.decide_group_task({"group_id":group["id"],"task_id":res["task_ids"][0]},approve=False)
            self.assertEqual("rejected",item["approval"]["status"])
            threads.assert_not_called()
            with self.assertRaisesRegex(ValueError,"pending"):
                self.app.decide_group_task({"group_id":group["id"],"task_id":res["task_ids"][0]},approve=True)

    def test_disabled_bot_blocks_routed_replies(self):
        group=self.create({"qwen2.5-coder:3b":"disabled"})
        with patch("ground_space.webapp.probe_ollama",return_value={"available":False,"models":[]}):
            with self.assertRaisesRegex(ValueError,"disabled"):
                self.app.submit_group({"group_id":group["id"],"prompt":"Hello"})
        self.assertEqual({},self.app.administrator.tasks)

    def test_cannot_approve_another_groups_task_or_write_task(self):
        group=self.create({"qwen2.5-coder:3b":"manual"})
        other=self.create({"qwen2.5-coder:3b":"manual"})
        with patch("ground_space.webapp.probe_ollama",return_value={"available":False,"models":[]}),patch("ground_space.webapp.threading.Thread"):
            res=self.app.submit_group({"group_id":group["id"],"prompt":"Review"})
        id=res["task_ids"][0]
        with self.assertRaisesRegex(ValueError,"Only a pending"):
            self.app.decide_group_task({"group_id":other["id"],"task_id":id},approve=True)
        self.app.administrator.tasks[id]["required_permissions"]=["read","write"]
        with self.assertRaisesRegex(ValueError,"Only a pending"):
            self.app.decide_group_task({"group_id":group["id"],"task_id":id},approve=True)

    def test_validation_rejects_foreign_bot_and_unsafe_policy(self):
        with self.assertRaisesRegex(ValueError,"must match"):
            self.create({"unregistered:7b":"approve_for_me"})
        with self.assertRaisesRegex(ValueError,"Invalid group bot"):
            self.create({"qwen2.5-coder:3b":"auto_execute"})
        self.assertFalse(self.registry.groups)

    def test_update_keeps_previous_member_policy_and_handles_new_member(self):
        base=self.registry.create_group("Demo",[self.models[0]],None,self.models,
                                        {self.models[0]:"manual"})
        updated=self.registry.update_group(base["id"],self.models,None,self.models)
        self.assertEqual("manual",updated["approval_modes"][self.models[0]])
        self.assertEqual("approve_for_me",updated["approval_modes"][self.models[1]])
        self.assertEqual(["read","propose"],self.app.administrator.submit(
            {"model":self.models[0]},worker_id="x",required_permissions=["read","propose"],
            execution_timeout_seconds=5,approved=True,approval_source="test")["required_permissions"])


if __name__=="__main__":
    unittest.main()
