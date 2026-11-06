"""opendraco adapter — the public OpenDraco inference event log (first instance)."""

from ..events import EventLogError, parse_event_log
from ..registry import ConvertError, register
from ..wire import build_session


def convert(run_id: str, body: bytes, title: str | None = None):
    try:
        run, _instances = parse_event_log(body, None)
    except EventLogError as exc:
        raise ConvertError(str(exc)) from exc
    if not run.activations:
        raise ConvertError("The OpenDraco event log records no agent activity.")
    return build_session(run, run_id, title)


register("opendraco", convert)
