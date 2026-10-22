"""Independent QW-002 acceptance tests, executed ONLY inside an isolated container.

The candidate must be mounted as /work/schedule_tasks.py. Never import or run
candidate code from the Ground Space host process.
"""
import copy
import unittest
from schedule_tasks import schedule_tasks


def task(name, priority, dependencies=None):
    return {"id": name, "priority": priority, "depends_on": dependencies or []}


class SchedulerContract(unittest.TestCase):
    def test_dependencies_vs_priority(self):
        self.assertEqual(["C", "A", "B", "D"], schedule_tasks([
            task("A", 2), task("B", 5, ["A"]),
            task("C", 4), task("D", 3, ["B", "C"]),
        ]))

    def test_forward_dependency(self):
        self.assertEqual(["A", "B"], schedule_tasks([task("B", 9, ["A"]), task("A", 1)]))

    def test_alphabetical_ties(self):
        self.assertEqual(["A", "B", "Z"], schedule_tasks([task("Z", 3), task("B", 3), task("A", 3)]))

    def test_duplicate_id(self):
        with self.assertRaises(ValueError):
            schedule_tasks([task("A", 1), task("A", 2)])

    def test_missing_dependency(self):
        with self.assertRaises(ValueError):
            schedule_tasks([task("A", 1, ["absent"])])

    def test_cycle(self):
        with self.assertRaises(ValueError):
            schedule_tasks([task("A", 1, ["B"]), task("B", 2, ["A"])])

    def test_self_cycle(self):
        with self.assertRaises(ValueError):
            schedule_tasks([task("A", 1, ["A"])])

    def test_does_not_mutate(self):
        tasks = [task("A", 1), task("B", 2, ["A"])]
        original = copy.deepcopy(tasks)
        self.assertEqual(["A", "B"], schedule_tasks(tasks))
        self.assertEqual(original, tasks)

    def test_empty(self):
        self.assertEqual([], schedule_tasks([]))


if __name__ == "__main__":
    unittest.main()
