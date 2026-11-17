import datetime
import types
import unittest

from utils.salt_report import commit_is_eligible, tally_salts

T0 = datetime.datetime(2026, 11, 16, 14, 30, tzinfo=datetime.timezone.utc)
MIN = datetime.timedelta(minutes=1)


def commit(created=T0, lag_s=3, h='H'):
    return types.SimpleNamespace(created=created, added_to_node=created + datetime.timedelta(seconds=lag_s), hash=h)


def reveal(value='v'):
    return types.SimpleNamespace(value=value)


hash_fn = lambda v: 'H' if v == 'v' else 'other'
no_block = lambda dt: False


class TallySaltsTests(unittest.TestCase):
    def test_matching_reveal_counts(self):
        self.assertEqual(tally_salts([commit()], {T0: reveal()}, hash_fn, no_block), (1, 1, 0))

    def test_missing_reveal_is_unrevealed_but_not_a_violation_without_a_block(self):
        self.assertEqual(tally_salts([commit()], {}, hash_fn, no_block), (1, 0, 0))

    def test_hash_mismatch_is_unrevealed(self):
        self.assertEqual(tally_salts([commit()], {T0: reveal('wrong')}, hash_fn, no_block), (1, 0, 0))

    def test_violation_needs_the_target_to_have_created_the_block_20_min_after_the_commit(self):
        asked = []
        def made_block(dt):
            asked.append(dt)
            return True
        self.assertEqual(tally_salts([commit()], {}, hash_fn, made_block), (1, 0, 1))
        self.assertEqual(asked, [T0 + 20 * MIN])

    def test_revealed_commit_never_asks_about_blocks(self):
        def boom(dt):
            raise AssertionError('should not be called')
        self.assertEqual(tally_salts([commit()], {T0: reveal()}, hash_fn, boom), (1, 1, 0))

    def test_commit_received_late_is_ignored_even_if_the_target_made_a_block(self):
        # this node got the commit 11 min after it was created: it can never accept the reveal, so it proves nothing
        late = commit(lag_s=11 * 60)
        self.assertFalse(commit_is_eligible(late))
        self.assertEqual(tally_salts([late], {}, hash_fn, lambda dt: True), (0, 0, 0))

    def test_commit_received_before_it_was_created_is_ignored(self):
        self.assertEqual(tally_salts([commit(lag_s=-5)], {}, hash_fn, no_block), (0, 0, 0))

    def test_commit_received_just_inside_the_window_counts(self):
        self.assertTrue(commit_is_eligible(commit(lag_s=599)))
        self.assertFalse(commit_is_eligible(commit(lag_s=600)))

    def test_no_commits(self):
        self.assertEqual(tally_salts([], {}, hash_fn, no_block), (0, 0, 0))

    def test_two_ticks_in_one_hour(self):
        t1 = T0 - 30 * MIN
        self.assertEqual(tally_salts([commit(t1), commit(T0)], {t1: reveal(), T0: reveal()}, hash_fn, no_block), (2, 2, 0))
        self.assertEqual(tally_salts([commit(t1), commit(T0)], {t1: reveal()}, hash_fn, no_block), (2, 1, 0))


if __name__ == '__main__':
    unittest.main()
