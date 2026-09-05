import unittest

from scripts.fetch_sources import coverage_degraded


class CoverageThresholdTests(unittest.TestCase):
    def test_no_attempts_is_not_degraded(self):
        self.assertFalse(coverage_degraded(0, 0))

    def test_half_success_is_not_degraded(self):
        self.assertFalse(coverage_degraded(10, 5))

    def test_just_under_half_is_degraded(self):
        self.assertTrue(coverage_degraded(10, 4))

    def test_single_total_failure_is_degraded(self):
        self.assertTrue(coverage_degraded(1, 0))

    def test_majority_success_is_not_degraded(self):
        self.assertFalse(coverage_degraded(3, 2))


if __name__ == "__main__":
    unittest.main()
