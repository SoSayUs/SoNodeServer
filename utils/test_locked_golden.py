"""
Golden tests for the consensus-critical pure functions in utils/locked.py.

Nothing in utils/locked.py may change behavior without breaking agreement with the existing network, so
these pin CURRENT outputs. A failure here means "this change would diverge from nodes running the old code".
They do not need Django or a database: utils.utils / network.models are stubbed for the duration of the run.

Run from the project root:   python -m unittest utils.test_locked_golden -v

If a golden changes on purpose (a coordinated network upgrade), update it in the same commit and say why.
"""
import base64
import datetime
import hashlib
import json
import shutil
import subprocess
import sys
import types
import unittest
from unittest import mock

_patcher = None
L = None


def setUpModule():
    global _patcher, L
    utils_stub = types.ModuleType('utils.utils')
    utils_stub.prnt = lambda *a, **k: None
    utils_stub.is_id = lambda obj: False
    utils_stub.is_dt_string = lambda val: False   # sort_for_sign's datetime branch is covered via dt_to_string below
    network_stub = types.ModuleType('network.models')
    network_stub.Node = object
    _patcher = mock.patch.dict(sys.modules, {'utils.utils': utils_stub, 'network.models': network_stub})
    _patcher.start()
    import importlib
    import utils.locked as locked
    L = importlib.reload(locked)


def tearDownModule():
    _patcher.stop()


def H(b):
    return hashlib.sha256(b).digest()


def leaves(n):
    return [f'v{i}'.encode() for i in range(n)]


class MerkleTests(unittest.TestCase):
    def test_sha256_known_answer(self):
        self.assertEqual(L.sha256(b'abc').hex(), 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')

    def test_root_matches_independent_construction(self):
        a, b, c = leaves(3)
        self.assertEqual(L.merkle_root([a]), H(a))
        self.assertEqual(L.merkle_root([a, b]), H(H(a) + H(b)))
        # odd level: the last hash is duplicated
        self.assertEqual(L.merkle_root([a, b, c]), H(H(H(a) + H(b)) + H(H(c) + H(c))))

    def test_root_goldens(self):
        self.assertEqual(L.merkle_root(leaves(1)).hex(), '0270da4daac514f30bece5788a87ad7b800f59476d0d7e6f70d4b61fbc4f5e9e')
        self.assertEqual(L.merkle_root(leaves(2)).hex(), '4acae3d528d8f1f3afa00aee7b41b0c5031719a8ec0b410851e6eba7294102d7')
        self.assertEqual(L.merkle_root(leaves(3)).hex(), '59c0a5c02c51f88c64bfb0100740d05ab0d84cb0cbbfb5dc2bdcb8097d3c8638')
        self.assertEqual(L.merkle_root(leaves(5)).hex(), 'dbbf00a1ec4cd9ee972d932224286c4acc104fac3674443ed300fc502eb3a460')

    def test_proofs_verify_for_every_leaf(self):
        for n in range(1, 12):
            ls = leaves(n)
            root = L.merkle_root(ls)
            for i in range(n):
                self.assertTrue(L.verify_merkle_proof(ls[i], L.merkle_proof(ls, i), root), (n, i))

    def test_tampering_fails(self):
        ls = leaves(6)
        root = L.merkle_root(ls)
        proof = L.merkle_proof(ls, 2)
        self.assertFalse(L.verify_merkle_proof(b'other', proof, root))
        self.assertFalse(L.verify_merkle_proof(ls[2], proof, H(b'wrong root')))

    def test_empty_and_bad_index_raise(self):
        with self.assertRaises(ValueError):
            L.merkle_root([])
        with self.assertRaises(IndexError):
            L.merkle_proof(leaves(3), 3)

    def test_odd_duplicate_last_leaf_collision_is_current_behavior(self):
        # [a,b,c] and [a,b,c,c] hash to the same root. Pinned so nobody "fixes" it silently: it would fork the network.
        self.assertEqual(L.merkle_root(leaves(3)), L.merkle_root(leaves(3) + [leaves(3)[-1]]))


class SeededShuffleTests(unittest.TestCase):
    # First three outputs per seed, from an independent JS implementation (see CrossLanguageTests).
    RNG = {
        1:  [0.6270739405881613, 0.002735721180215478, 0.5274470399599522],
        42: [0.6011037519201636, 0.44829055899754167, 0.8524657934904099],
    }

    def test_int_seed_vectors(self):
        for seed, expected in self.RNG.items():
            r = L.mulberry32(seed)
            self.assertEqual([r(), r(), r()], expected, seed)

    def test_string_seed_is_fnv1a(self):
        # string seeds go through 32-bit FNV-1a before seeding
        def fnv(s):
            h = 0x811C9DC5
            for ch in s:
                h = ((h ^ ord(ch)) * 0x01000193) & 0xFFFFFFFF
            return h
        for s in ('a', 'sonet', 'block-123'):
            r1, r2 = L.mulberry32(s), L.mulberry32(fnv(s))
            self.assertEqual([r1(), r1(), r1()], [r2(), r2(), r2()])

    def test_shuffle_goldens(self):
        # exact shuffle vectors are checked against the JS reference in CrossLanguageTests; here: determinism + permutation
        a = L.cross_language_shuffle(list(range(50)), 'seed-1')
        self.assertEqual(a, L.cross_language_shuffle(list(range(50)), 'seed-1'))
        self.assertEqual(sorted(a), list(range(50)))
        self.assertNotEqual(a, L.cross_language_shuffle(list(range(50)), 'seed-2'))

    def test_shuffle_does_not_mutate_input(self):
        src = list(range(10))
        L.cross_language_shuffle(src, 'x')
        self.assertEqual(src, list(range(10)))

    def test_empty_and_single(self):
        self.assertEqual(L.cross_language_shuffle([], 's'), [])
        self.assertEqual(L.cross_language_shuffle([7], 's'), [7])


JS_REFERENCE = r"""
function seedFromString(s){let h=0x811C9DC5;for(const ch of s){h^=ch.codePointAt(0);h=Math.imul(h,0x01000193)>>>0;}return h>>>0;}
function mulberry32(a){return function(){a=(a+0x6D2B79F5)>>>0;let t=a;t=Math.imul(t^(t>>>15),t|1);t^=t+Math.imul(t^(t>>>7),t|61);return((t^(t>>>14))>>>0)/4294967296}}
function shuffle(arr,seed){const r=[...arr];const rng=mulberry32(typeof seed==='string'?seedFromString(seed):seed);for(let i=r.length-1;i>0;i--){const j=Math.floor(rng()*(i+1));[r[i],r[j]]=[r[j],r[i]];}return r;}
const out={rng:{},shuffle:{}};
for(const s of ['a','sonet','block-123']){const r=mulberry32(seedFromString(s));out.rng[s]=[r(),r(),r()];}
for(const s of [1,42]){const r=mulberry32(s);out.rng[String(s)]=[r(),r(),r()];}
out.shuffle['sonet']=shuffle([...Array(10).keys()],'sonet');
out.shuffle['block-123']=shuffle([...Array(7).keys()].map(String),'block-123');
out.shuffle['big']=shuffle([...Array(200).keys()],'epoch-9');
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which('node'), 'node not installed')
class CrossLanguageTests(unittest.TestCase):
    """Node assignment must agree between this server and JS clients: compare against an independent JS implementation."""

    @classmethod
    def setUpClass(cls):
        out = subprocess.run(['node', '-e', JS_REFERENCE], capture_output=True, text=True, check=True).stdout
        cls.ref = json.loads(out)

    def test_matches_js_reference(self):
        for key, expected in self.ref['rng'].items():
            seed = int(key) if key.isdigit() else key
            r = L.mulberry32(seed)
            self.assertEqual([r(), r(), r()], expected, key)
        self.assertEqual(L.cross_language_shuffle(list(range(10)), 'sonet'), self.ref['shuffle']['sonet'])
        self.assertEqual(L.cross_language_shuffle([str(i) for i in range(7)], 'block-123'), self.ref['shuffle']['block-123'])
        self.assertEqual(L.cross_language_shuffle(list(range(200)), 'epoch-9'), self.ref['shuffle']['big'])


class PositionSortTests(unittest.TestCase):
    ACTIVE = {i: f'N{i}' for i in range(1, 11) if i not in (3, 7)}

    def test_goldens(self):
        ps = lambda s, p, m: L.position_sort(s, p, self.ACTIVE, m, max_pos=10)
        self.assertEqual(ps(1, 3, 3), ['N4', 'N10', 'N6'])
        self.assertEqual(ps(5, 7, 4), ['N2', 'N9', 'N6', 'N10'])
        self.assertEqual(ps(9, 10, 8), ['N9', 'N10', 'N1', 'N2', 'N4', 'N5', 'N6', 'N8'])
        self.assertEqual(ps(2, -4, 3), ['N8', 'N5', 'N2'])
        self.assertEqual(ps(10, 1, 10), ['N1', 'N2', 'N4', 'N5', 'N6', 'N8', 'N9', 'N10'])

    def test_never_repeats_and_respects_count(self):
        for pattern in range(-20, 40):
            out = L.position_sort(4, pattern, self.ACTIVE, 5, max_pos=10)
            self.assertEqual(len(out), len(set(out)))
            self.assertLessEqual(len(out), 5)

    def test_nonpositive_max_pos_is_empty(self):
        self.assertEqual(L.position_sort(1, 3, self.ACTIVE, 3, max_pos=0), [])


class SigningFormTests(unittest.TestCase):
    def test_sort_dict(self):
        self.assertEqual(json.dumps(L.sort_dict('{"b":1,"a":{"z":[{"y":1,"x":2}],"c":null}}')),
                         '{"a": {"c": null, "z": [{"x": 2, "y": 1}]}, "b": 1}')

    def test_sort_for_sign_golden(self):
        d = {'Zeta': True, 'alpha': None, 'id': 'X1', 'signed': 'SIG', 'beta': [],
             'Gamma': {'n': None, 'B': False, 'a': [1, None]}, 'list': [True, 's']}
        self.assertEqual(json.dumps(L.sort_for_sign(d)),
                         '{"id": "X1", "alpha": "Val:N", "beta": "Val:N", "Gamma": {"a": [1, "Val:N"], "B": "False", "n": "Val:N"}, '
                         '"list": ["True", "s"], "Zeta": "True", "signed": "SIG"}')

    def test_sort_for_sign_none_handling(self):
        self.assertEqual(L.sort_for_sign({'a': None, 'b': []}, none_is_string=False), {'a': None, 'b': 'Val:N'})

    def test_id_first_signed_last_and_case_insensitive_order(self):
        keys = list(L.sort_for_sign({'b': 1, 'signed': 's', 'A': 2, 'id': 'i', 'c': 3}).keys())
        self.assertEqual(keys, ['id', 'A', 'b', 'c', 'signed'])

    def test_dt_to_string(self):
        # NOTE: the comment in locked.py says milliseconds, but [:-4] keeps only TWO fractional digits (truncated, not rounded).
        # That is what every node currently signs, so it is pinned as-is. Do not "fix" it without a coordinated upgrade.
        self.assertEqual(L.dt_to_string('2024-01-02T03:04:05.123456+00:00'), '2024-01-02T03:04:05.12Z')
        self.assertEqual(L.dt_to_string(datetime.datetime(2024, 1, 2, 3, 4, 5, 678901, tzinfo=datetime.timezone.utc)), '2024-01-02T03:04:05.67Z')
        self.assertEqual(L.dt_to_string('2024-01-02T03:04:05-05:00'), '2024-01-02T08:04:05.00Z')
        self.assertEqual(L.dt_to_string(datetime.datetime(2024, 1, 2, 3, 4, 5)), '2024-01-02T03:04:05.00Z')  # naive == UTC
        self.assertEqual(L.dt_to_string('not-a-date'), 'not-a-date')
        self.assertEqual(L.dt_to_string(''), '')

    def test_base64url(self):
        self.assertEqual(L.bytes_to_base64url(b'\xfb\xff\xfe?'), '-__-Pw')
        self.assertEqual(L.base64url_to_bytes('-__-Pw'), b'\xfb\xff\xfe?')
        raw = bytes(range(256))
        self.assertEqual(L.base64url_to_bytes(L.bytes_to_base64url(raw)), raw)
        self.assertEqual(L.bytes_to_base64url(raw), base64.urlsafe_b64encode(raw).decode().rstrip('='))


if __name__ == '__main__':
    unittest.main()
