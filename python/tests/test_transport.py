"""Queueing and delivery isolation."""

import threading

from blare.transport import QUEUE_SIZE, Transport
from helpers import RecordingSink


def test_events_reach_every_sink():
    first, second = RecordingSink(), RecordingSink()
    transport = Transport([first, second])
    transport.submit({"title": "boom"})
    assert transport.flush(5) is True
    assert first.payloads == second.payloads == [{"title": "boom"}]
    transport.close()


def test_one_broken_sink_does_not_stop_the_others():
    """A dead Discord webhook must not cost you the Slack alert."""
    broken, working = RecordingSink(raises=True), RecordingSink()
    transport = Transport([broken, working])
    transport.submit({"title": "boom"})
    transport.flush(5)
    assert working.payloads == [{"title": "boom"}]
    assert transport.failed == 1
    transport.close()


def test_a_failing_sink_is_counted_not_raised():
    transport = Transport([RecordingSink(fail=True)])
    transport.submit({"title": "boom"})
    transport.flush(5)
    assert transport.failed == 1
    assert transport.delivered == 0
    transport.close()


def test_a_full_queue_drops_rather_than_blocks():
    """Back-pressure from a chat webhook must never reach production traffic."""
    release = threading.Event()

    class BlockingSink(RecordingSink):
        def send(self, payload):
            release.wait(5)
            return True

    transport = Transport([BlockingSink()])
    accepted = sum(
        1 for index in range(QUEUE_SIZE + 50) if transport.submit({"n": index})
    )
    release.set()
    assert accepted <= QUEUE_SIZE + 1, "the queue must be bounded"
    assert transport.dropped > 0
    transport.close(1)


def test_importing_blare_starts_no_threads():
    """The worker is lazy, so a library import has no side effects."""
    before = threading.active_count()
    transport = Transport([RecordingSink()])
    assert threading.active_count() == before
    transport.submit({"title": "boom"})
    transport.flush(5)
    transport.close()


def test_submitting_after_close_is_a_no_op():
    transport = Transport([RecordingSink()])
    transport.close()
    assert transport.submit({"title": "boom"}) is False
