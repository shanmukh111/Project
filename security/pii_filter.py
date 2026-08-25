from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine


# ---------------------------------------------------------
# Presidio engines
# ---------------------------------------------------------

_analyzer = AnalyzerEngine()
_anonymizer = AnonymizerEngine()


# ---------------------------------------------------------
# Protected terms
#
# Presidio's default location recognizer is a general-purpose NER
# model with no awareness of this system's own vocabulary - it
# confidently misclassifies "Jarvis" as a LOCATION (score 0.85,
# confirmed by direct testing), which silently strips the word out
# of every question before it reaches authorization matching or
# the retrieval agent's own reasoning. Real PII detection stays on
# for everything else; these specific terms are business
# vocabulary, not personal data, and are excluded from masking
# regardless of what Presidio's model guesses about them.
# ---------------------------------------------------------

PROTECTED_TERMS = {
    "jarvis",
    "alpha",
}


def _filter_protected_terms(
    text: str,
    analyzer_results: list,
) -> list:
    return [
        result
        for result in analyzer_results
        if text[result.start:result.end].strip().lower()
        not in PROTECTED_TERMS
    ]


# ---------------------------------------------------------
# PII detection
# ---------------------------------------------------------

def detect_pii(
    text: str,
) -> list[dict]:
    """
    Detect PII entities in text.

    Returns only metadata about the detected
    entities. The actual sensitive values are
    not returned.
    """

    results = _analyzer.analyze(
        text=text,
        language="en",
    )

    results = _filter_protected_terms(text, results)

    return [
        {
            "entity_type": result.entity_type,
            "start": result.start,
            "end": result.end,
            "score": round(
                result.score,
                3,
            ),
        }
        for result in results
    ]


# ---------------------------------------------------------
# PII masking
# ---------------------------------------------------------

def anonymize_pii(
    text: str,
) -> dict:
    """
    Detect and mask PII before the text reaches
    the routing and agent orchestration layer.

    Important:
    The caller should avoid logging original_text
    when PII is detected.
    """

    analyzer_results = _analyzer.analyze(
        text=text,
        language="en",
    )

    analyzer_results = _filter_protected_terms(
        text,
        analyzer_results,
    )

    if not analyzer_results:
        return {
            "original_text": text,
            "sanitized_text": text,
            "pii_detected": False,
            "entities": [],
        }

    anonymized = _anonymizer.anonymize(
        text=text,
        analyzer_results=analyzer_results,
    )

    entities = [
        {
            "entity_type": result.entity_type,
            "score": round(
                result.score,
                3,
            ),
        }
        for result in analyzer_results
    ]

    return {
        "original_text": text,
        "sanitized_text": anonymized.text,
        "pii_detected": True,
        "entities": entities,
    }