"""Trace and span ids for audit events (ADR-0033 point 14).

An audit event stores the trace id and span id that were current when it was written. That link
does not depend on any span attribute the tracer may or may not carry."""

from opentelemetry import trace


def current_trace_ids() -> tuple[str | None, str | None]:
    """The active trace id (32 hex digits) and span id (16), or (None, None) with no active span."""
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None, None
    return format(context.trace_id, "032x"), format(context.span_id, "016x")
