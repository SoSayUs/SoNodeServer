"""
Regression tests for utils.models.compute_node_trust. No Django or DB needed: the function is extracted from
utils/models.py and run against in-memory fakes for Node / NodeReview / the compute_* helpers.

Run from the project root:   python -m unittest utils.test_compute_node_trust -v
"""
import ast
import contextlib
import datetime
import math
import os
import sys
import types
import unittest
from unittest import mock

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models.py')
NOW = datetime.datetime.now(datetime.timezone.utc)


class FakeNode:
    def __init__(self, nid, trust=0.5):
        self.id, self.trust_score, self.influence_score, self.score_dt = nid, trust, 0.5, None
        self.suspended_dt, self.activeNode = None, False

    def save(self, *a, **k):
        # Node.save() silently writes nothing for locked nodes unless called with a whitelisted update_fields
        if k.get('update_fields') not in (['suspended_dt'], ['activeNode'], ['expelled_dt']):
            raise AssertionError('node.save() would be skipped for a locked node')


class QS(list):
    def only(self, *a, **k): return self
    def order_by(self, *a, **k): return self
    def exists(self): return True


def review(target, creator, resp=1.0, job=0.5, trust=0.5, inter=40):
    return types.SimpleNamespace(TargetNode_obj_id=target, CreatorNode_obj_id=creator, response_success=resp, job_success=job,
                                 trust_score=trust, interactions=inter, failures=None,
                                 lastUpdate=NOW - datetime.timedelta(minutes=10))


def run(nodes, reviews, job=None, self_id='N0'):
    calls = {'node_bulk': [], 'review_bulk': []}

    class NodeM:
        class objects:
            exclude = staticmethod(lambda **k: QS(nodes))
            filter = staticmethod(lambda **k: QS(nodes))
            bulk_update = staticmethod(lambda items, fields: calls['node_bulk'].append((list(items), fields)))

    class ReviewM:
        class objects:
            filter = staticmethod(lambda *a, **k: QS(reviews))
            bulk_update = staticmethod(lambda items, fields: calls['review_bulk'].append((list(items), fields)))

    net = types.ModuleType('network.models')
    net.Node, net.NodeReview, net.recent_failure_range, net.recent_failure_count = NodeM, ReviewM, 2, 140
    dj = types.ModuleType('django.db')
    dj.transaction = types.SimpleNamespace(atomic=contextlib.contextmanager(lambda: (yield)))
    uu = types.ModuleType('utils.utils')
    uu.self_is_active = lambda *a: None
    with open(SRC) as f:
        tree = ast.parse(f.read())
    fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'compute_node_trust'][0]
    ns = dict(prnt=lambda *a, **k: None, datetime=datetime, now_utc=lambda: NOW, round_time=lambda d, **k: d,
              get_operator_obj=lambda k: self_id, string_to_dt=lambda s: NOW, request_items=lambda *a, **k: None,
              compute_block_success=lambda *a: {}, compute_consensus_alignment=lambda *a: {},
              compute_job_success=lambda *a: dict(job or {}), compute_reveal_success=lambda *a: {},
              compute_creator_reveal_violations=lambda *a: {})
    with mock.patch.dict(sys.modules, {'network.models': net, 'django.db': dj, 'utils.utils': uu}):
        exec(compile(ast.Module(body=[fn], type_ignores=[]), 'compute_node_trust', 'exec'), ns)
        ns['compute_node_trust']()
    return calls


class ComputeNodeTrustTests(unittest.TestCase):
    def test_scores_are_persisted_without_node_save(self):
        nodes = [FakeNode(f'N{i}') for i in range(4)]
        revs = [review(t, c, job=1.0) for t in ('N1', 'N2', 'N3') for c in ('N0', 'N1', 'N2', 'N3') if c != t]
        calls = run(nodes, revs)  # FakeNode.save raises if the old node.save() loop comes back
        items, fields = calls['node_bulk'][0]
        self.assertEqual(fields, ['trust_score', 'influence_score', 'score_dt'])
        self.assertEqual(len(items), 4)
        self.assertGreater(nodes[1].trust_score, 0.5)
        self.assertTrue(all(abs(n.influence_score - math.sqrt(n.trust_score)) < 1e-12 for n in nodes))
        self.assertTrue(all(n.score_dt for n in nodes))

    def test_node_without_enough_interactions_stays_at_default(self):
        nodes = [FakeNode(f'N{i}') for i in range(3)]
        run(nodes, [review('N1', 'N0', inter=9), review('N1', 'N2', inter=9)])
        self.assertEqual(nodes[1].trust_score, 0.5)

    def test_targets_job_result_reaches_its_score(self):
        nodes = [FakeNode(f'N{i}') for i in range(4)]
        revs = [review('N1', c, job=1.0) for c in ('N0', 'N2', 'N3')] + [review('N2', c, job=0.0) for c in ('N0', 'N1', 'N3')]
        run(nodes, revs)
        self.assertGreater(nodes[1].trust_score, 0.5)
        self.assertLess(nodes[2].trust_score, 0.5)

    def _target_trust(self, reviewer_trusts, given):
        nodes = [FakeNode('N0'), FakeNode('T'), FakeNode('A', reviewer_trusts[0]), FakeNode('B', reviewer_trusts[1])]
        run(nodes, [review('T', 'A', resp=1.0, trust=given[0]), review('T', 'B', resp=0.0, trust=given[1])])
        return nodes[1].trust_score

    def test_reviewer_weight_follows_reviewers_own_trust(self):
        self.assertGreater(self._target_trust((0.9, 0.1), (0.5, 0.5)), self._target_trust((0.1, 0.9), (0.5, 0.5)))

    def test_trust_a_reviewer_gave_the_target_does_not_change_weights(self):
        self.assertAlmostEqual(self._target_trust((0.5, 0.5), (0.5, 0.5)), self._target_trust((0.5, 0.5), (0.99, 0.01)), places=12)

    def test_misaligned_reviewers_count_less(self):
        def t(job):
            nodes = [FakeNode('N0'), FakeNode('T'), FakeNode('A'), FakeNode('B')]
            run(nodes, [review('T', 'A', resp=1.0), review('T', 'B', resp=0.0)], job=job)
            return nodes[1].trust_score
        self.assertGreater(t({'A': 1.0, 'B': 0.0}), t({'A': 0.0, 'B': 1.0}))

    def test_own_reviews_get_trust_written_back_and_interactions_reset(self):
        nodes = [FakeNode(f'N{i}') for i in range(3)]
        calls = run(nodes, [review('N1', 'N0'), review('N1', 'N2')])
        updated, fields = calls['review_bulk'][0]
        self.assertEqual(fields, ['trust_score', 'interactions'])
        self.assertEqual([u.interactions for u in updated], [0])
        self.assertAlmostEqual(updated[0].trust_score, nodes[1].trust_score)


if __name__ == '__main__':
    unittest.main()
