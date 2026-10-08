# Incident replay dataset

This is a planned test dataset assembled from friend-reported incident leads in `ATTACH_TN_incident_notes.md`. It is not an independently verified incident database, and no replay has been run. The source note's heading says “verified via WebFetch,” but that is not treated as verification here. The 20 Tamil Nadu cases TN-A through TN-T and three comparison leads from Kerala, Maharashtra, and Gujarat are represented as 23 rows. Aggregate notes are excluded because they are not case-level incidents.

## Fields and coding

- `id` preserves the source-note case label. `date` is ISO `YYYY-MM-DD` when a date is reported with sufficient precision; it is blank when unresolved. `date_uncertain` is `true` where the note signals a date ambiguity. TN-D records July 2 with uncertainty because the note also says July 3; KL has no date because the note says October 1, 2025 with a question mark.
- Counts (`deaths`, `injuries`, `rescuer_deaths`) are blank when the source note gives no count. Do not read blank as zero.
- The yes/no/unknown fields `ppe`, `gas_test`, `machine_present`, and `ms_act_invoked` use `Y`, `N`, and `U`. `U` means unreported or unresolved; `N` is used only where the note explicitly reports absence. “No gear” maps to `ppe=N`; absence of a gas-test mention maps to `gas_test=U`, not `N`.
- `source_urls` lists the URLs present in the source notes. `evidence_status` is uniformly `FRIEND_REPORTED`; URLs and descriptions have not been independently checked for this extraction.
- `unknowns_and_cautions` retains important ambiguity and missing information. TN-B's claim that all six were rescuers is explicitly ambiguous, not coded as six rescuer deaths. A machine being present does not establish that it worked successfully or made the job safe. TN-R is reported as a cave-in, so the dataset preserves a non-atmospheric hazard pathway outside any gas-only gate.
- `design_test_candidate` records a possible scenario for testing a proposed workflow. These are replay hypotheses, not causal conclusions or proof of safety. No blocked-death percentage or other causal estimate is derived.

## Legal and scope limits

FIR descriptions are transcribed as reported, with qualifiers where the source note is incomplete. They are not verified charges, legal advice, or a basis for automatically forcing or inferring statutory sections. In particular, a report that the MS Act was not invoked is retained as a reported status, not corrected by inference. Reported compensation is kept descriptive and may be announced, offered, mandated, or partly paid; it is not normalized into a confirmed payment. Victim names are omitted because they are not needed for the planned workflow tests.

The dataset supports review of data handling, uncertainty, entry controls, rescue cascades, employer/contractor handoffs, and non-gas hazards. It does not establish incident causation, legal liability, prevalence, intervention effectiveness, or safety performance.
