"""Model evaluation script for ba-rbq.

Tests each available Ollama model against standardized trivia Q&A prompts.
Run with: poetry run python eval_models.py [model_name]
"""

import asyncio
import sys
import time
from typing import NamedTuple

import httpx

OLLAMA_BASE = "http://localhost:11434"

# Real context fetched from ESPN - NFL All-Time TD Leaders
CONTEXT = """NFL All-Time Touchdowns Leaders - National Football League - ESPN
RK PLAYER TD
1 Jerry Rice 208
2 Emmitt Smith 175
3 LaDainian Tomlinson 162
4 Randy Moss 157
5 Terrell Owens 156
6 Marcus Allen 145
7 Marshall Faulk 136
8 Cris Carter 131
9 Marvin Harrison 128
10 DERRICK HENRY 127
11 Jim Brown 126
Adrian Peterson 126
13 Walter Payton 125
14 Larry Fitzgerald 121
15 DAVANTE ADAMS 117
16 Antonio Gates 116
John Riggins 116
18 Lenny Moore 113
19 Shaun Alexander 112
20 Tony Gonzalez 111
*Active players are in CAPS."""

SYSTEM_PROMPT = (
    "You are a terse trivia assistant. "
    "Answer using ONLY the information in the provided context. "
    "Your reply MUST be one of: 'Yes', 'No', or 'Correct!' followed by "
    "at most one short sentence. "
    "Do NOT explain. Do NOT add extra information. "
    "If the answer is not in the context, reply 'I don't know.'\n\n"
    f"Context:\n---\n{CONTEXT}\n---"
)


class TestCase(NamedTuple):
    name: str
    query: str
    expected_keywords: list[str]  # must appear in response (any)
    forbidden_keywords: list[str]  # must NOT appear in response (any)
    correct_note: str  # what a correct response looks like


TESTS = [
    TestCase(
        name="rank_lookup_6",
        query="Who is #6 on the list?",
        expected_keywords=["marcus allen", "marcus", "allen", "145"],
        forbidden_keywords=["terrell", "marshall", "jerry", "emmitt"],
        correct_note="Marcus Allen (145 TDs)",
    ),
    TestCase(
        name="rank_lookup_10",
        query="Who is number 10?",
        expected_keywords=["derrick henry", "derrick", "henry", "127"],
        forbidden_keywords=["marvin", "cris", "randy"],
        correct_note="Derrick Henry (127 TDs)",
    ),
    TestCase(
        name="rank_lookup_1",
        query="Who is #1?",
        expected_keywords=["jerry rice", "rice", "208"],
        forbidden_keywords=["emmitt", "ladainian", "randy"],
        correct_note="Jerry Rice (208 TDs)",
    ),
    TestCase(
        name="existence_not_on_list",
        query="Is Tom Brady on this list?",
        expected_keywords=["no"],
        forbidden_keywords=["yes", "correct"],
        correct_note="No (Tom Brady not on TD leaders list)",
    ),
    TestCase(
        name="existence_on_list",
        query="Is Randy Moss on this list?",
        expected_keywords=["yes", "157", "randy moss"],
        forbidden_keywords=["no", "correct!"],
        correct_note="Yes, Randy Moss #4 with 157 TDs",
    ),
    TestCase(
        name="no_correct_on_question",
        query="What rank is Jerry Rice?",
        # Should answer with rank info, NOT start with "Correct!"
        expected_keywords=["1", "first", "rice", "one"],
        forbidden_keywords=["correct!"],
        correct_note="Rank 1 — should NOT say 'Correct!'",
    ),
    TestCase(
        name="hallucination_guard",
        query="Is Patrick Mahomes on this list?",
        # Mahomes is NOT on the all-time TD leaders top 20
        expected_keywords=["no", "don't know", "i don't know"],
        forbidden_keywords=["yes"],
        correct_note="No (Mahomes not in top 20 TD leaders)",
    ),
    TestCase(
        name="reverse_rank_lookup",
        query="What rank is LaDainian Tomlinson?",
        expected_keywords=["3", "third", "162", "three"],
        forbidden_keywords=["correct!"],
        correct_note="Rank 3 with 162 TDs — should NOT say 'Correct!'",
    ),
]


async def query_ollama(model: str, user_message: str) -> tuple[str, float]:
    """Query Ollama /api/chat and return (response_text, latency_ms)."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
        "options": {
            "num_predict": 50,
            "temperature": 0.0,
        },
    }
    start = time.monotonic()
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{OLLAMA_BASE}/api/chat", json=payload, timeout=90.0)
        resp.raise_for_status()
    elapsed_ms = (time.monotonic() - start) * 1000
    data = resp.json()
    text = data.get("message", {}).get("content", "").strip()
    return text, elapsed_ms


def score_response(response: str, test: TestCase) -> dict:
    """Score a model response against test expectations."""
    resp_lower = response.lower()
    kw_hits = [kw for kw in test.expected_keywords if kw in resp_lower]
    forbidden_hits = [kw for kw in test.forbidden_keywords if kw in resp_lower]
    passed = len(kw_hits) > 0 and len(forbidden_hits) == 0
    return {
        "passed": passed,
        "response": response,
        "expected_found": kw_hits,
        "forbidden_found": forbidden_hits,
    }


async def evaluate_model(model: str) -> dict:
    """Run all test cases against a model. Returns summary."""
    print(f"\n{'=' * 60}")
    print(f"Model: {model}")
    print(f"{'=' * 60}")

    results = []
    latencies = []

    for test in TESTS:
        try:
            response, latency_ms = await query_ollama(model, test.query)
            scored = score_response(response, test)
            scored["latency_ms"] = latency_ms
            scored["test_name"] = test.name
            scored["query"] = test.query
            scored["expected"] = test.correct_note
            results.append(scored)
            latencies.append(latency_ms)

            status = "✓ PASS" if scored["passed"] else "✗ FAIL"
            print(f"\n  [{status}] {test.name}")
            print(f"    Query:    {test.query}")
            print(f"    Response: {response!r}")
            print(f"    Expected: {test.correct_note}")
            print(f"    Latency:  {latency_ms:.0f}ms")
            if not scored["passed"]:
                if scored["forbidden_found"]:
                    print(
                        f"    !! Forbidden keywords found: {scored['forbidden_found']}"
                    )
                if not scored["expected_found"]:
                    print(
                        f"    !! No expected keywords matched: {test.expected_keywords}"
                    )
            # Small pause between queries to avoid overwhelming Ollama
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"\n  [ERROR] {test.name}: {e}")
            results.append({"test_name": test.name, "passed": False, "error": str(e)})

    passed = sum(1 for r in results if r.get("passed"))
    total = len(results)
    avg_latency = sum(latencies) / len(latencies) if latencies else 0

    pct = 100 * passed // total
    print(f"\n  Score: {passed}/{total} ({pct}%)  Avg latency: {avg_latency:.0f}ms")
    return {
        "model": model,
        "passed": passed,
        "total": total,
        "score_pct": 100 * passed // total,
        "avg_latency_ms": avg_latency,
        "results": results,
    }


async def main():
    # If a specific model is passed as arg, test only that one
    target_model = sys.argv[1] if len(sys.argv) > 1 else None

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{OLLAMA_BASE}/api/tags", timeout=5.0)
            models_data = resp.json()
            available = [m["name"] for m in models_data.get("models", [])]
        except Exception as e:
            print(f"Cannot connect to Ollama: {e}")
            return

    print(f"Available Ollama models: {available}")

    if target_model:
        to_test = [target_model]
    else:
        # Test all available models
        to_test = available

    print(f"Models to evaluate: {to_test}")

    all_results = []
    for model in to_test:
        result = await evaluate_model(model)
        all_results.append(result)
        # Cool-down between models to let Ollama unload/reload
        if len(to_test) > 1:
            print("\n[Cooling down 5s before next model...]")
            await asyncio.sleep(5)

    # Summary table
    print(f"\n\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    print(f"{'Model':<30} {'Score':>8} {'Avg Latency':>12}")
    print("-" * 52)
    for r in sorted(all_results, key=lambda x: -x["score_pct"]):
        score = f"{r['passed']}/{r['total']} ({r['score_pct']:>3}%)"
        lat = f"{r['avg_latency_ms']:>8.0f}ms"
        print(f"{r['model']:<30} {score}  {lat}")


if __name__ == "__main__":
    asyncio.run(main())
