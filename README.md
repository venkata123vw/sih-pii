# sih-pii

PII detection, confidence scoring, policy-based redaction.

## Setup

```
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

The second command is required and easy to miss — `pip install spacy` only
installs the library, not the English model `scoring/ner.py` loads at
runtime. Skipping it fails with `OSError: Can't find model 'en_core_web_sm'`
the first time NER detection runs, on a fresh machine or a fresh demo laptop.
