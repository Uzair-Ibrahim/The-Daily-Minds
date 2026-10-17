import json
import argparse
import io
import os
import subprocess
import sys

import pytest

from backend.config import ROOT


@pytest.mark.parametrize("provider,key_name", [("exa", "EXA_API_KEY"), ("tavily", "TAVILY_API_KEY")])
@pytest.mark.parametrize("arguments,expected_code", [
    (["ask", "Python asyncio", "--json", "--live"], 1),
    (["ask", "Python asyncio", "--json"], 1),
    (["ask", "  ", "--live", "--json"], 2),
])
def test_cli_process_json_and_exit_codes(arguments, expected_code, provider, key_name):
    env = dict(os.environ, SEARCH_PROVIDER=provider, EXA_API_KEY="", TAVILY_API_KEY="", LLM_API_KEY="", LLM_PROVIDER="none")
    result = subprocess.run([sys.executable, "-m", "backend.cli", *arguments], cwd=ROOT,
                            env=env, capture_output=True, text=True, timeout=45)
    assert result.returncode == expected_code
    if expected_code == 2:
        assert result.stdout == ""
        assert "Invalid input" in result.stderr
    else:
        payload = json.loads(result.stdout)
        assert not payload["evidence"]
        assert payload["status"] == ("provider_unavailable" if "--live" in arguments else "no_evidence")
        assert payload["retrieved_at_utc"] is None
        if "--live" in arguments:
            assert any(key_name in message for message in payload["limitations"])


def test_smoke_missing_key_is_skip_with_nonzero_exit():
    result = subprocess.run([sys.executable, "scripts/smoke_live.py"], cwd=ROOT,
                            env=dict(os.environ, SEARCH_PROVIDER="exa", EXA_API_KEY="", TAVILY_API_KEY=""), capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert result.stdout.strip() == "LIVE_SMOKE_TEST: NOT RUN (missing key)"


@pytest.mark.parametrize("entrypoint", ["cli", "smoke"])
async def test_json_output_handles_unicode_on_ascii_console(settings, monkeypatch, entrypoint):
    from backend import cli
    from backend.schemas import AskResponse
    from backend.services.provenance import utc_now
    from scripts import smoke_live

    class AsciiConsole(io.StringIO):
        def write(self, value):
            value.encode("ascii")
            return super().write(value)

    class Workflow:
        def __init__(self, settings):
            pass

        async def ask(self, request):
            return AskResponse(answer="TEST Unicode: \u2192 \u2705", status="no_evidence", queried_at_utc=utc_now(),
                               freshness="not_retrieved", elapsed_ms=0)

    console = AsciiConsole()
    monkeypatch.setattr(sys, "stdout", console)
    module = cli if entrypoint == "cli" else smoke_live
    monkeypatch.setattr(module, "Settings", lambda: settings)
    monkeypatch.setattr(module, "Orchestrator", Workflow)
    if entrypoint == "cli":
        args = argparse.Namespace(command="ask", question="test", live=True, json=True, max_sources=1)
        assert await cli.execute(args) == 1
        assert json.loads(console.getvalue())["answer"] == "TEST Unicode: \u2192 \u2705"
    else:
        assert await smoke_live.main() == 1
        assert "LIVE_SMOKE_TEST: FAIL" in console.getvalue()
