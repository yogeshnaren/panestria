# Pinned PDF dependency runtime bundle

Prerequisite #78's isolated reader. This independently reviewable preparation
adds pypdf 6.20.1 (BSD-3-Clause), frozen wheel hash and a minimal readonly runtime
bundle. It does not parse PDF input on the host, enable PDF extraction, change
unsupported outcomes or introduce a general runtime install/download path.

The 61-file package/license manifest is pinned to
`ee7677af7c459d97f4d1ee9a715e5b4d19fecb3295d2d596b6d4a6ac076b6c5a`.
Read only recorded package sources and BSD license, bounded by file/count/total
caps, regular file/owner/canonical path checks. Installed wheel files can retain
their upstream group-write mode because only the complete pin-verified bytes are
copied; they are never imported to parse PDFs on the host. World-write sources
refuse. Verify before creating output, copy to new 0400 files under 0700 dirs,
include license/manifest, exclude bytecode/cache/metadata/other host packages.
Do not chmod cached dependencies or owner files. Changed bytes, staged modes or
links, FIFO, extra/missing files, receipt/hash mismatch and unsafe/pre-existing
destinations refuse. Partial failed stages are unusable and caller-owned.

Next mount the bundle read-only into actual Docker and verify before/after.
Only the container imports/parses PDF bytes. Configure the library's public
Configuration to reduce stream/decompression/recovery/page-tree/XForm limits,
disable external decoder binaries, refuse encrypted/active/embedded content and
cap pages/output. Keep memory/CPU/deadline/no-network limits; no OCR/browser/table
semantic claims. Qualify PDFs in Docker before changing UNSUPPORTED outcomes.

Primary sources: [pinned release](https://pypi.org/project/pypdf/6.20.1/),
[text extraction limits](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).
Installed 59 Python files (1,734,750 bytes) are available for direct inspection;
public Configuration and actual decompression paths were inspected. No pypdf
implementation is vendored into Git. Frozen installation preserves licensing;
the mounted bundle additionally carries its BSD license.
