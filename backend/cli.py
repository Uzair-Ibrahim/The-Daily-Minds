import argparse
import asyncio
import json
import sys

from pydantic import ValidationError

from backend.config import Settings
from backend.mcp_client import MCPSearchClient
from backend.orchestrator import Orchestrator
from backend.schemas import AskRequest


async def execute(args) -> int:
    settings = Settings()
    if args.command == "paper":
        from pydantic import TypeAdapter
        from backend.schemas import Query
        query = TypeAdapter(Query).validate_python(args.question)
        result = await MCPSearchClient(settings).discover_news(query, args.limit)
        if args.json:
            print(result.model_dump_json())
        else:
            print(f"THE DAILY MIND | RSS discovery | {result.status}")
            for index, article in enumerate(result.articles, 1):
                print(f"\n{index}. {article.title}\n{article.source} | {article.url}")
                print(f"Published: {article.published_at or 'unknown'} | Retrieved: {article.retrieved_at}")
                print(f"{article.description}\nPriority: {article.score} | {'; '.join(article.reasons)}")
            for warning in result.warnings:
                print(f"Warning: {warning}")
        return 0 if result.articles else 1
    if args.command == "health":
        tools = await MCPSearchClient(settings).list_tools()
        print(json.dumps({"status": "ok", "mcp_tools": tools,
                          "search_provider": settings.search_provider,
                          "live_search_configured": settings.search_configured, "llm_enabled": False}))
        return 0
    request = AskRequest(question=args.question, live=args.live, max_sources=args.max_sources,
                         use_cache=getattr(args, "cache", False))
    result = await Orchestrator(settings).ask(request)
    if args.json:
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=True))
    else:
        print(f"Status: {result.status} | Mode: {result.mode}\n{result.answer}")
        for item in result.evidence:
            print(f"Source [{item.id}]: {item.title} - {item.url}")
        print(f"Retrieved UTC: {result.retrieved_at_utc or 'not retrieved'} | Freshness: {result.freshness}")
        for warning in result.limitations:
            print(f"Warning: {warning}")
    return 0 if result.status in {"ok", "partial"} else 1


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Evidence-backed MCP search baseline")
    sub = parser.add_subparsers(dest="command", required=True)
    ask = sub.add_parser("ask")
    ask.add_argument("question")
    ask.add_argument("--live", action="store_true", help="Perform fresh search through MCP using SEARCH_PROVIDER")
    ask.add_argument("--json", action="store_true")
    ask.add_argument("--cache", action="store_true", help="Allow in-process cached evidence; standalone invocations start empty")
    ask.add_argument("--max-sources", type=int, default=5)
    sub.add_parser("health")
    paper = sub.add_parser("paper", help="Discover, rank and persist live RSS news through MCP; no paid API")
    paper.add_argument("question")
    paper.add_argument("--limit", type=int, choices=range(1, 21), default=8)
    paper.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        return asyncio.run(execute(args))
    except ValidationError:
        print("Invalid input/configuration: question 1-2000 characters; sources 1-8; timeout 1-120; SEARCH_PROVIDER exa or tavily.", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    except Exception:
        print("Service temporarily unavailable. Check local MCP installation and configuration.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
