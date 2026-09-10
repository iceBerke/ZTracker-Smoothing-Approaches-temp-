# PHASE B — zsmooth governance files

**Status line:** `PHASE B - zsmooth-governance - 934f617 - 2 decisions needed`

Date: 2026-09-10
Task: 002. Supersedes nothing. Verification basis:
`prompt_outputs/001-zsmooth-recon-audit.md`.

This task had no separate Phase A: `001` is that phase, by explicit instruction
in the request. This is the first report written under the rules that this task
itself creates.

---

## 0. Decisions needed (2)

Both are claims in the request that did not survive checking. Neither blocked
the work. In both cases the accurate version was written into the deliverable
and the mismatch is raised here for accept-or-correct, rather than the request's
wording being reproduced silently.

### D1. "The cross-method consensus check (Stage 1c) is the ONE place where input files are not independent" — CONTRADICTED

There are **three** places in Stage 1 where files interact, not one. Checked
against the source:

1. **`stage1_consistency`** (Stage 1a) compares every file's `Track_ID`,
   `Frame`, `X` and `Y` against the first file and raises `FatalDataError` on
   any mismatch:

   ```python
   raise FatalDataError(
       f"{mf.name} is not row-for-row comparable with {ref.name}: "
       + "; ".join(problems)
       + ". The files must describe the same tracks at the same frames."
   )
   ```

   One file's content can stop the entire run, so no other file gets processed.
   That is a stronger cross-file dependency than 1c's, not a weaker one.

2. **`stage1_zstep`** (Stage 1b) resolves the lattice spacing from the single
   file named by `--lattice-reference` (`g = spacings[lattice_reference_index]`)
   and raises `Z_STEP_UNVERIFIED`, `Z_STEP_MISMATCH` or
   `Z_STEP_REFERENCE_NOT_LATTICE`. All three are in `RUN_LEVEL_WARNING_CODES`:

   ```python
   RUN_LEVEL_WARNING_CODES = frozenset({
       "Z_STEP_MISMATCH", "Z_STEP_REFERENCE_NOT_LATTICE", "Z_STEP_UNVERIFIED",
   })
   ```

   so one file's lattice determines a code that `build_derivation_note` writes
   into **every** file's `derivation_note`.

3. **`stage1_cross_method`** (Stage 1c) — the consensus check the request means.

**What is true, and what I wrote into CLAUDE.md instead:** Stage 1 is the only
*stage* where files interact; within it there are three such places; and Stage
1c is the only one that produces a per-method **usability verdict**. That last
clause is what the shorthand is reaching for and it is worth keeping — but as
stated the claim is false, and stated in a governance document it would license
a future reader to assume Stages 1a and 1b are per-file.

**Second, smaller correction inside the same claim.** The request says Stage 1c
"alters no output value". Precisely: it alters no **smoothed value** — `z_smoothed`
never sees `inconsistent`. But it does alter CSV **content**, because it adds
`DO_NOT_USE:flagged-inconsistent` to `derivation_note`:

```python
note = build_derivation_note(mf.name, mf.name in inconsistent, rep.warnings)
```

`inconsistent` is read in exactly four places, all reporting or marking: the
note above, the do-not-use banner, the parameter-block `STATUS` string, and
eligibility for the CROSS-METHOD AGREEMENT table. None touches a computed value.
Scope of that check: the whole of `zsmooth.py`, by searching every occurrence of
`inconsistent`.

CLAUDE.md states it as "changes no smoothed value... so it does alter CSV
content, just not any computed value."

### D2. "Per-track Gamma goes negative on some tracks" — CONFIRMED but substantially understated

This claim appears in no part of `001`, the README or the source — the tool
performs no per-track fitting anywhere — so there was nothing to check it
against. I verified it empirically. Full method and numbers in section 5 below.

**It is true**: per-track Gamma does go negative. But it is a minor part of the
failure. The dominant finding is that **roughly half of all tracks produce no
converged fit at all**, and that fitted per-track alpha spans nearly the entire
search grid including its bounds.

Writing only the negative-Gamma half into CLAUDE.md would understate the case
for pooling and would leave a future reader thinking per-track estimation nearly
works. The stronger, accurate version is what I wrote.

**Decision requested:** confirm the expanded wording in CLAUDE.md Part B is
acceptable, or tell me to narrow it back to the negative-Gamma claim as
originally stated.

---

## 1. Blockers

None. Every deliverable was produced.

---

## 2. Proposed deviations

Listed, not done. Items 1 and 2 are carried forward unchanged from `001`; item 3
is new to this task.

1. **`requirements.txt` pins nothing but lower bounds.** `pandas 3.0.0` is
   installed against a declared `pandas>=2.0`. It works today. Nothing stops a
   future environment resolving something incompatible. Proposal: pin, or record
   a tested-versions block. Not touched. (Carried from `001`; RULES.md section 8
   now records the current versions, which is a record, not a pin.)

2. **The rest of the README's result numbers are unverified.** `001` spot-checked
   a sample and found most current; this task annotated the one block `001`
   established as stale. Roughly a dozen other numeric claims across the
   explanatory sections have never been systematically checked against a current
   run. Proposal: a dedicated audit task. Not done — the request explicitly
   scoped this to the one block, and rewriting unverified numbers is the failure
   mode being guarded against.

3. **NEW: `001`'s list of constants missing from the report's "Declared
   constants" block is itself incomplete.** The request said to take that list
   from `001` rather than re-derive it, and I did. While reading the constants
   for CLAUDE.md I noticed at least these further omissions that `001` did not
   name: `DEFAULT_MAD_THRESHOLD`, `MIN_HAMPEL_WINDOW`, `LATTICE_MULTIPLE_FRACTION`,
   `LATTICE_MIN_OCCUPANCY`, `LATTICE_ATOL`, `FITRANGE_STABLE_RATIO`,
   `FITRANGE_IMPROVEMENT_FACTOR`, `ALPHA_CI_PERCENTILES`,
   `CROSS_METHOD_THRESHOLD_MULTIPLES`, `CROSS_METHOD_SCORE_MULTIPLE`.

   I did **not** write these into CLAUDE.md, because the request specified
   `001`'s list. Instead CLAUDE.md flags `001`'s list as "a list of omissions
   found, not a full audit of omissions. Treat it as a lower bound." Proposal:
   a task to enumerate the omissions completely, or to make the block
   self-generating from the module namespace so it cannot drift again. Not done.

---

## 3. Re-verification of `001` before implementing

Per the two-phase protocol, `001`'s findings were re-checked before any file was
written. `001` was written earlier in the same session; the re-check confirms
nothing moved between the two.

```
$ git rev-parse HEAD
934f617e87bf00e2767497f225659b5b018b17c6

$ git rev-parse --abbrev-ref HEAD
main

$ git status --short
?? prompt_outputs/

$ git log --oneline
934f617 Add initial python files for running smoothing screening on ZTracker output data
```

File tree and sizes, compared against the table in `001` section TASK 1.2:
identical for every entry. `zsmooth.py` still 2703 lines and 155749 bytes;
`README.md` still 952 lines and 66222 bytes; `.gitignore` still 418 bytes; all
five `data/*.csv` and all nine `out/*` files byte-for-byte the same sizes. The
only addition to the tree since `001` is `prompt_outputs/001-zsmooth-recon-audit.md`
itself, at 75625 bytes.

Tracked file list unchanged from `001`: the same nine paths, including the five
`out/` entries that this task untracks.

Function names cited by the request were confirmed to exist before being written
into CLAUDE.md:

```
218:def window_bounds(...)
232:def hampel_flags(...)
263:def gap_aware_moving_average(...)
581:def stage1_cross_method(...)
727:def run_hampel(...)
740:def pooled_msd(...)
764:def fit_anomalous(...)
889:def bootstrap_alpha(...)
1000:def measure_transfer_exponents(...)
1633:def build_derivation_note(...)
1775:def gap_aware_moving_average_all(...)
1796:def derivation_stamp(...)
```

(Line numbers recorded here only as evidence that the grep ran; CLAUDE.md and
the chat report reference these by name only, per RULES.md section 5.)

Environment values were **not** re-measured. RULES.md section 8 takes them
verbatim from `001` as instructed: CPython 3.14.2 at
`C:\Users\berke.santos\AppData\Local\Programs\Python\Python314\python.exe`,
numpy 2.4.1, pandas 3.0.0, matplotlib 3.10.8, pip 26.2.1.

**Conclusion: `001` is not stale. Implementation proceeded.**

---

## 4. Claim-by-claim check of this request

Every factual claim in the request, checked before being relied on.

| Claim | Verdict | Evidence |
| --- | --- | --- |
| No virtual environment, no tests, machine-wide interpreter | CONFIRMED | Fresh tree listing shows no `.venv`/`venv`/`env` and no `tests/`; matches `001` TASK 1.4 / 1.7 |
| `.gitignore` header claims filename + SHA-256 is recorded | CONFIRMED | Line quoted verbatim below in section 6 |
| The tool records filename and path but computes no input hash | CONFIRMED | `001` TASK 3.7; `hashlib` is used only in `derivation_stamp`, which hashes arguments and constants |
| `out/` is half-tracked: PNGs and report committed, `_smoothed.csv` blocked by `*.csv` | CONFIRMED | `git ls-files` showed 4 PNGs + report tracked; the 4 `_smoothed.csv` absent |
| README stale block is pre-`1/alpha` (derivation-3) | CONFIRMED | `001` PROPOSED DEVIATION 2; README's own "Derivation stamp" section records the `9,9,7 -> 7,7,7` move |
| `001` locates the block and gives stale and current figures | CONFIRMED, but the block is **larger than `001` recorded** | See section 6 |
| `run_hampel` / `gap_aware_moving_average_all` iterate per track | CONFIRMED | Both loop `for start, stop in mf.slices` |
| `window_bounds` resolves windows in frame numbers | CONFIRMED | `np.searchsorted(frames, frames - half, ...)` |
| Two stochastic sites, seeded `default_rng`, not CLI-exposed | CONFIRMED | `001` TASK 2.1 / 2.2 |
| Stamp omits input data, `--lattice-reference` and seeds | CONFIRMED | `001` TASK 3.7 and PROPOSED DEVIATION 3 |
| `WINDOW_NOT_DETERMINED` routing is per-method via text prefix | CONFIRMED | `001` TASK 3.6; `f"{method_name}:" in tail` in `build_derivation_note` |
| Flagged and failed are different mechanisms with different outcomes | CONFIRMED | `001` TASK 3.8 and 4.7 |
| No recommendation logic in the source | CONFIRMED | `001` decision D4 |
| `SIGMA_STABILITY_TOL` / `_MIN_RUN` responsible for a method failing | CONFIRMED | `001` TASK 3.11: the `radius_median` failure text names the plateau rule |
| Whether those two were chosen before or after seeing results is not established | CONFIRMED as unestablished | No provenance recorded anywhere in the repository; searched README and source comments |
| Track lengths vary by roughly a factor of six | CONFIRMED | `001` TASK 4.9: min 42, max 264 points; ratio 6.29 |
| README "State at handover" takes the no-numbers position | CONFIRMED | `001` TASK 5.3 quotes it |
| Stage 1c is the ONE place files are not independent | **CONTRADICTED** | Decision D1 |
| Per-track Gamma goes negative on some tracks | **CONFIRMED but understated** | Decision D2, section 5 |
| Group 1 constants "fixed by convention, not tuned on any data" | **PARTIAL** | That they are dimensionless and scale-free is verifiable and verified. That they were never tuned is a provenance claim the repository does not record. CLAUDE.md says exactly this rather than asserting the stronger version. |

---

## 5. Measurement performed during this phase: per-track estimability

This is the only measurement taken in Phase B. It exists because request claim
D2 could not be checked against the code, the README or `001` — the tool does no
per-track fitting at all.

### Method

A read-only probe written to the scratch directory **outside the project**:

```
C:\Users\BERKE~1.SAN\AppData\Local\Temp\claude\C--Users-berke-santos-Documents-Python-Projects-ZTracker-Plugin-Smoothing\eba820a8-e41c-4d5f-9c32-37d3cbd14eaa\scratchpad\pertrack_probe.py
```

It imports `zsmooth` and reuses the tool's own functions rather than
reimplementing them. Nothing was written into the project and `zsmooth.py` was
not modified. Procedure:

1. `zs.load_method(...)` on the input CSV.
2. Stage 2 exactly as `main` performs it: window
   `next_odd_at_least(STAGE2_WINDOW_TRACK_FRACTION * median_track_length)`,
   floored at `MIN_HAMPEL_WINDOW`, threshold `STAGE2_MAD_THRESHOLD`, MAD floor
   `--z-step` = 2.0; flagged points set to `NaN`.
3. For each track slice independently: lay the track on a dense frame-indexed
   array with `NaN` in the gaps (the same construction `pooled_msd` uses), form
   the MSD over lags 1..8, and fit with the tool's own `zs.fit_anomalous`.
4. Lag range 1..8 was chosen because it is the pooled fit range the tool itself
   selected for these methods on this data, per `001`.

### Results, verbatim

```
== four_neighbor_median_results_table.csv  (per-track fit over lags 1..8, Stage-2 cleaned)
   tracks total                       : 70
   too short for the fit range        : 0
   anomalous fit did not converge     : 34
   fitted                             : 36
   of those, Gamma <= 0 (impossible)  : 1
   of those, intercept 2sig^2 <= 0    : 7
   of those, BOTH Gamma>0 and 2sig^2>0: 28
   Gamma  min / median / max          : -0.135 / 5.224 / 3864
   alpha  min / median / max          : 0.125 / 1.112 / 1.94
   track length (pts) min / max       : 42 / 264  (ratio 6.29x)

== single_pixel_results_table.csv  (per-track fit over lags 1..8, Stage-2 cleaned)
   tracks total                       : 70
   too short for the fit range        : 0
   anomalous fit did not converge     : 32
   fitted                             : 38
   of those, Gamma <= 0 (impossible)  : 1
   of those, intercept 2sig^2 <= 0    : 9
   of those, BOTH Gamma>0 and 2sig^2>0: 28
   Gamma  min / median / max          : -0.2837 / 5.284 / 864.2
   alpha  min / median / max          : 0.1 / 1.077 / 1.98
   track length (pts) min / max       : 42 / 264  (ratio 6.29x)

== four_neighbor_mean_results_table.csv  (per-track fit over lags 1..8, Stage-2 cleaned)
   tracks total                       : 70
   too short for the fit range        : 0
   anomalous fit did not converge     : 29
   fitted                             : 41
   of those, Gamma <= 0 (impossible)  : 3
   of those, intercept 2sig^2 <= 0    : 10
   of those, BOTH Gamma>0 and 2sig^2>0: 28
   Gamma  min / median / max          : -1.592 / 6.26 / 885.3
   alpha  min / median / max          : 0.135 / 0.895 / 1.945
   track length (pts) min / max       : 42 / 264  (ratio 6.29x)
```

### Reading

- **Negative Gamma: confirmed.** 1, 1 and 3 tracks across the three methods.
  Physically impossible, therefore estimation error rather than heterogeneity.
  This is the claim as the request stated it, and it holds.
- **But it is the smallest part of the failure.** 34, 32 and 29 of 70 tracks
  produce **no converged fit at all** — `fit_anomalous` returns `None`, meaning
  either a degenerate design matrix at every alpha or a best alpha sitting on a
  search bound.
- A further 7, 9 and 10 tracks return a **non-positive intercept**, so sigma is
  unresolvable for them.
- **Exactly 28 of 70 tracks survive on all three methods** with both Gamma and
  the intercept positive. The agreement of that count across three independent
  sampling methods is itself notable and was not investigated.
- Fitted alpha spans **0.100 to 1.98** against a search grid of
  `[ALPHA_SEARCH_MIN, ALPHA_SEARCH_MAX]` = `[0.05, 2.00]`. Hitting within one
  grid step of both bounds is the signature of a fit that is not identified.
- Track length ratio **6.29x**, independently confirming the request's "roughly
  a factor of six".

### Scope of this measurement — stated precisely

- Measured under **the tool's own model** (`2*sigma^2 + Gamma*tau^alpha`) and
  **the pooled fit range applied per track**, on **Stage-2-cleaned** data, on
  **three** of the five input methods.
- A different per-track procedure — a shorter fit range, a fixed alpha, a
  hierarchical or partially pooled model, or tracks filtered by length first —
  **was not tried** and might behave differently.
- This measurement establishes that naive per-track substitution fails on this
  data. It does **not** establish that per-track estimation is impossible in
  principle, and CLAUDE.md does not claim that.
- **This is not the justification for pooling.** The justification is the
  comparability argument in CLAUDE.md Part A, which holds regardless of whether
  per-track estimation would work.

---

## 6. Finding: the README stale block is larger than `001` recorded

**This is a self-correction against my own prior phase.**

`001` PROPOSED DEVIATION 2 identified the stale block as README lines 917 and
925–926: the `1.2812×` cross-method spread and the three `w_req` values
`4.4977, 3.9662, 3.5105` rounding to `W_smooth = 5`.

On reading the full `## Cross-method agreement` section for this task, a
**third** stale statement is present that `001` did not name. Current text,
quoted verbatim:

```
On the current dataset the three eligible methods give `sigma_fit` within 1.025×
of each other and identical Hampel windows, with smoothing windows of 9, 9 and 7.
```

`smoothing windows of 9, 9 and 7` is derivation-3 output. The README's own
"Derivation stamp" section states the correction's effect:

```
**Any `_smoothed.csv` written before derivation-4 is stale.** The `1/alpha`
correction moved the sound methods from `W = 9, 9, 7` to `7, 7, 7` and
`radius_mean` from 5 to 11.
```

So the README contradicts itself across two sections, and `001` caught only one
side of it.

**How the correct statement was established:** by comparing the sentence against
the README's own derivation-stamp section and against `001` TASK 4.1, which
records current `W_smooth` as 7 / 7 / 7 for the three sound methods and 11 for
`radius_mean`. No new run was performed and no figure was re-derived.

**Complication handled in the annotation.** That sentence is **mixed**: the same
sentence contains two claims that are current and one that is stale.
`sigma_fit within 1.025×` matches `001`'s recorded fitted sigmas (4.31109,
4.39702, 4.41805; max/min = 1.0248), and `identical Hampel windows` matches
`001`'s recorded derived Hampel window of 5 for all three eligible methods. Only
`smoothing windows of 9, 9 and 7` is stale.

The annotation therefore names which clauses are stale and which are current,
rather than marking the whole sentence. Marking a current claim as stale would
be its own error, and a blanket warning over a mixed sentence teaches a reader
to distrust the correct half.

The annotation also records that the **argument** of the section is unaffected —
that `k` cancels out of any ratio between methods, and that rounding hides real
disagreement, are both structural points that do not depend on the stale
figures. Only the illustrative numbers are wrong.

**Scope of this finding:** the `## Cross-method agreement` section only. No other
README section was re-audited in this task, and `001`'s caveat stands that most
sampled numbers elsewhere were current but the set was not exhaustive.

---

## 7. What changed

### 7.1 Files

| File | Action |
| --- | --- |
| `RULES.md` | **Created.** Process governance, 9 sections, per the request. |
| `CLAUDE.md` | **Created.** Project governance, split into Part A (tool properties) and Part B (dataset observations) with a warning between them. |
| `.gitignore` | **Modified.** Two edits: corrected the input-identity comment; added `out/`. |
| `README.md` | **Modified.** One annotation block inserted in `## Cross-method agreement`. No existing text altered or deleted. |
| `out/` (5 files) | **Untracked** via `git rm --cached`. All five remain on disk. |
| `prompt_outputs/002-zsmooth-governance-phaseB.md` | **Created.** This file. |
| `prompt_outputs/002-zsmooth-governance-diff.txt` | **Created.** The diff artifact. |
| `prompt_outputs/INDEX.md` | **Created**, with lines for 001 and 002. |

`zsmooth.py` was **not modified**. No constant was changed. Nothing was
refactored. No test was added. No package was installed. No commit was made.

### 7.2 `.gitignore`, before and after

Before:

```
# ---- Data: inputs and outputs are not tracked ----
# Record input identity (filename + SHA-256) in run output instead.
data/
```

After:

```
# ---- Data: inputs and outputs are not tracked ----
# Run output records input identity as FILENAME AND ABSOLUTE PATH only -- in the
# report's "Inputs:" block and in each method's parameter block "input" field.
# NOT IMPLEMENTED: a content hash (SHA-256) of each input. Intended, not present.
# Until it exists, nothing in the output can tell you which data produced it --
# the derivation stamp hashes the arguments, never the inputs. See CLAUDE.md,
# "The derivation stamp's blind spots".
data/
```

The original comment described intended future behaviour in the present tense.
The replacement states what is actually recorded, marks the hash as intended and
absent, and states the consequence of its absence.

Second edit, `out/` added above the `*.csv` rule with a comment explaining the
half-tracked history it resolves.

### 7.3 Files untracked by `git rm --cached`

Exactly these five, verbatim from the command output:

```
rm 'out/four_neighbor_mean_results_table_diagnostics.png'
rm 'out/four_neighbor_median_results_table_diagnostics.png'
rm 'out/radius_mean_results_table_diagnostics.png'
rm 'out/single_pixel_results_table_diagnostics.png'
rm 'out/zsmooth_parameters_report.txt'
```

**All five are still present on disk**, confirmed after the operation — the
directory still holds all nine files at their original sizes, including the four
`*_smoothed.csv` that were never tracked:

```
four_neighbor_mean_results_table_diagnostics.png   104689
four_neighbor_mean_results_table_smoothed.csv      652864
four_neighbor_median_results_table_diagnostics.png 103470
four_neighbor_median_results_table_smoothed.csv    652632
radius_mean_results_table_diagnostics.png          109145
radius_mean_results_table_smoothed.csv             923192
single_pixel_results_table_diagnostics.png         102908
single_pixel_results_table_smoothed.csv            652241
zsmooth_parameters_report.txt                      105922
```

Tracked file list afterwards: `.gitignore`, `README.md`, `requirements.txt`,
`zsmooth.py`.

**Note on what this means for history:** untracking removes these from the
*index*, not from history. The versions committed at `934f617` remain in the
repository and are still retrievable from that commit. Nothing was destroyed.

### 7.4 `git status --short`

Verbatim, after `git add -N` on the new files:

```
 M .gitignore
 A CLAUDE.md
 M README.md
 A RULES.md
D  out/four_neighbor_mean_results_table_diagnostics.png
D  out/four_neighbor_median_results_table_diagnostics.png
D  out/radius_mean_results_table_diagnostics.png
D  out/single_pixel_results_table_diagnostics.png
D  out/zsmooth_parameters_report.txt
 A prompt_outputs/001-zsmooth-recon-audit.md
 A prompt_outputs/002-zsmooth-governance-phaseB.md
 A prompt_outputs/INDEX.md
?? prompt_outputs/002-zsmooth-governance-diff.txt
```

The five `out/` entries show `D ` in the **staged** column: they are deleted from
the index by `git rm --cached` and still present in the working tree. That is the
intended result and is not a pending file deletion.

The diff artifact itself shows as `??`. It is deliberately not `add -N`'d — a
diff cannot contain itself. It is listed in `DELIVERABLES` and will be picked up
at commit time.

### 7.5 `git diff HEAD --stat`

Verbatim:

```
 .gitignore                                         |   11 +-
 CLAUDE.md                                          |  527 +++++++
 README.md                                          |   21 +
 RULES.md                                           |  358 +++++
 ...our_neighbor_mean_results_table_diagnostics.png |  Bin 104689 -> 0 bytes
 ...r_neighbor_median_results_table_diagnostics.png |  Bin 103470 -> 0 bytes
 out/radius_mean_results_table_diagnostics.png      |  Bin 109145 -> 0 bytes
 out/single_pixel_results_table_diagnostics.png     |  Bin 102908 -> 0 bytes
 out/zsmooth_parameters_report.txt                  | 1501 --------------------
 prompt_outputs/001-zsmooth-recon-audit.md          | 1484 +++++++++++++++++++
 prompt_outputs/002-zsmooth-governance-phaseB.md    |  594 ++++++++
 prompt_outputs/INDEX.md                            |   12 +
 12 files changed, 3006 insertions(+), 1502 deletions(-)
```

**SELF-CORRECTION.** An earlier draft of this section carried estimated figures
written before the diff was generated — `.gitignore 10`, `CLAUDE.md 461`,
`RULES.md 330`, `out/zsmooth_parameters_report.txt 1394`, and `(added)` in place
of counts for the three `prompt_outputs/` entries. Every one of those was wrong.
They were replaced with the verbatim output above, established by running
`git diff HEAD --stat` after `git add -N`. The draft was corrected before this
phase reported, which RULES.md section 2 permits; nothing that had already
reported was altered.

The error is recorded rather than quietly fixed because it is exactly the
failure RULES.md section 6 exists to catch: a summary written from expectation
rather than from the command output, which would have disagreed with the diff
artifact sitting beside it.

**One figure in the table above is necessarily approximate.** The row for
`prompt_outputs/002-zsmooth-governance-phaseB.md` counts this file's own lines,
so revising this file changes it. The value shown is from the run that produced
the diff artifact. The stat in the chat report, generated last, is authoritative.

---

## 8. Notes on the deliverables

### 8.1 RULES.md

Nine sections as specified. Two points worth recording about how they were
written:

- **Section 8 does not re-measure the environment.** The request specified
  taking the values from `001`, and it does. The section also states that a
  pinned environment is intended but not created, and that a future session must
  not assume `.venv/` exists or create one silently.
- **Section 9 distinguishes the two irreversible things** — `data/` (gitignored,
  so git offers no protection) and `prompt_outputs/` (holds reasoning that
  existed only in conversations that no longer exist) — from `out/`, which is
  regenerable build output. That distinction is what makes the `git rm --cached`
  in this same task safe.

### 8.2 CLAUDE.md

Structured Part A / Part B with a blockquoted warning between them explaining
why the separation exists: that a Part B value promoted into Part A turns a
general instrument into a device tuned to one experiment, and that the resulting
failure is invisible because the tool still runs and still produces plausible
numbers.

**Part B contains no measured values**, per the request and per the README's own
`State at handover` doctrine. It gives the command to run and the parameter-block
fields to read instead. The one exception is structural rather than numeric:
Part B says track lengths vary by "roughly a factor of six", which the request
itself supplied as a shape and which I confirmed at 6.29x.

Three things in CLAUDE.md deviate from the request's literal wording, all
upward in accuracy and all recorded above: D1 (the "ONE place" correction), D2
(the expanded per-track finding), and the Group 1 provenance qualification in
the constants section.

### 8.3 README annotation

Inserted as a blockquote immediately before the first stale statement, so a
reader meets the warning before the numbers. Nothing existing was edited or
deleted — the stale text remains exactly as written, which is deliberate: it is
evidence of what the tool used to produce, and the request explicitly said not
to rewrite it.

---

## 9. Matters next

1. **The two decisions in section 0.**
2. **Approval of this report**, after which a commit message is proposed — not
   before, per RULES.md section 7.
3. **The `SIGMA_STABILITY_TOL` / `SIGMA_STABILITY_MIN_RUN` sensitivity sweep**,
   recorded as planned-and-not-run in CLAUDE.md. These two constants determine
   which methods survive derivation at all, and their provenance is unrecorded.
   This is the largest unexamined lever in the tool.
4. **The heterogeneity detector**, recorded as planned-and-not-built. Pooling
   weights tracks by pair count and lengths vary six-fold; whether long and
   short tracks differ systematically is untested.
5. **Extraction of the cross-method consensus check** into a separate script,
   recorded in CLAUDE.md as pending. It is a method-selection diagnostic that
   currently lives inside the smoothing tool.
6. **PROPOSED DEVIATION 3** — a complete audit of what the report's "Declared
   constants" block omits, or making it self-generating.

---

## Provenance of this file

Written before the chat report, per the rules this task creates. The chat report
is derived from it and is a strict subset. The only file written outside the
project during this phase was the read-only probe in the scratch directory named
in section 5.

--- END OF REPORT ---
