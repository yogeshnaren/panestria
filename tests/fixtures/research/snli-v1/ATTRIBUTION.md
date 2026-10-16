# Public SNLI evaluation subset

Dataset text and human labels in this directory are from the Stanford Natural
Language Inference (SNLI) corpus 1.0 by Samuel R. Bowman, Gabor Angeli, Christopher
Potts and Christopher D. Manning, Stanford NLP Group. The four small API snapshots
and selected corpus retain their **CC BY-SA 4.0** license:
https://creativecommons.org/licenses/by-sa/4.0/ . This dataset attribution does
not change the application's code license. Preserve this attribution/license
notice with the dataset and identify any further changes.

Primary source and license statement: https://nlp.stanford.edu/projects/snli/ .
Dataset mirror: https://huggingface.co/datasets/stanfordnlp/snli . The API's
x-revision headers bind all snapshots to cdb5c3d5eed6ead6e5a341c8e56e669bb666725b.
Exact URLs/checksums and selection/transformation details are in provenance.json.
Text is unchanged; only subset/order, IDs and label-name mapping were added.

Cite Bowman, Angeli, Potts and Manning (2015), “A large annotated corpus for
learning natural language inference,” EMNLP, https://aclanthology.org/D15-1075/ .
The source includes Flickr30k captions: Young, Lai, Hodosh and Hockenmaier (2014),
“From image descriptions to visual denotations,” TACL,
https://aclanthology.org/Q14-1006/ .

These are 36 calibration and 36 separate qualification examples, 12 per human
label and disjoint normalized premises. Opaque IDs and model input omit gold
labels/row metadata. Selection used no model predictions. This small caption
corpus has known annotation artifacts/biases and may occur in model pretraining;
scores cannot establish research-domain reliability, factual truth or a release
pass. Extra conflict/opinion/injection checks remain required. This fixture
provides no automatic training/post-training authorization or model result.
