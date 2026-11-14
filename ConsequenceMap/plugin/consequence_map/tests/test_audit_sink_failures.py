"""The audit sink's failure counter must be visible.

A storage failure is counted by the sink and the operation continues:
the host owns the decision, and a missing audit row is a gap in the
trail, never a reason to let an operation through that would not
otherwise have gone through.

But a gap that nobody can see is not a gap anyone can act on. The
counter was incremented and never read - the status command did not
mention it. These tests pin the behaviour:

* the counter starts at zero;
* it increments when a write fails;
* the status command reports the current value;
* reading the status does not reset or hide the counter;
* a sink without the counter does not make the status command fail.

They are behavioural: they make a real sink fail and read the real
status output.
"""
from __future__ import annotations

import unittest

from .. import hooks
from ..hooks import RepositoryAuthorizationSink


class _BrokenLifecycle:
    """A lifecycle whose write always fails."""

    def record_authorization(self, record):
        raise RuntimeError("the storage is unavailable")


class _NoLifecycleSink(RepositoryAuthorizationSink):
    """A sink with no storage at all - the write cannot even be tried."""

    def __init__(self):
        super().__init__(repository=None, lifecycle=None)

    def _lifecycle_for(self):
        return None


class AuditSinkFailureCounterTests(unittest.TestCase):
    """The counter exists, moves and is reported."""

    def setUp(self):
        self._original_sink = hooks.STATE.sink
        self.addCleanup(self._restore)

    def _restore(self):
        hooks.STATE.sink = self._original_sink

    def test_the_counter_starts_at_zero(self):
        sink = RepositoryAuthorizationSink(lifecycle=_BrokenLifecycle())
        self.assertEqual(sink.failures, 0)

    def test_the_counter_increments_when_the_write_fails(self):
        sink = RepositoryAuthorizationSink(lifecycle=_BrokenLifecycle())
        sink._write(object(), action="settle")
        self.assertEqual(sink.failures, 1)
        sink._write(object(), action="settle")
        self.assertEqual(sink.failures, 2)

    def test_the_counter_increments_when_there_is_no_storage_at_all(self):
        sink = _NoLifecycleSink()
        sink._write(object(), action="settle")
        self.assertEqual(sink.failures, 1)

    def test_the_status_reports_the_current_value(self):
        sink = RepositoryAuthorizationSink(lifecycle=_BrokenLifecycle())
        hooks.STATE.sink = sink
        self.assertIn("Audit sink failures this session: 0", hooks.on_command("status"))
        sink._write(object(), action="settle")
        self.assertIn("Audit sink failures this session: 1", hooks.on_command("status"))
        sink._write(object(), action="settle")
        self.assertIn("Audit sink failures this session: 2", hooks.on_command("status"))

    def test_reading_the_status_does_not_reset_or_hide_the_counter(self):
        sink = RepositoryAuthorizationSink(lifecycle=_BrokenLifecycle())
        hooks.STATE.sink = sink
        sink._write(object(), action="settle")
        for _ in range(3):
            hooks.on_command("status")
        self.assertEqual(sink.failures, 1)
        self.assertIn("Audit sink failures this session: 1", hooks.on_command("status"))

    def test_a_sink_without_the_counter_does_not_break_the_status(self):
        class _NoCounterSink:
            def begin(self, record):
                pass

            def settle(self, record):
                pass

            def close(self, record):
                pass

        hooks.STATE.sink = _NoCounterSink()
        output = hooks.on_command("status")
        self.assertIn("Audit sink failures this session: 0", output)

    def test_the_inert_sink_reports_zero_failures(self):
        inert = hooks.AuthorizationSink()
        self.assertEqual(inert.failures, 0)
        hooks.STATE.sink = inert
        self.assertIn("Audit sink failures this session: 0", hooks.on_command("status"))


if __name__ == "__main__":
    unittest.main()
