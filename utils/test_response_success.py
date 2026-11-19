"""Run from the project root:   python -m unittest utils.test_response_success -v   (no Django needed)"""
import datetime
import unittest
from utils.salt_report import response_success_ratio

T0 = datetime.datetime(2026, 1, 1, 10, 0)
parse = lambda k: k


def times(n, start=T0):
    return {start + datetime.timedelta(seconds=i): {'time': None} for i in range(n)}


class ResponseSuccessRatio(unittest.TestCase):
    def test_no_interactions_is_neutral(self):
        self.assertEqual(response_success_ratio({}, {}, 0, T0, 150, parse), 0.5)

    def test_all_successes(self):
        self.assertEqual(response_success_ratio(times(25), {}, 25, T0, 150, parse), 1.0)

    def test_failures_count_against(self):
        self.assertEqual(response_success_ratio(times(20), {}, 25, T0, 150, parse), 0.8)

    def test_full_log_does_not_undercount_busy_healthy_node(self):
        # 400 interactions, log trimmed to the latest 150, no failures: must be 1.0 (was 150/400)
        self.assertEqual(response_success_ratio(times(150), {}, 400, T0, 150, parse), 1.0)

    def test_full_log_counts_only_failures_inside_the_slice(self):
        f = {T0 - datetime.timedelta(seconds=5): 'old', T0 + datetime.timedelta(seconds=10): 'in', T0 + datetime.timedelta(seconds=20): 'in2'}
        self.assertAlmostEqual(response_success_ratio(times(150), f, 400, T0, 150, parse), 150 / 152)


if __name__ == '__main__':
    unittest.main()
