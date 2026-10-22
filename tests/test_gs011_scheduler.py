"""QW-002 reference benchmark tests; all cases are deterministic and offline."""
import copy
import unittest

from examples.schedule_tasks import schedule_tasks


class ScheduleTasksTests(unittest.TestCase):
    def test_priority_obeys_dependencies(self):
        tasks = [
            {"id": "A", "priority": 2, "depends_on": []},
            {"id": "B", "priority": 5, "depends_on": ["A"]},
            {"id": "C", "priority": 4, "depends_on": []},
            {"id": "D", "priority": 3, "depends_on": ["B", "C"]},
        ]
        self.assertEqual(["C", "A", "B", "D"], schedule_tasks(tasks))

    def test_forward_dependencies_are_valid(self):
        self.assertEqual(["A", "B"], schedule_tasks([
            {"id": "B", "priority": 50, "depends_on": ["A"]},
            {"id": "A", "priority": 1, "depends_on": []},
        ]))

    def test_priority_ties_alphabetical(self):
        self.assertEqual(["A", "B", "C"], schedule_tasks([
            {"id": n, "priority": 3, "depends_on": []} for n in ("C", "B", "A")
        ]))

    def test_duplicate_id_raises(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            schedule_tasks([{"id": "A", "priority": 1, "depends_on": []}] * 2)

    def test_missing_dependency_raises(self):
        with self.assertRaises(ValueError):
            schedule_tasks([{"id": "A", "priority": 1, "depends_on": ["X"]}])

    def test_cycle_raises(self):
        with self.assertRaises(ValueError):
            schedule_tasks([
                {"id": "A", "priority": 1, "depends_on": ["B"]},
                {"id": "B", "priority": 2, "depends_on": ["A"]},
            ])

    def test_self_cycle_raises(self):
        with self.assertRaises(ValueError):
            schedule_tasks([{"id": "A", "priority": 1, "depends_on": ["A"]}])

    def test_does_not_mutate_input(self):
        tasks = [
            {"id": "A", "priority": 1, "depends_on": []},
            {"id": "B", "priority": 2, "depends_on": ["A", "A"]},
        ]
        unchanged = copy.deepcopy(tasks)
        self.assertEqual(["A", "B"], schedule_tasks(tasks))
        self.assertEqual(unchanged, tasks)

    def test_empty_task_set(self):
        self.assertEqual([], schedule_tasks([]))

    def test_invalid_records_raise_value_error(self):
        for tasks in (
            [{"id": [], "priority": 1, "depends_on": []}],
            [{"id": "A", "priority": True, "depends_on": []}],
            [{"id": "A", "priority": 1, "depends_on": "B"}],
            [{"id": "A", "priority": "5", "depends_on": []}],
            [None],
        ):
            with self.subTest(tasks=tasks), self.assertRaises(ValueError):
                schedule_tasks(tasks)


if __name__ == "__main__":
    unittest.main()
