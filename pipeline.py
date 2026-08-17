from ingestion.extract import extract
from detection.detect import detect
from scoring.score import score
from redaction.redact import apply_redactions


def analyze(filepath: str, profile: str = "THIRD_PARTY_SERVICE") -> dict:
    extraction = extract(filepath)

    candidates = detect(extraction)

    decisions = score(candidates, profile)

    return decisions


def apply(filepath: str, decisions: dict, out_path: str) -> str:
    return apply_redactions(filepath, decisions, out_path)


if __name__ == "__main__":
    import sys, json
    path = sys.argv[1]
    decisions = analyze(path)
    print(json.dumps(decisions, indent=2))
    out = apply(path, decisions, "testdata/documents/out.pdf")
    print("wrote", out)
