"""
False-positive benchmark for the detection registry.

Answers the question a judge will ask: "how often does this flag things
that aren't PII?" Reports per-type hit rates against two corpora:

  RANDOM    — uniformly random strings matching each type's rough shape.
              An upper bound; real documents are not uniformly random.
  REALISTIC — plausible non-PII strings that actually appear in invoices,
              orders, and forms. This is the number that matters.

Run: python -m detection.benchmark_fp
"""
import random
import re

from detection.detect import REGISTRY, detect

SEED = 1668
N = 20000


def _random_corpus(n=N):
    """Uniformly random strings shaped like each type's raw material."""
    out = []
    for _ in range(n):
        kind = random.choice(["d10", "d12", "d16", "alnum10", "l3d7"])
        if kind == "d10":
            out.append("".join(random.choice("0123456789") for _ in range(10)))
        elif kind == "d12":
            out.append("".join(random.choice("0123456789") for _ in range(12)))
        elif kind == "d16":
            out.append("".join(random.choice("0123456789") for _ in range(16)))
        elif kind == "alnum10":
            out.append("".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
                               for _ in range(5))
                       + "".join(random.choice("0123456789") for _ in range(4))
                       + random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
        else:
            out.append("".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
                               for _ in range(3))
                       + "".join(random.choice("0123456789") for _ in range(7)))
    return out


def _realistic_corpus(n=N):
    """
    Non-PII strings of the kind that actually appear in the documents
    this tool will process. None of these should ever be flagged.
    """
    out = []
    for _ in range(n):
        kind = random.choice([
            "order", "invoice", "amount", "date", "gstin_ish", "ref",
            "phone_like_amount", "pincode", "account", "tracking",
        ])
        if kind == "order":                       # date-based order ID
            out.append(f"2025{random.randint(1,12):02d}"
                       f"{random.randint(1,28):02d}"
                       f"{random.randint(0,9999):04d}")
        elif kind == "invoice":
            out.append(f"INV{random.randint(0,9999999):07d}")
        elif kind == "amount":                    # rupee amounts in paise
            out.append(str(random.randint(10**9, 10**12)))
        elif kind == "date":
            out.append(f"{random.randint(1,28):02d}"
                       f"{random.randint(1,12):02d}"
                       f"{random.randint(1950,2025)}")
        elif kind == "gstin_ish":
            out.append(f"{random.randint(1,37):02d}"
                       + "".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
                                 for _ in range(5))
                       + f"{random.randint(0,9999):04d}")
        elif kind == "ref":
            out.append("".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
                               for _ in range(3))
                       + f"{random.randint(0,9999999):07d}")
        elif kind == "phone_like_amount":          # 10-digit totals
            out.append(str(random.randint(6 * 10**9, 10**10 - 1)))
        elif kind == "pincode":
            out.append(f"{random.randint(100000, 999999)}")
        elif kind == "account":                    # bank account numbers
            out.append(str(random.randint(10**11, 10**16)))
        else:                                      # courier tracking
            out.append("".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
                               for _ in range(2))
                       + f"{random.randint(0,999999999):09d}IN")
    return out


def _hits(corpus, chunk=500):
    """
    Count claims by running the REAL detect() — not the patterns in
    isolation. This exercises raw_requires and context_keywords, which
    live in the engine, so the number reflects what actually ships.
    """
    counts = {t: 0 for t in REGISTRY}
    for i in range(0, len(corpus), chunk):
        batch = corpus[i:i + chunk]
        page = {
            "page_num": 0,
            "tokens": [{"text": s, "bbox": None, "ocr_conf": 1.0}
                       for s in batch],
            "full_text": " ".join(batch),
        }
        out = detect({"doc_id": "bench", "pages": [page]})
        for c in out["candidates"]:
            counts[c["pii_type"]] += 1
    return counts


def main():
    random.seed(SEED)
    corpora = {"RANDOM": _random_corpus(), "REALISTIC": _realistic_corpus()}

    print(f"n = {N} strings per corpus, seed = {SEED}\n")
    header = f"{'TYPE':<14}{'CHECKSUM':<12}"
    header += "".join(f"{name:>12}" for name in corpora)
    print(header)
    print("-" * len(header))

    results = {name: _hits(c) for name, c in corpora.items()}
    for pii_type, spec in REGISTRY.items():
        has_ck = "yes" if spec["validator"] else "no"
        row = f"{pii_type:<14}{has_ck:<12}"
        for name in corpora:
            rate = results[name][pii_type] / N
            row += f"{rate:>11.2%}"
        print(row)

    print("\nRead: percentage of NON-PII strings each type incorrectly claims.")
    print("Types without a checksum rely on pattern shape alone, so their")
    print("rate is bounded only by how specific the regex is. Context")
    print("scoring in P3 is what separates these from true positives.")


if __name__ == "__main__":
    main()