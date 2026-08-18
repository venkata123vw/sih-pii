"""
app.py — P5: Interface & Integration

Wired to REAL teammate modules via pipeline.py (detection, scoring,
redaction all real now; ingestion is real code but still a stub body).
See pipeline.py's module docstring for the full list of integration
fixes and known bugs found while wiring this up.

Run with:  streamlit run app.py
"""

import streamlit as st
import pipeline

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
st.caption("SIH1668 — wired to real detection/scoring/redaction modules. "
           "Ingestion is still a stub, so every upload shows the same "
           "fixed sample detections until real OCR/extraction lands.")

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

    st.divider()
    st.subheader(f"Found {len(detections)} item(s)")

    if analysis["excess_pii_alert"]:
        for item in analysis["excess_pii_alert"]:
            st.warning(
                f"This document contains **{item['count']}× {item['pii_type']}**, "
                f"which is not required for **{profile}**. Consider removing it before uploading."
            )

    with st.expander("Metadata findings (EXIF / hidden layers)"):
        st.caption("No metadata scanner output yet — placeholder for P2's metadata stage.")

    st.caption("Uncheck any item you don't want actioned. Defaults follow the selected profile.")

    if st.button("Accept all recommendations"):
        for d in detections:
            d["user_confirmed"] = d["policy_action"] in ("REMOVE", "MASK")

    confirmed = []
    for i, d in enumerate(detections):
        cols = st.columns([0.5, 1.2, 2, 1, 1, 1.3])
        checked = cols[0].checkbox("", value=d["user_confirmed"], key=f"det_{i}")
        cols[1].markdown(f"**{d['pii_type']}**")
        cols[2].code(d["value"])
        cols[3].markdown(f"conf {d['confidence']:.2f}")
        cols[4].markdown(f"`{d['policy_action']}`")
        cols[5].markdown(f"_{d['necessity'].lower()}_")
        d["user_confirmed"] = checked
        confirmed.append(d)

    with st.expander("Why these decisions? (reasons)"):
        for d in detections:
            st.caption(f"**{d['pii_type']}** ({d['value']}): {', '.join(d['reasons'])}")

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