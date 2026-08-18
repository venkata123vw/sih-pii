# DPDP Act 2023 — Compliance Mapping

How this tool's actual architecture and behavior map to the Digital Personal
Data Protection Act, 2023. Written for the deck's compliance slide — every
claim here points at a real, built mechanism, not an aspiration.

## What's answered by architecture, not by feature

> Nothing is stored. Nothing leaves the machine. Documents are processed in
> memory and discarded; no database, no upload, no telemetry. A tool built
> to protect PII that retained PII would have failed its own premise.

This single design decision answers **storage limitation** and **access
control** at once: there is no retained store of processed documents or
extracted PII for anyone to access, breach, or fail to delete on schedule,
because none exists after the process exits.

## What's answered by a built feature

**Purpose limitation** — the four context profiles
(`PUBLIC_DISCLOSURE`, `THIRD_PARTY_SERVICE`, `REGULATED_KYC`,
`INTERNAL_REVIEW`, `policy/profiles.yaml`) make the system's redaction
decision a function of *why* the document is being shared, not just *what*
is in it. The same Aadhaar number is removed for a public upload, masked
for a bank KYC check, and flagged-only for an internal audit — the tool
enforces that PII is only retained/disclosed to the extent the stated
purpose requires.

**Data minimisation** — every detection is independently classified
`REQUIRED` / `OPTIONAL` / `EXCESS` (`scoring/resolver.py`'s necessity
matrix) against the active profile. Anything marked `EXCESS` — present in
the document, but never needed for this purpose — surfaces in
`excess_pii_alert` and is shown to the user directly: *"this document
contains an Aadhaar number, which isn't required for this purpose."* This
is the part of the Act closest to a direct, demonstrable feature rather
than a design-level answer, and it's the piece almost no competing team
is likely to have built.

**Knowledge and consent** — *partially* answered, not fully. The
human-in-the-loop confirmation step (policy preview before processing,
detection review before writing output) means every proposed action is
shown to the user, who approves, adjusts, or rejects it individually
before anything is redacted. That is knowledge and consent in the only
sense a local, account-less tool can deliver — informed approval of each
action, not a data-sharing consent flow with an external party.

## Explicitly out of scope, and why

- **Consent management** (in the Act's sense — collecting, recording, and
  honoring a data principal's consent for a Data Fiduciary's processing)
  doesn't apply here: this tool has no accounts, no data principal
  relationship, and processes nothing on anyone's behalf after the file
  is discarded. The in-app confirmation step above is a different thing
  (user approving redaction actions on their own document), not this.
- **Breach notification** doesn't apply because there is no retained
  store of processed data to breach — see "answered by architecture."
  A breach-notification process exists to govern access to data that
  persists; none does here.
- **Grievance redressal** (a formal channel for a data principal to raise
  complaints against a Data Fiduciary) doesn't apply for the same reason
  consent management doesn't: no ongoing custodial relationship over
  anyone's data exists once a document is processed and discarded.

## Known limitation worth stating honestly

`policy/profiles.yaml`'s specific action assignments (e.g., which types get
`REMOVE` vs `MASK` under which profile) are the team's own first-pass
judgment calls, matched to the workplan's agreed matrix but not
independently reviewed by a compliance or legal source. If asked to defend
a specific cell, the honest answer is "reasoned from data-minimisation
principle X," not "verified against case law."
