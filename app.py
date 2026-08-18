"""
app.py — P5: Interface & Integration

Built entirely against pipeline.py's STUB functions. Nothing here depends
on P1/P2/P3/P4's real code. When their modules land, only pipeline.py
changes (swap the stub for the real import) — this file stays as-is.

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
st.caption("SIH1668 — demo build. Interface wired against stub data; "
           "swap in real modules as they land.")

# ---------------------------------------------------------------------
# Entry mode (P5 item 10)
# ---------------------------------------------------------------------
mode = st.radio(
    "How are you using this?",
    ["Before I upload (I'm the individual user)", "Reviewing what I received (I'm the processing entity)"],
    horizontal=True,
)
is_individual = mode.startswith("Before")

st.divider()

# ---------------------------------------------------------------------
# Context profile dropdown (section 3b)
# ---------------------------------------------------------------------
col_a, col_b = st.columns([2, 3])
with col_a:
    profile = st.selectbox("Context profile", pipeline.PROFILES, index=1)
with col_b:
    profile_notes = {
        "PUBLIC_DISCLOSURE": "Nothing survives — every identifier removed.",
        "THIRD_PARTY_SERVICE": "Government IDs removed; name/email kept since the service needs them.",
        "REGULATED_KYC": "The one legally-required identifier is kept; everything else removed.",
        "INTERNAL_REVIEW": "Alert-only. Nothing is redacted — everything is flagged and reported.",
    }
    st.info(profile_notes[profile])

st.divider()

# ---------------------------------------------------------------------
# Input: file upload OR paste-text (P5 item 9)
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
        progress = st.progress(0, text="Extracting...")
        if uploaded_file:
            file_bytes = uploaded_file.getvalue()
            filename = uploaded_file.name
            progress.progress(40, text="Detecting...")
            analysis = pipeline.analyze(file_bytes, filename, profile)
        else:
            file_bytes = None
            filename = "pasted-text.txt"
            progress.progress(40, text="Detecting...")
            analysis = pipeline.analyze_pasted_text(pasted_text, profile)
        progress.progress(100, text="Done")
        progress.empty()

    st.session_state.analysis = analysis
    st.session_state.file_bytes = file_bytes
    st.session_state.filename = filename
    st.session_state.result = None  # clear any previous redaction result

# ---------------------------------------------------------------------
# Findings + human-in-the-loop review (section 3c, stage 2)
# ---------------------------------------------------------------------
if st.session_state.analysis:
    analysis = st.session_state.analysis
    detections = analysis["detections"]

    st.divider()
    st.subheader(f"Found {len(detections)} item(s)")

    # Excess-PII alert banner (P5 item 8)
    if analysis["excess_pii_alert"]:
        for item in analysis["excess_pii_alert"]:
            st.warning(
                f"This document contains **{item['count']}× {item['pii_type']}**, "
                f"which is not required for **{profile}**. Consider removing it before uploading."
            )

    # Metadata findings shown separately (P5 item 11) — stub has none yet,
    # placeholder so the section exists when P2's metadata scanner lands
    with st.expander("Metadata findings (EXIF / hidden layers)"):
        st.caption("No metadata scanner output yet — placeholder for P2's metadata stage.")

    st.caption("Uncheck any item you don't want actioned. Defaults follow the selected profile.")

    if st.button("Accept all recommendations"):
        for d in detections:
            d["user_confirmed"] = d["policy_action"] in ("REMOVE", "MASK")

    # Detection review checklist — grouped by type, editable
    confirmed = []
    for i, d in enumerate(detections):
        cols = st.columns([0.5, 1.2, 2, 1, 1, 1.3])
        checked = cols[0].checkbox("", value=d["user_confirmed"], key=f"det_{i}")
        cols[1].markdown(f"**{d['pii_type']}**")
        cols[2].code(d["value"])
        cols[3].markdown(f"conf {d['confidence']}")
        cols[4].markdown(f"`{d['policy_action']}`")
        cols[5].markdown(f"_{d['necessity'].lower()}_")
        d["user_confirmed"] = checked
        confirmed.append(d)

    st.divider()

    # Redaction mode toggle (P5 item 6)
    redaction_mode = st.radio(
        "Redaction mode for confirmed items",
        ["Full removal", "Masking"],
        horizontal=True,
    )

    if st.button("Apply redaction", type="primary"):
        with st.spinner("Applying redaction to confirmed items..."):
            output_bytes, report = pipeline.apply(
                st.session_state.file_bytes or b"",
                confirmed,
            )
        st.session_state.result = {"output_bytes": output_bytes, "report": report}

# ---------------------------------------------------------------------
# Results: side-by-side + download (P5 items 3, 5)
# ---------------------------------------------------------------------
if st.session_state.result:
    st.divider()
    st.subheader("Result")

    report = st.session_state.result["report"]
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Removed", report["removed"])
    r2.metric("Masked", report["masked"])
    r3.metric("Kept", report["kept"])
    r4.metric("Flagged", report["flagged"])

    left, right = st.columns(2)
    with left:
        st.markdown("**Original**")
        if st.session_state.file_bytes:
            st.caption(st.session_state.filename)
        else:
            st.caption("(pasted text — no file preview)")
    with right:
        st.markdown("**Redacted**")
        st.caption("Stub output — real redacted file once P4's module is wired in.")

    if st.session_state.result["output_bytes"]:
        st.download_button(
            "Download redacted file",
            data=st.session_state.result["output_bytes"],
            file_name=f"redacted_{st.session_state.filename}",
        )
