"""
test_verdict_engine.py — Integration tests for the Verdict Engine.

Runs 5 test scenarios against real Russell JSON payloads.
Tests 2–5 invoke the NLI model; Test 1 (Path 1) does not.

Usage:
    python test_verdict_engine.py
"""

import json

from agents.verdict_engine import VerdictEngine

# ---------------------------------------------------------------------------
# One engine instance shared across all tests (model loads once).
# ---------------------------------------------------------------------------
engine = VerdictEngine()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_result(test_id: int, passed: bool, detail: str = "") -> None:
    """Print a standardised PASSED / FAILED line."""
    status = "PASSED" if passed else "FAILED"
    suffix = f" — {detail}" if detail else ""
    print(f"Test {test_id} {status}{suffix}")


def _dump(output: dict) -> None:
    """Pretty-print a FinalOutput for debugging."""
    print(json.dumps(output, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Test 1 — Path 1: HIGH_FAKE_MATCH
# ---------------------------------------------------------------------------

def test_path_one_high_fake() -> bool:
    """
    Path 1 fast path.

    A HIGH_FAKE_MATCH signal with a 0.94-similarity Bucket A hit should
    short-circuit to FALSE with no NLI inference.
    """
    russell_json = {
        "claim": "test",
        "dialect": "MSA",
        "dialect_confidence": 0.9,
        "query_used": "test",
        "verdict_signal": "HIGH_FAKE_MATCH",
        "bucket_a": [
            {
                "claim": "test",
                "similarity": 0.94,
                "label": "FALSE",
                "source": "saheeh",
                "debunk": "fake",
            }
        ],
        "bucket_b": [],
        "bucket_b_searched": False,
    }

    output = engine.decide(russell_json)

    checks = {
        "final_verdict == FALSE":    output["final_verdict"] == "FALSE",
        "confidence == 0.94":        output["confidence"] == 0.94,
        "stance_breakdown is empty": output["stance_breakdown"] == [],
    }

    passed = all(checks.values())
    failed_checks = [k for k, v in checks.items() if not v]
    detail = "" if passed else f"failed: {failed_checks}; output={output}"
    _print_result(1, passed, detail)
    return passed


# ---------------------------------------------------------------------------
# Test 2 — Path 2: POSSIBLE_FAKE → should REFUTE
# ---------------------------------------------------------------------------

def test_path_two_refutes() -> bool:
    """
    Path 2 NLI path.

    The claim asserts Sinai was sold. Trusted propositions strongly assert
    Egyptian sovereignty over Sinai — the model should label them REFUTES.
    Expected verdict: FALSE (POSSIBLE_FAKE prior + all-refute evidence).
    """
    russell_json = {
        "claim": "السيسي باع سيناء للإسرائيليين",
        "dialect": "MSA",
        "dialect_confidence": 0.85,
        "query_used": "بيع سيناء",
        "verdict_signal": "POSSIBLE_FAKE",
        "bucket_a": [],
        "bucket_b": [
            {
                "proposition": "سيناء أرض مصرية محررة وجزء لا يتجزأ من الأراضي المصرية.",
                "title": "سيادة مصر على سيناء",
                "source": "الأهرام",
                "hybrid_score": 0.88,
                "bm25_score": 0.80,
                "arabert_score": 0.91,
            },
            {
                "proposition": "لم تتنازل مصر عن أي جزء من أراضيها في سيناء لأي طرف أجنبي.",
                "title": "ثوابت الموقف المصري",
                "source": "وكالة أنباء الشرق الأوسط",
                "hybrid_score": 0.85,
                "bm25_score": 0.78,
                "arabert_score": 0.88,
            },
        ],
        "bucket_b_searched": True,
    }

    output = engine.decide(russell_json)

    stances = [sd["stance"] for sd in output["stance_breakdown"]]
    checks = {
        "final_verdict == FALSE": output["final_verdict"] == "FALSE",
        "all stances are REFUTES": all(s == "REFUTES" for s in stances),
    }

    passed = all(checks.values())
    failed_checks = [k for k, v in checks.items() if not v]
    detail = "" if passed else (
        f"failed: {failed_checks}; "
        f"verdict={output['final_verdict']}, stances={stances}"
    )
    _print_result(2, passed, detail)
    return passed


# ---------------------------------------------------------------------------
# Test 3 — Path 2: EVIDENCE_FOUND → should SUPPORT
# ---------------------------------------------------------------------------

def test_path_two_supports() -> bool:
    """
    Path 2 NLI path.

    The claim states the Egyptian pound depreciated. Trusted propositions
    confirm this — the model should label them SUPPORTS.
    Expected verdict: TRUE (EVIDENCE_FOUND prior + all-support evidence).
    """
    russell_json = {
        "claim": "الجنيه المصري فقد قيمته أمام الدولار في السنوات الأخيرة",
        "dialect": "MSA",
        "dialect_confidence": 0.90,
        "query_used": "انخفاض الجنيه المصري",
        "verdict_signal": "EVIDENCE_FOUND",
        "bucket_a": [],
        "bucket_b": [
            {
                "proposition": "شهد الجنيه المصري انخفاضاً حاداً في قيمته مقابل الدولار الأمريكي خلال الفترة الأخيرة.",
                "title": "تراجع العملة المصرية",
                "source": "رويترز عربي",
                "hybrid_score": 0.91,
                "bm25_score": 0.87,
                "arabert_score": 0.93,
            },
            {
                "proposition": "فقدت العملة المصرية أكثر من نصف قيمتها أمام الدولار خلال السنوات الأخيرة.",
                "title": "الاقتصاد المصري والضغوط النقدية",
                "source": "بي بي سي عربي",
                "hybrid_score": 0.89,
                "bm25_score": 0.84,
                "arabert_score": 0.91,
            },
        ],
        "bucket_b_searched": True,
    }

    output = engine.decide(russell_json)

    stances = [sd["stance"] for sd in output["stance_breakdown"]]
    checks = {
        "final_verdict == TRUE": output["final_verdict"] == "TRUE",
        "all stances are SUPPORTS": all(s == "SUPPORTS" for s in stances),
    }

    passed = all(checks.values())
    failed_checks = [k for k, v in checks.items() if not v]
    detail = "" if passed else (
        f"failed: {failed_checks}; "
        f"verdict={output['final_verdict']}, stances={stances}"
    )
    _print_result(3, passed, detail)
    return passed


# ---------------------------------------------------------------------------
# Test 4 — Path 2: LOW_CONFIDENCE → should be UNVERIFIED
# ---------------------------------------------------------------------------

def test_path_two_uncertain() -> bool:
    """
    Path 2 NLI path with weak evidence.

    One proposition with a low hybrid_score (0.45) and a LOW_CONFIDENCE
    signal.  The aggregator should not have enough weight to cross a verdict
    threshold; confidence must stay ≤ 0.70.
    """
    russell_json = {
        "claim": "ارتفعت نسبة البطالة في مصر هذا العام",
        "dialect": "MSA",
        "dialect_confidence": 0.75,
        "query_used": "البطالة في مصر",
        "verdict_signal": "LOW_CONFIDENCE",
        "bucket_a": [],
        "bucket_b": [
            {
                "proposition": "تتباين الأرقام حول معدلات التوظيف في السوق المصرية.",
                "title": "سوق العمل المصري",
                "source": "الجهاز المركزي للتعبئة والإحصاء",
                "hybrid_score": 0.45,
                "bm25_score": 0.40,
                "arabert_score": 0.48,
            },
        ],
        "bucket_b_searched": True,
    }

    output = engine.decide(russell_json)

    checks = {
        "final_verdict == UNVERIFIED": output["final_verdict"] == "UNVERIFIED",
        "confidence <= 0.70":          output["confidence"] <= 0.70,
    }

    passed = all(checks.values())
    failed_checks = [k for k, v in checks.items() if not v]
    detail = "" if passed else (
        f"failed: {failed_checks}; "
        f"verdict={output['final_verdict']}, confidence={output['confidence']}"
    )
    _print_result(4, passed, detail)
    return passed


# ---------------------------------------------------------------------------
# Test 5 — Path 2: POSSIBLE_MATCH → mixed evidence → UNVERIFIED
# ---------------------------------------------------------------------------

def test_path_two_mixed() -> bool:
    """
    Path 2 NLI path with deliberately mixed evidence.

    Two propositions are chosen to support the claim; two to refute it.
    The POSSIBLE_MATCH signal carries a 0.0 prior.  With balanced evidence
    the adjusted_ratio should stay in the UNVERIFIED band (0.31–0.69).
    """
    russell_json = {
        "claim": "مصر ستبني مفاعلاً نووياً في الضبعة",
        "dialect": "MSA",
        "dialect_confidence": 0.88,
        "query_used": "مفاعل الضبعة النووي",
        "verdict_signal": "POSSIBLE_MATCH",
        "bucket_a": [],
        "bucket_b": [
            # --- expected SUPPORTS ---
            {
                "proposition": "وقّعت مصر اتفاقية مع روساتوم الروسية لإنشاء محطة الضبعة للطاقة النووية.",
                "title": "اتفاقية الضبعة النووية",
                "source": "رويترز عربي",
                "hybrid_score": 0.82,
                "bm25_score": 0.78,
                "arabert_score": 0.85,
            },
            {
                "proposition": "تمضي مصر قدماً في مشروع الضبعة النووي بالتعاون مع الجانب الروسي.",
                "title": "مشروع الضبعة",
                "source": "الأهرام",
                "hybrid_score": 0.80,
                "bm25_score": 0.76,
                "arabert_score": 0.83,
            },
            # --- expected REFUTES ---
            {
                "proposition": "تواجه محطة الضبعة النووية تأخيرات متكررة ولم يُحسم موعد إنشائها حتى الآن.",
                "title": "تأخيرات مشروع الضبعة",
                "source": "بي بي سي عربي",
                "hybrid_score": 0.78,
                "bm25_score": 0.74,
                "arabert_score": 0.81,
            },
            {
                "proposition": "لم تُصدر الحكومة المصرية حتى الآن قراراً نهائياً ببدء تشييد المفاعل النووي في الضبعة.",
                "title": "الوضع الراهن للضبعة",
                "source": "العربي الجديد",
                "hybrid_score": 0.76,
                "bm25_score": 0.71,
                "arabert_score": 0.79,
            },
        ],
        "bucket_b_searched": True,
    }

    output = engine.decide(russell_json)

    checks = {
        "final_verdict == UNVERIFIED": output["final_verdict"] == "UNVERIFIED",
    }

    passed = all(checks.values())
    failed_checks = [k for k, v in checks.items() if not v]
    stances = [sd["stance"] for sd in output["stance_breakdown"]]
    detail = "" if passed else (
        f"failed: {failed_checks}; "
        f"verdict={output['final_verdict']}, stances={stances}, "
        f"confidence={output['confidence']}"
    )
    _print_result(5, passed, detail)
    return passed


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Verdict Engine — Integration Tests")
    print("=" * 60)

    results: list[bool] = []

    # Test 1 — Path 1 (no NLI)
    print("\n[Test 1] Path 1: HIGH_FAKE_MATCH")
    results.append(test_path_one_high_fake())

    # Tests 2–5 — Path 2 (NLI runs for each)
    nli_tests = [
        (2, "Path 2: POSSIBLE_FAKE → REFUTES",   test_path_two_refutes),
        (3, "Path 2: EVIDENCE_FOUND → SUPPORTS",  test_path_two_supports),
        (4, "Path 2: LOW_CONFIDENCE → UNVERIFIED",test_path_two_uncertain),
        (5, "Path 2: POSSIBLE_MATCH → mixed",     test_path_two_mixed),
    ]

    for test_id, label, fn in nli_tests:
        print(f"\n[Test {test_id}] {label}")
        try:
            results.append(fn())
        except Exception as exc:
            print(
                f"Test {test_id} SKIPPED — NLI model unavailable or error: {exc}"
            )
            results.append(False)

    # Summary
    passed_count = sum(results)
    total_count  = len(results)
    print("\n" + "=" * 60)
    print(f"Results: {passed_count}/{total_count} tests passed.")
    print("=" * 60)
