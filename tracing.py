"""
Phoenix tracing for the retrieval pipeline.

Emits one OpenInference RETRIEVER span per question, carrying the query and
every chunk that came back with its rank, score, token count and source path.
That is the difference between "Q22 failed" and "Q22 failed because AppState.kt
took two of the five slots and SettingsScreen.kt ranked 11th".

results.json already records the top-k paths, so this is not the only way to
see that. What Phoenix adds is a UI to sort and compare runs in, and -- once
answer generation lands -- a place where the retrieval span and the generation
span sit under one trace.

Usage:
    python -m phoenix.server.main serve      # in another shell, or:
    python tracing.py --serve                # launches and blocks

    python score.py --trace                  # emits spans to it
"""

import argparse
import os

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace as ot
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

ENDPOINT = os.environ.get("PHOENIX_ENDPOINT", "http://localhost:6006/v1/traces")
_tracer = None


def get_tracer(project: str = "cardwise-code-rag"):
    """Idempotent. Returns None if the collector is unreachable, so a missing
    Phoenix never breaks a scoring run."""
    global _tracer
    if _tracer is not None:
        return _tracer
    try:
        provider = TracerProvider(resource=Resource.create({
            "service.name": project, "openinference.project.name": project}))
        provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(ENDPOINT)))
        ot.set_tracer_provider(provider)
        _tracer = ot.get_tracer(__name__)
    except Exception as e:                      # noqa: BLE001
        print(f"tracing disabled: {e}")
        _tracer = False
    return _tracer


def trace_retrieval(question: str, qid: int, arm: str, docs: list[dict],
                    expected: list[str], passed: dict) -> None:
    """
    One RETRIEVER span. `docs` is rank-ordered, each with id/path/score/tokens.
    Expected files and pass/fail ride along as attributes so a failing question
    can be found in the UI without cross-referencing results.json.
    """
    tracer = get_tracer()
    if not tracer:
        return
    with tracer.start_as_current_span(f"retrieve.{arm}.Q{qid}") as span:
        span.set_attribute(SpanAttributes.OPENINFERENCE_SPAN_KIND,
                           OpenInferenceSpanKindValues.RETRIEVER.value)
        span.set_attribute(SpanAttributes.INPUT_VALUE, question)
        span.set_attribute("eval.question_id", qid)
        span.set_attribute("eval.arm", arm)
        span.set_attribute("eval.expected", ", ".join(expected))
        span.set_attribute("eval.n_expected", len(expected))
        for name, ok in passed.items():
            span.set_attribute(f"eval.{name}", bool(ok))
        for i, d in enumerate(docs):
            p = f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document"
            span.set_attribute(f"{p}.id", d["id"])
            span.set_attribute(f"{p}.score", float(d["score"]))
            span.set_attribute(f"{p}.content", d.get("preview", ""))
            span.set_attribute(f"{p}.metadata",
                               f'{{"path": "{d["path"]}", "tokens": {d["tokens"]}, '
                               f'"rank": {i + 1}, "expected": {str(d["path"] in expected).lower()}}}')


def flush() -> None:
    provider = ot.get_tracer_provider()
    if hasattr(provider, "force_flush"):
        provider.force_flush()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true", help="launch the Phoenix UI")
    if ap.parse_args().serve:
        import phoenix as px
        session = px.launch_app()
        print(f"Phoenix UI: {session.url}")
        input("press enter to stop\n")
