# Current R0 progress

Technical G0 PASS on `f161193ed31918592015ec9e68163d31d77cb0ae`: 160 non-live tests plus the fresh-Ubuntu live case. All 20 required groups observed. Owner handoff remains PENDING; R1 has not started.

The dev-api/r0-demo port conflict is repaired. The demo reuses an authenticated running API or owns and cleans up a temporary API. The read-only browser snapshot is running at http://127.0.0.1:8870/. See [current review](reviews/R0-DEMO-REVIEW.md) and [gate](../evidence/G0/evaluation.json).

Original specs, skills ZIP and hardware probe inventories are preserved. The current full regression ran natively after a verified review-database backup. All review data was restored and checked, and the existing API process was resumed. The separate fresh VM passed the live startup case and demo.

Review this candidate and its evidence before recording owner acceptance. R1 and the R3 MVP remain separate work.
