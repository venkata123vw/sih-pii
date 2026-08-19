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

## Running the app

```
python -m streamlit run app.py
```

Use `python -m streamlit`, not a bare `streamlit run app.py` — on Windows
especially, `pip install`'s console-script (`streamlit.exe`) only lands
somewhere PowerShell can find it if that Scripts directory happens to be on
PATH, which isn't guaranteed even right after a successful `pip install`
(common with venvs that aren't activated, or a global user install). A bare
`streamlit run app.py` then fails with
`CommandNotFoundException: The term 'streamlit' is not recognized...`, even
though the package installed fine. `python -m streamlit` sidesteps that
entirely — it's the same `python` you just used for `pip install`, so if
that command worked, this one will too.
