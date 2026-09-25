---
title:     Lane Context Sizing — What One Lane Can Read in Full
topic:     "Measured in HAZELHURST on its 2026-09-24 email-dump desk: lanes that read up to about 470 KB of text (or 900 KB skimmed) finished cleanly; one lane, at about 2 MB of text plus 223 scanned pages and 324 policy pages, reached 80% context and survived only by farming reads to subagents. Size a lane's reading before stamping it; the stamp does not measure it yet."
keywords:  [lane, desk, context, compaction, sizing, task sheet, reads, bytes, scanned pages, split a unit, email dump, subagents, stamp, sheet_problems]
kind:      probe
retrieved: 2026-09-24
status:    current
---

# Lane Context Sizing — What One Lane Can Read in Full

**Why it's here.** On 2026-09-24 a HAZELHURST desk split an email dump into lanes by topic and gave the largest bucket, an association's mail, to one lane. It reached 80% of its context before it finished; a lane that compacts has failed its job. A lane that compacts loses what it read, and its report can no longer be trusted as a read in full. The numbers below were measured there, on this machine; they are the calibration every project starts from until it measures its own (one Windows machine; the ceiling is the model's context, not the OS).

## Measured in HAZELHURST, 2026-09-24 (text = extracted `.txt` per email)

| Lane (by topic) | Emails | Text read | Also | Outcome |
|---|---|---|---|---|
| statements | 19 | 61 KB | 39 scanned pages rendered | clean |
| maintenance | 23 | 153 KB | — | clean |
| occupancy | 26 | 200 KB | — | clean |
| ownership | 27 | 468 KB | a 92-page loan application | clean |
| other (checking) | 153 | 903 KB | headers and search, not a full read | clean |
| association | 71 | 1,990 KB | 223 scanned pages; two 160-page policies | **80% context**; finished only by handing page transcription to subagents |

The large lane's volume was two things: an insurance policy's full text (450 KB, present three times) and two scanned governing documents (73 and 150 pages).

## How to size a lane

- **Measure before stamping.** Sum the text bytes and count the scanned pages the lane must read in full, the same way on any OS: `<venv python> -c "import sys,pathlib; print(sum(p.stat().st_size for a in sys.argv[1:] for p in pathlib.Path(a).rglob('*.txt')))" <folders>` (a single file: its size), plus `len(pypdf.PdfReader(p).pages)` for each scan.
- **Split above about 500 KB of full-read text, or above about 40 scanned pages.** Split by document, not by date: one lane per large instrument (a governing document, a policy), and the rest in chunks.
- **Read a long policy form by its declarations and endorsements**, and say which pages were read. Only those pages carry values specific to the insured.
- **List every path the lane reads in full under `reads:`.** The large lane's sheet listed only the index, so its size was invisible at the stamp.

## Not built yet

The stamp (`scripts/desk_record.py`, `sheet_problems`) checks that `reads:` paths exist. It does not measure them. The structural fix is for the stamp to sum the text bytes and scanned pages under `reads:` and refuse a sheet above a ceiling. The thresholds above are the calibration. Until that check exists, sizing is a desk step taken from this entry.
