"""
app.py — P5: Interface & Integration

Wired to REAL teammate modules via pipeline.py (ingestion, detection,
scoring, and redaction are all real now — no track is a stub body).
See pipeline.py's module docstring for the full list of integration
fixes and known bugs found while wiring this up.

Run with:  python -m streamlit run app.py
(not a bare `streamlit run app.py` — see README's "Running the app"
section for why that fails with CommandNotFoundException on Windows)
"""

import streamlit as st
import pipeline
from pipeline import group_detections_for_review

st.set_page_config(page_title="PII Detection & Redaction", layout="wide")

# ---------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------
if "analysis" not in st.session_state:
    st.session_state.analysis = None
if "file_bytes" not in st.session_state:
    st.session_state.file_bytes = None
if "filename" not in st.session_state:
    st.session_state.filename = None
if "result" not in st.session_state:
    st.session_state.result = None

st.title("PII Detection & Redaction")
st.caption("SIH1668 — wired to real ingestion/detection/scoring/redaction "
           "modules end to end. Every upload runs through real extraction "
           "(native text or OCR) and real PII detection.")

# ---------------------------------------------------------------------
# Entry mode
# ---------------------------------------------------------------------
mode = st.radio(
    "How are you using this?",
    ["Before I upload (I'm the individual user)", "Reviewing what I received (I'm the processing entity)"],
    horizontal=True,
)

st.divider()

# ---------------------------------------------------------------------
# Context profile dropdown
# ---------------------------------------------------------------------
col_a, col_b = st.columns([2, 3])
with col_a:
    profile = st.selectbox("Context profile", pipeline.PROFILES, index=1)
with col_b:
    profile_notes = {
        "PUBLIC_DISCLOSURE": "Nothing survives — every identifier removed.",
        "THIRD_PARTY_SERVICE": "Government IDs removed/masked; name kept since the service needs it.",
        "REGULATED_KYC": "Required identifiers are kept or masked; nothing extraneous survives.",
        "INTERNAL_REVIEW": "Everything flagged for human review by default.",
    }
    st.info(profile_notes[profile])

st.divider()

# ---------------------------------------------------------------------
# Input: file upload OR paste-text
# ---------------------------------------------------------------------
tab_file, tab_paste = st.tabs(["Upload a document", "Paste text / form data"])

uploaded_file = None
pasted_text = None

with tab_file:
    uploaded_file = st.file_uploader(
        "PDF, DOCX, JPG, or PNG",
        type=["pdf", "docx", "jpg", "jpeg", "png"],
    )

with tab_paste:
    st.caption("Paste-text mode supports detection and scoring only. It has no original file to redact.")
    pasted_text = st.text_area(
        "Paste raw text, CSV rows, or form field values",
        height=150,
        placeholder="e.g. Name: Rahul Sharma, Aadhaar: 1234 5678 9012, Phone: 9876543210",
    )

run = st.button("Analyze", type="primary", disabled=not (uploaded_file or pasted_text))

# ---------------------------------------------------------------------
# Stage 1: analyze()  — extract -> detect -> score. No modification yet.
# ---------------------------------------------------------------------
if run:
    with st.spinner("Extracting text, detecting identifiers, scoring..."):
        try:
            if uploaded_file:
                file_bytes = uploaded_file.getvalue()
                filename = uploaded_file.name
                analysis = pipeline.analyze(file_bytes, filename, profile)
            else:
                file_bytes = None
                filename = "pasted-text.txt"
                analysis = pipeline.analyze_pasted_text(pasted_text, profile)
        except Exception as e:
            st.error(f"Analysis failed: {e}")
            analysis = None

    if analysis:
        st.session_state.analysis = analysis
        st.session_state.file_bytes = file_bytes
        st.session_state.filename = filename
        st.session_state.result = None  # clear any previous redaction result

# ---------------------------------------------------------------------
# Findings + human-in-the-loop review
# ---------------------------------------------------------------------
if st.session_state.analysis:
    analysis = st.session_state.analysis
    detections = analysis["detections"]
    # Groups by (pii_type, value) -- a real ID value (e.g. an Aadhaar
    # number printed twice on one card) shouldn't show as two separate
    # rows to confirm. Confirming a group propagates to every physical
    # occurrence together; see pipeline.group_detections_for_review()'s
    # docstring for the redaction crash this also prevents.
    groups = group_detections_for_review(detections)

    st.divider()
    st.subheader(f"Found {len(groups)} item(s)")

    if analysis["excess_pii_alert"]:
        for item in analysis["excess_pii_alert"]:
            st.warning(
                f"This document contains **{item['count']}× {item['pii_type']}**, "
                f"which is not required for **{profile}**. Consider removing it before uploading."
            )

    with st.expander("Metadata findings (EXIF / hidden layers)"):
        metadata = analysis.get("metadata")
        findings = metadata["findings"] if metadata else []
        if findings:
            for f in findings:
                st.caption(f"**{f['field']}** ({f['category']}): {f['value']}")
        else:
            st.caption("No metadata findings for this file (or paste-text has no file to scan).")

    st.caption("Uncheck any item you don't want actioned. Defaults follow the selected profile.")

    if st.button("Accept all recommendations"):
        for d in detections:
            d["user_confirmed"] = d["policy_action"] in ("REMOVE", "MASK")

    confirmed = []
    for i, members in enumerate(groups):
        # All members share pii_type/value (the grouping key) and
        # policy_action/necessity (looked up purely from pii_type +
        # profile, so identical within a group) -- the highest-confidence
        # member is the most informative one to show for the rest.
        best = max(members, key=lambda d: d["confidence"])
        cols = st.columns([0.5, 1.2, 2, 1, 1, 1.3])
        checked = cols[0].checkbox("", value=best["user_confirmed"], key=f"det_{i}")
        cols[1].markdown(f"**{best['pii_type']}**")
        label = best["value"] if len(members) == 1 else f"{best['value']}  (×{len(members)})"
        cols[2].code(label)
        cols[3].markdown(f"conf {best['confidence']:.2f}")
        cols[4].markdown(f"`{best['policy_action']}`")
        cols[5].markdown(f"_{best['necessity'].lower()}_")
        for d in members:
            d["user_confirmed"] = checked
        confirmed.extend(members)

    with st.expander("Why these decisions? (reasons)"):
        for members in groups:
            best = max(members, key=lambda d: d["confidence"])
            occurrence_note = "" if len(members) == 1 else f" — found {len(members)} times"
            st.caption(
                f"**{best['pii_type']}** ({best['value']}){occurrence_note}: "
                f"{', '.join(best['reasons'])}"
            )

    st.divider()

    # Real P4 has no global redaction-mode override — action is per-type
    # from policy/profiles.yaml. The only real knob exposed is how FLAG-only
    # items are handled.
    flag_action = st.radio(
        "How should FLAGGED items (no clear policy) be handled?",
        ["REMOVE", "MASK", "SKIP"],
        horizontal=True,
        help="REMOVE fails closed (default) — a flagged item is redacted unless "
             "you uncheck it above. SKIP leaves flagged items untouched for later review.",
    )

    apply_disabled = st.session_state.file_bytes is None
    if apply_disabled:
        st.caption("Redaction needs the original file — pasted text has no file to redact "
                   "(detection + alert only for that path).")

    if st.button("Apply redaction", type="primary", disabled=apply_disabled):
        with st.spinner("Applying redaction to confirmed items..."):
            try:
                output_bytes, report = pipeline.apply(
                    st.session_state.file_bytes,
                    st.session_state.filename,
                    analysis,
                    flag_action=flag_action,
                )
                st.session_state.result = {"output_bytes": output_bytes, "report": report}
            except Exception as e:
                st.error(f"Redaction failed: {e}")

# ---------------------------------------------------------------------
# Results: side-by-side + download
# ---------------------------------------------------------------------
if st.session_state.result:
    st.divider()
    st.subheader("Result")

    report = st.session_state.result["report"]
    r1, r2, r3, r4, r5 = st.columns(5)
    r1.metric("Removed", report["removed"])
    r2.metric("Masked", report["masked"])
    r3.metric("Kept", report["kept"])
    r4.metric("Flagged", report["flagged"])
    r5.metric("No bbox (skipped)", report["no_bbox"])

    if report["verified"]:
        st.success("Verified — redacted values confirmed gone from the output's text layer.")
    else:
        st.warning("Not verified (verify=False was used or verification failed silently).")

    left, right = st.columns(2)
    with left:
        st.markdown("**Original**")
        st.caption(st.session_state.filename)
    with right:
        st.markdown("**Redacted**")
        st.caption("Real output from redaction.redact.apply_redactions().")

    st.download_button(
        "Download redacted file",
        data=st.session_state.result["output_bytes"],
        file_name=f"redacted_{st.session_state.filename}",
    )