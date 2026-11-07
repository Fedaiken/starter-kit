---
title:     Lane Context Sizing — What One Lane Can Read in Full
topic:     "How a lane and the desk are sized before they fill. Built 2026-11-02 from FACOWORK: context_meter.py reads each window's real load from its transcript (the window is 1,000,000 tokens, measured); lane_budget.py predicts a lane's peak from its reads: bytes and the stamp refuses one past 600,000; the desk plans its own windows and hands over on predicted load. The kit's default, Savecraft's first calibration on 7 closed lanes: its lanes cost about a token per byte read, so the whole-read fit is 100,000 + 1.06 a byte (split past about 470 KB). HAZELHURST's 2026-09-24 measurements kept below."
keywords:  [lane, desk, context, compaction, sizing, task sheet, reads, bytes, budget, lane_budget, context_meter, calibrate, plan, NO PLAN, PLAN CHANGED, PLANNED HANDOVER, REPLAN, THIS DESK, IDLE NOT DONE, window tokens, split a unit, stamp, sheet_problems]
kind:      probe
retrieved: 2026-11-02
status:    current
---

# Lane Context Sizing — What One Lane Can Read in Full

**Why it's here.** A lane that compacts has failed its job: it loses what it read, and its report is no longer a read in full. A desk that compacts loses the job's thread. On 2026-11-02 a Savecraft desk warned of a crowded window on a guess while the owner's status line read 24%. The fix is measurement, ported that day from FACOWORK, where a lane had died at its ceiling, and from Savecraft into this kit.

## What the kit ships

| Tool | What it does |
|---|---|
| `scripts/context_meter.py --report` | Every live window of this project: tokens now, share of the window, peak, error state. Marks THIS WINDOW. Read from `~/.claude/projects/<the project folder's key>/<session>.jsonl`: a turn's load is `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`. Unreadable prints `METER UNREADABLE`, never a number. |
| `scripts/lane_budget.py <sheet>` | A lane's predicted peak from the bytes its `reads:` names. The stamp (`desk_record.sheet_problems`) refuses a sheet predicted past 600,000 tokens and names the remedy: split the unit. |
| `scripts/lane_budget.py --calibrate <home> ...` | Each closed lane of the homes: predicted, measured peak in its own window, residual; the least-squares line and the refit per reason. A lane past its prediction by more than 200,000 is `DRIFT` and fails the run until cited in this entry as `calibrate <lane>`. |
| `desk_record.py plan --lanes N` | The desk's own windows: how many lanes each takes. The stamp refuses `NO PLAN` without one, `REPLAN` when the meter says the window's rest no longer fits, and `PLANNED HANDOVER` when one lane past the planned count does not fit; past the count but under the line it prints and logs `PLAN CHANGED`. Backstop: no stamp at 60% (70% for a window planned past 60%). |
| Every desk act's banner | Ends with `THIS DESK — <name> <tokens> tokens, <n>% of its window — plan: ...` (`THIS WINDOW — ...`, no plan, in any window not the desk on record). Above it: `NEEDS THE DESK` (API error), `DEAD AT ITS CEILING`, `IDLE, NOT DONE` (turn ended mid-task 3+ minutes ago, no `done:` or `question:`), `FILLING` (80%). |

## The numbers, and where each comes from

- **The window is 1,000,000 tokens.** Measured in Savecraft: a desk carried 244,859 tokens on its turn of 2026-11-02 20:57Z, and the owner's next message read the status line as 24% (24.5%). FACOWORK measured the same ceiling: "Prompt is too long" at 970,937.
- **A window starts at about 37,000–43,500 tokens** before it reads anything: 30 Savecraft windows, 2026-11-01 to 02, first turns 36,869–43,540. The desk plan uses 43,540.
- **Lane budget 600,000** (60%), leaving room for FACOWORK's largest under-prediction (+200k) and the report written after reading.
- **The desk plan** prices a lane at 9,600 tokens of desk work, a byte the desk reads at 0.61, and a 50,000 reserve: FACOWORK's figures before its cuts, since this desk writes its sheets by hand and every lane acks. UNTIL CALIBRATED: no desk has yet been measured lane by lane.

## The kit's default fit: Savecraft's calibration 1, 2026-11-02

Until this project runs `lane_budget.py --calibrate` on its own closed lanes, the stamp prices them on this fit. Record each calibration below it.

`lane_budget.py --calibrate coordination/desks/data-design coordination/desks/data-model`, 7 closed lanes, priced on the whole-read fit FACOWORK shipped (125,000 + 0.52 a byte):

| Lane | Reason | Bytes read | Predicted | Measured | Residual |
|---|---|---|---|---|---|
| caravan-type | modding | 15,178 | 132,893 | 62,007 | −70,886 |
| data-shape | research | 120,227 | 187,518 | 255,030 | +67,512 |
| query-census | research | 198,123 | 228,024 | 233,255 | +5,231 |
| plan-check | checking | 146,145 | 200,995 | 215,007 | +14,012 |
| plan-review | checking | 189,477 | 223,528 | 270,316 | +46,788 |
| plan-write | drafting | 169,738 | 213,264 | 290,077 | +76,813 |
| work-shape | research | 129,959 | 192,579 | 258,928 | +66,349 |

No DRIFT, but six of seven were under-predicted. Savecraft's lanes loaded about a token per byte their sheet names, twice FACOWORK's rate: they read beyond `reads:` (the game's files, the save, the code they are routed to). Least squares over the seven: 80,570 + 1.0535 a byte. **Adopted, by FACOWORK's refit rule** (intercept rounded up to 25,000; rate the larger of least squares and the rate that holds the drift line, rounded up): **100,000 + 1.06 a byte** for every reason without its own fit. On it, data-shape is the worst at +27,589. It refuses past 471,698 bytes read. The evidence spans 15–198 KB, so a larger sheet is priced by extrapolation; the next calibration with bigger lanes moves the line. `design-latitude` (250,000 + 0.36) and `prescribed` (125,000 + 0.52) stay on FACOWORK's fit until five of their lanes close in a project and `--calibrate` refits them.

## HAZELHURST, 2026-09-24 (text = extracted `.txt` per email)

The numbers every project started from. One Windows machine; the ceiling is the model's context, not the OS.

| Lane (by topic) | Emails | Text read | Also | Outcome |
|---|---|---|---|---|
| statements | 19 | 61 KB | 39 scanned pages rendered | clean |
| maintenance | 23 | 153 KB | — | clean |
| occupancy | 26 | 200 KB | — | clean |
| ownership | 27 | 468 KB | a 92-page loan application | clean |
| other (checking) | 153 | 903 KB | headers and search, not a full read | clean |
| association | 71 | 1,990 KB | 223 scanned pages; two 160-page policies | **80% context**; finished only by handing page transcription to subagents |

The large lane's volume was an insurance policy's full text (450 KB, present three times) and two scanned governing documents (73 and 150 pages). Its sheet listed only the index, so its size was invisible at the stamp.

## How to size a lane

- **List every path the lane reads in full under `reads:`.** The budget can only price what the sheet names.
- **Split by document, not by date:** one lane per large instrument, the rest in chunks. Scanned pages are not bytes the budget sees; above about 40 of them, split by hand.
- **Read a long policy form by its declarations and endorsements**, and say which pages were read.
- **After a desk closes, calibrate its home** and record the table here; cite any DRIFT lane as `calibrate <lane>` with what it read beyond its sheet.
