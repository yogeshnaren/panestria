# Versioned human-label entailment preflight

AOS-022 needs real human labels rather than an agent labeling its own rubric as
human-reviewed. Use a small public SNLI 1.0 subset with the original labels and
text, retaining CC BY-SA 4.0 attribution separately from application code.
Stanford's primary corpus page confirms manually labeled premise/hypothesis
pairs. Four bounded Hugging Face Dataset Viewer pages have x-revision headers
matching cdb5c3d5eed6ead6e5a341c8e56e669bb666725b; exact snapshots and selected
fixtures are checksum-pinned. Full source card/annotation and rights metadata
were inspected through the HF datasets skill and REA direct-source workflow.

Select 36 calibration and36 held-out qualification cases, 12 per label and
no shared normalized premise across folds. Selection uses no model predictions.
Original text remains unchanged; opaque IDs omit gold, cases sort by ID, and an
explicit model-input projection contains only ID/premise/hypothesis. Preserve
source split/row, gold labels and snapshots for the host evaluator only.

Map premise-entails-hypothesis to SUPPORTED, contradiction to CONTRADICTED and
neutral to INSUFFICIENT. This is semantic entailment preflight, not world-truth
validation. The scorer refuses missing/duplicate/foreign/invalid predictions,
retains abstention, and reports confusion, coverage, answered accuracy and
supported precision. No support predictions means precision UNKNOWN; all
abstentions also leave answered accuracy UNKNOWN. It has no release/model
qualification flag. Synthetic scorer tests cannot be actual model calibration.

The caption-domain dataset is small and has annotation artifacts, biases and
possible model pretraining contamination. Additional research-domain partial,
opinion, correlated/conflicting-source and injection checks remain required.
No SOTA/complete AOS022/release acceptance follows from a small score. Actual
model/version/prompt/privacy/usage observations and separate qualification are
still needed, with independent model family where supported and UNKNOWN when
unavailable. Fixture preparation authorizes no inference or training by itself.

Primary source: https://nlp.stanford.edu/projects/snli/ . Source/label metadata:
https://huggingface.co/datasets/stanfordnlp/snli . The fixture directory contains
full attribution, original-paper links, revisions, checksums and changes.
