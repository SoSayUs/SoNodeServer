"""
Salt commit/reveal bookkeeping used for the NodeReview.reveal_success metric, plus a diagnostic report.

tally_salts() is pure (no Django) so it can be unit-tested; salt_report() is the ORM-side tool: run it on each node
(`python manage.py shell`, then `from utils.salt_report import salt_report; salt_report(3)`), because every number
depends on when THIS node received a commit/reveal, and RevealData.save_requirements() silently drops reveals that
arrive outside its window.
"""
import datetime

TEN_MIN = datetime.timedelta(minutes=10)


def commit_is_eligible(c):
    """
    Same rule RevealData.save_requirements() applies to the commit: it must have reached this node within 10 minutes
    of its created time. A commit received later can never be matched with an acceptable reveal here, so it says
    nothing about the target and must not count against it.
    """
    return c.created is not None and c.added_to_node is not None and c.created <= c.added_to_node < c.created + TEN_MIN


def tally_salts(commits, reveals_by_created, hash_fn, creator_made_block):
    """
    commits:            iterable of CommitData-like (created, added_to_node, hash)
    reveals_by_created: {created: RevealData-like (value)} for the same target
    hash_fn:            quick_hash
    creator_made_block: callable(dt) -> bool, did the target create a block at dt (commit.created + 20 min)
    Returns (committed, revealed, violations).
    """
    committed = revealed = violations = 0
    for c in commits:
        if not commit_is_eligible(c):
            continue
        committed += 1
        rv = reveals_by_created.get(c.created)
        if rv is not None and c.hash == hash_fn(rv.value):
            revealed += 1
        elif creator_made_block(c.created + 2 * TEN_MIN):
            violations += 1
    return committed, revealed, violations


def response_success_ratio(response_times, failures, interactions, window_start, cap, parse_dt):
    """
    NodeReview.response_success = successful accesses / interactions for the period since the last reset.
    response_times keeps at most `cap` entries (oldest dropped) while `interactions` keeps counting, so once the log is
    full the successes are only a recent slice. Then count only the failures inside that same slice, otherwise a
    healthy, busy node reads cap/interactions. 0.5 (neutral) when there is nothing to measure.
    """
    entries = []
    for k in (response_times or {}):
        try:
            entries.append(parse_dt(k))
        except Exception:
            pass
    successes = sum(1 for d in entries if d >= window_start)
    if not interactions or interactions < successes:
        return 0.5
    if len(entries) >= cap and interactions > successes:
        oldest = min(entries)
        fails = 0
        for k in (failures or {}):
            try:
                if parse_dt(k) >= oldest:
                    fails += 1
            except Exception:
                pass
        interactions = successes + fails
    return successes / interactions if interactions else 0.5


def block_report(hours=3):
    """Per target: blocks created in the window and, for rejected ones, why (Block.notes fail_position / fail_dt)."""
    from network.models import Node, Block
    from utils.utils import now_utc, round_time
    end = round_time(now_utc(), dir='down', amount='hour')
    start = end - datetime.timedelta(hours=hours)
    for node in Node.objects.exclude(activated_dt=None):
        blocks = list(Block.objects.filter(CreatorNode_obj=node, DateTime__gte=start, DateTime__lt=end).order_by('DateTime').defer('data', 'extraData'))
        if not blocks:
            continue
        ok = sum(1 for b in blocks if b.validated is True)
        bad = [b for b in blocks if b.validated is False]
        pending = sum(1 for b in blocks if b.validated is None)
        print(f"{str(node.id)[:14]}  blocks={len(blocks)} validated={ok} rejected={len(bad)} pending(not counted)={pending}")
        for b in bad:
            n = b.notes or {}
            print(f"  {b.DateTime:%m-%d %H:%M} chain={str(b.networkChain)[:10]} idx={b.index} fail_position={n.get('fail_position')} fail_dt={n.get('fail_dt')}")


def salt_report(hours=3):
    """Per target, per commit: what THIS node saw. Prints one line per target and a reason for every unmatched commit."""
    from network.models import Node, CommitData, RevealData
    from utils.utils import now_utc, round_time
    end = round_time(now_utc(), dir='down', amount='hour')
    start = end - datetime.timedelta(hours=hours)
    for node in Node.objects.exclude(activated_dt=None):
        commits = list(CommitData.objects.filter(Node_obj=node, dataType='salt', created__gte=start, created__lt=end).order_by('created'))
        reveals = {r.created: r for r in RevealData.objects.filter(Node_obj=node, dataType='salt', created__gte=start, created__lt=end)}
        ok = late_commit = missing = 0
        notes = []
        for c in commits:
            commit_lag = (c.added_to_node - c.created).total_seconds()
            rv = reveals.get(c.created)
            if not commit_is_eligible(c):
                late_commit += 1
                notes.append(f"  {c.created:%H:%M} commit received {commit_lag:.0f}s after created (>=600: this node was late/offline, reveal can't be accepted)")
            elif rv is None:
                missing += 1
                notes.append(f"  {c.created:%H:%M} no reveal stored here (never arrived, or save_requirements rejected it: grep the log for 'reveal rejected')")
            else:
                ok += 1
                reveal_lag = (rv.added_to_node - c.created).total_seconds()
                if not 600 < reveal_lag < 1200:
                    notes.append(f"  {c.created:%H:%M} reveal stored {reveal_lag:.0f}s after created (valid window is 600..1200s)")
        print(f"{str(node.id)[:14]}  commits={len(commits)} revealed={ok} missing={missing} late_commit={late_commit}")
        for n in notes:
            print(n)
