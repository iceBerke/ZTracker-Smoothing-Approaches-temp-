# CLAUDE.md

**Read `RULES.md` first.**

`RULES.md` is about the **process**: how work is phased, what evidence a claim
needs, where the decision record lives, what may not be changed without asking.
This file is about the **project**: what `zsmooth.py` is, what it guarantees,
and what is merely true of the data it currently happens to be tested on.

Where the two disagree, RULES.md wins.

---

## The single most important thing in this file

This document is split into two parts, and **the split is the point**:

- **Part A — TOOL PROPERTIES.** Always true. What the code guarantees on any
  dataset it is given.
- **Part B — DATASET OBSERVATIONS.** True of the current test data only.

> ### WARNING: DO NOT MOVE A FACT FROM PART B INTO PART A
>
> A Part B observation is a measurement of one dataset. It is **not** something
> the code should assume, **not** a value to hardcode, **not** a default to bake
> in, and **not** a property to preserve when the tool changes.
>
> The separation exists because the failure it prevents is invisible. If a
> measured value from this dataset is written into the code as a constant, or
> treated as a behaviour to protect, the tool silently stops being a
> general-purpose instrument and becomes a device tuned to one experiment. It
> will still run on new data. It will still produce plausible numbers. Nothing
> will look wrong. The results will be wrong.
>
> Every value in Part B is written as a **shape**, not a number, for the same
> reason. If you need a number, run the tool and read the report.

---

# PART A — TOOL PROPERTIES

Always true. These describe the code's guarantees, independent of dataset.

## Purpose

`zsmooth.py` is a **general-purpose smoothing approach that happens to be tested
on this dataset.** It is not a tool built for this data.

It rejects transient outliers from Z-coordinate trajectories exported by the
ZTracker_Fiji Tool 3 (TopoJ) plugin, then smooths Z(t), so that speeds derived
downstream are not dominated by measurement noise or single-frame artifacts.

**Any change that makes the tool fit this dataset better at the cost of
generality is wrong**, even if it improves every number in the current report.
That is the trade this project exists to refuse.

## Independence: per file, and per track within a file

Smoothing and outlier rejection are performed **per input CSV**, and within a
file **per track**. A window never crosses a track boundary.

The mechanism is that `run_hampel` and `gap_aware_moving_average_all` both
iterate over `mf.slices` — the contiguous row ranges of one track each — and
call the underlying single-track routine on one slice at a time. No operation
sees two tracks at once.

**Precise scope of "each input CSV is processed independently":** this holds for
everything that produces a smoothed value. It does **not** hold for Stage 1
diagnosis, where files are deliberately compared against each other. See
"Where files are not independent" below.

## Gap awareness

Both the smoothing window and the Hampel window are **gap-aware**: a window is
resolved in **FRAME numbers, not row offsets**.

`window_bounds` implements this, and both `gap_aware_moving_average` and
`hampel_flags` use it. The window of a point at frame `f` is the set of rows
whose frame lies in `[f - half, f + half]`. Because frames are sorted within a
track, that set is still a contiguous row range — but its size varies with the
local frame gaps, which is exactly the required behaviour.

**A frame gap is never treated as contiguous time.** Two rows that are adjacent
in the file but separated by a gap in frame number are not neighbours.

The same discipline is applied independently elsewhere: `covariance_sigma`
accepts only triples of genuinely successive frames, and `pooled_msd` and
`bootstrap_alpha` lay each track onto a dense frame-indexed array with `NaN` in
the gaps, so a displacement is counted only when both of its endpoints are
present.

## One window per file, derived from tracks pooled

The MSD is **pooled across all tracks in a file** (`pooled_msd`), fitted once
(`fit_anomalous`), and yields **one** sigma, one Gamma, one alpha, and therefore
**one smoothing window and one Hampel window per file**.

**The rationale matters more than the fact, so record it here rather than
rediscovering it later:**

Smoothing attenuates measured speed, and a wider window attenuates it more. If
each track received its own window, each cell's speed would be attenuated by a
different and unknown amount. Measured differences between cells would then
partly reflect differences in **how hard each cell was smoothed** rather than
differences in how the cells actually moved — and that contamination is
invisible in the output, because every value still looks like a speed.

**Uniform treatment within a file is what makes cell-to-cell comparison valid.**

**This is a design principle that holds on any dataset. It is NOT an
accommodation to the current one.** It would remain correct on data where
per-track estimation was statistically comfortable.

### If per-track estimation ever becomes viable

If a future dataset supports per-track estimation, switching to it is an
**explicit human decision**, recorded as such.

**The tool must never switch estimation mode on its own based on a detector.**
Two runs in different estimation modes are incomparable, and the incomparability
is undetectable after the fact: both runs emit the same columns, the same stamp
format and the same plausible numbers. An automatic mode switch would make the
comparability of any two outputs depend on a threshold nobody looked at.

## Outliers are removed, never imputed

Flagged points are set to `NaN` and **removed**. They are never interpolated,
forward-filled or imputed, and there is no code path that does so.

`gap_aware_moving_average` refuses to produce a value at a point whose own Z is
missing — computing one there would be imputation. Rejected and missing points
are written to the CSV as **empty cells**.

## Z_raw and the original Z column

`Z_raw` is always present in the output, and the original `Z` column is **never
overwritten**. The output frame is built from `mf.raw_text`, the input read as
verbatim strings, and `Z` is never assigned to.

**Recorded accurately:** `Z_raw` **duplicates the untouched `Z` column** rather
than preserving something that would otherwise be lost. Both columns hold the
same original values. It is redundancy, not rescue. Do not describe it as
preserving data that smoothing would have destroyed — smoothing writes to
`Z_smoothed`, a separate column.

## Output CSV provenance columns

Every output CSV carries `run_stamp` and `derivation_note`.

`derivation_note` is a **semicolon-joined, severity-ordered list of caveat
codes**, built by `build_derivation_note` and ordered by `NOTE_SEVERITY_ORDER`.
Codes absent from that ranking sort after it alphabetically, so a check added
later still reaches the CSV rather than being silently dropped.

The note is driven entirely by which checks fired, never by method name, so on
another dataset it follows whatever that data turns out to warrant.

## The derivation stamp's blind spots

`derivation_stamp` hashes the derivation version, the CLI arguments the
derivation reads, and most declared constants. It **records HOW a file was
produced, not WHAT it was produced FROM.**

**Three specific blind spots. All three are load-bearing:**

1. **The input data is not hashed.** Two runs on completely different input data
   with identical arguments produce an **identical stamp**. A `run_stamp`
   answers "was this made by the current derivation?" and cannot answer "was
   this made from the current data?". The input paths are recorded in the report
   only.

2. **`--lattice-reference` is not in the stamp.** But it changes whether
   `Z_STEP_UNVERIFIED` fires, and that code is run-level, so it reaches every
   file's note. **Two CSVs can therefore share a `run_stamp` and carry different
   `derivation_note` values.**

3. **The RNG seeds are not in the stamp.** Editing `ALPHA_BOOTSTRAP_SEED` or
   `TRANSFER_PROBE_SEED` in the source would change the reported confidence
   interval **without changing the stamp**, so the change would be invisible to
   anyone comparing stamps.

**Any future cross-dataset feature must handle these rather than assume them
away.** A feature that derives one window and applies it across several
datasets — which has been discussed — cannot use the stamp to tell those
datasets apart, because every dataset in the group would carry the same one.
Widening the stamp, or adding a second identifier alongside it, is a decision to
be made at that point and not assumed.

## Determinism

There are **exactly two stochastic sites** in the tool:

- `bootstrap_alpha` — the track-level bootstrap producing the alpha interval and
  the window interval
- `measure_transfer_exponents` — the synthetic noise and fBm probe, report-only

Both use **seeded `np.random.default_rng` instances**, not legacy global
`np.random.seed` state, so neither perturbs the other and neither is affected by
any global state. `np.random.seed` does not appear in the source.

**Runs are byte-reproducible on a fixed environment.** Two runs with identical
arguments produce identical output CSVs and a report differing only in the
output path.

**The seeds are hardcoded and not CLI-exposed.** They cannot be varied without
editing the source, so the reported interval cannot be re-drawn under a
different seed from the command line. Combined with blind spot 3 above, a seed
edit is both unexposed and unstamped.

Reproducibility here means repeat runs on a fixed environment. It is not a claim
about other platforms, interpreters or numpy versions.

## Warnings

**Warnings must be actionable, and must never be downgraded, made conditional or
suppressed.** A warning that fires on the current data is not noise to be tuned
out; it is the tool doing its job. If a warning is wrong, fix what makes it
wrong — do not raise its threshold until it stops firing.

**`WINDOW_NOT_DETERMINED` routing is PER-METHOD, not run-wide.** It reaches a
given method's CSV only because its warning text begins with that method's
filename and `build_derivation_note` matches on that prefix. Only the three
`Z_STEP_*` codes in `RUN_LEVEL_WARNING_CODES` are genuinely run-wide.

That it currently reaches every output CSV is a **Part B observation, not a
structural guarantee**. On data where one method's bootstrap were tight, that
method's CSV would correctly carry no such note.

## The constants, and where they come from

Write this section carefully; it is the one most likely to be paraphrased into
something false.

**The accurate position:** every **temporal window** is derived from a quantity
measured in the data. But the **ratios, tolerances and thresholds that convert
those measurements into windows are hardcoded constants.**

Do not restate this as "every parameter that affects the result is derived from
the data". That is the over-broad version and it is false. The module docstring
states a narrower version — that the Hampel threshold is the only hardcoded
statistical constant — which is also too narrow, since the noise margin `k` and
the Stage 2 MAD threshold are both hardcoded statistical constants and both
change the result.

The constants fall into three groups.

### Group 1 — scale-free, adapting to whatever data they are given

- `DEFAULT_NOISE_MARGIN_FACTOR` — `k`, the noise margin (CLI-overridable)
- `STAGE2_MAD_THRESHOLD` — the Stage 2 pass, in MAD units
- `STAGE2_WINDOW_TRACK_FRACTION` — the Stage 2 window as a fraction of the
  **measured** median track length

These are dimensionless. None encodes a Z step, a frame rate or a motion
magnitude, and each scales with the data it is applied to. They are described in
the source as fixed by convention rather than tuned.

**Verified:** that they are dimensionless and adapt. **Not verified:** that they
were never tuned on data. The repository records no provenance for them, so
"fixed by convention, not tuned" is the source's characterisation, not an
established fact.

`k` is the largest single lever on the smoothing window: the window scales as
`k^(2/alpha)`, and the report says so wherever the window appears.

### Group 2 — chosen, with no justification recorded in the repository

- `SIGMA_STABILITY_TOL`
- `SIGMA_STABILITY_MIN_RUN`

These two set the sigma-stability plateau detector, which caps the MSD fit range
and therefore determines sigma, Gamma and alpha. They are **responsible for at
least one method failing derivation outright** on the current data.

**Whether they were chosen before or after seeing results is NOT established
anywhere in this repository.** Say exactly that. Do not imply they were
principled, and do not imply they were fitted — neither is known. The README
argues for the stability rule on the grounds that it produces agreement with the
independent covariance estimator, which is an argument made after results
existed; that is a reason to be careful about the claim, not evidence either
way.

**A sensitivity sweep on these two is planned and has not been run.**

### Group 3 — absolute counts, which do not scale with dataset size

- `MIN_TRACKS_FOR_MSD`
- `MIN_PAIRS_AT_MAX_FIT_LAG`
- `MSD_MIN_FIT_LAGS`
- `ALPHA_SEARCH_MIN` and `ALPHA_SEARCH_MAX` (the alpha search grid bounds)

Unlike Groups 1 and 2 these are counts, not ratios. They mean the same thing on
a 70-track dataset and a 7000-track one, which is a limitation to be aware of
rather than a defect to fix unasked.

### The report's "Declared constants" block is not exhaustive

The block is headed "Declared constants (all of them scale-free ratios or
tolerances)" and **reads as a complete list. It is not.**

Constants absent from it, per the Phase A audit `001`:

`SIGMA_STABILITY_TOL`, `SIGMA_STABILITY_MIN_RUN`, `ALPHA_SEARCH_*`,
`ALPHA_WARN_DEVIATION`, `SIGMA_ESTIMATOR_DISAGREE_RATIO`,
`ALPHA_CORRECTION_WARN_RATIO`, `MSD_MIN_FIT_LAGS`, `ALPHA_BOOTSTRAP_*`,
`TRANSFER_PROBE_*`, `SENSITIVITY_MAX_WINDOW`, `SENSITIVITY_MIN_MAX_WINDOW`.

**That list is taken from `001` and `001` did not establish it as complete.** It
is a list of omissions found, not a full audit of omissions. Treat it as a lower
bound.

## Where files are not independent

**Correction to a common shorthand:** it is often said that the cross-method
consensus check is the one place where input files are not independent. That is
not accurate. Stage 1 is the only **stage** where files interact, and it
contains **three** such places:

1. **Stage 1a, `stage1_consistency`** — checks that every file has identical
   `Track_ID`, `Frame`, `X` and `Y` as the first file. On a mismatch it raises
   `FatalDataError` and **the entire run stops**. One file's content can prevent
   every other file being processed.

2. **Stage 1b, `stage1_zstep`** — verifies `--z-step` against the lattice
   spacing of the single file named by `--lattice-reference`. The resulting
   `Z_STEP_*` codes are run-level and reach **every** file's `derivation_note`.

3. **Stage 1c, `stage1_cross_method`** — compares each file's raw Z against the
   median of the other files and flags disagreement.

Stage 1c is the only one of the three that produces a **per-method usability
verdict**, and it is the one the shorthand is reaching for.

**What Stage 1c does and does not alter:** it changes **no smoothed value**. It
adds a `DO_NOT_USE:flagged-inconsistent` code to the flagged method's
`derivation_note`, prints a banner, sets the parameter block `STATUS`, and
excludes the method from the cross-method agreement comparison. So it does alter
CSV *content* — just not any computed value.

It is a **method-selection diagnostic, not part of smoothing**, and is a
**candidate for extraction into a separate script**. Recorded here as present,
diagnostic only, and pending extraction.

## Flagged and failed are two different mechanisms

**Never conflate these.**

| | Flagged by the consensus check | Failed derivation |
| --- | --- | --- |
| Mechanism | Stage 1c disagreement with the other files | Stage 3 could not derive a parameter |
| CSV written | **Yes** | **No** |
| Marking | do-not-use banner in the report, `DO_NOT_USE:flagged-inconsistent` in `derivation_note`, `STATUS` records it | No output exists to mark; recorded under METHOD FAILURES |
| Warnings raised | Yes | Possibly none at all, if it fails before the checks run |

A flagged method is **reported in full and left to the reader to reject**. A
failed method **produces nothing**, and that is the correct outcome rather than
something to work around.

Both outcomes currently occur on the test data, for two different methods, for
two unrelated reasons. Treating them as one category loses the distinction that
matters.

## The tool recommends no sampling method

**There is no recommendation logic in the source.** No method is preferred,
ranked or selected by the code.

The README's position is: use a method that is **consistent with the
cross-method consensus**. The report's `CROSS-METHOD AGREEMENT` section lists
exactly those and excludes the rest with reasons. More than one method is
typically eligible.

Do not write "the recommended method is X" into any document, report or commit
message. It is not a thing the tool produces.

## The README as a source

The README contains **result numbers throughout its explanatory sections**,
where they function as **evidence for past decisions** rather than as current
values to use. That is a legitimate role for them.

**At least one such block is known to be stale** — it quotes pre-`1/alpha`-
correction (derivation-3) figures that the current derivation does not
reproduce. It is annotated in place as of task 002. Others have not been
exhaustively checked.

The README's own `State at handover` section deliberately contains no numbers
and states why: numbers copied into prose go stale silently, and this project
has already lost a round to a value mis-copied between two methods.

**The parameters report the tool writes on every run is the only authority for
current values.**

---

# PART B — DATASET OBSERVATIONS

> **Everything below is true of the current test data only.**
>
> None of it is a property of the tool. None of it may be hardcoded, assumed,
> defaulted to, or preserved as a behaviour. If the data changes, all of it may
> change, and the tool is correct to produce different answers.

**These are recorded as SHAPES, NOT NUMBERS**, deliberately, following the
README's `State at handover` section and for the same reason it gives.

**Every figure lives in the parameters report, which the tool writes on every
run:**

```
python zsmooth.py data/*.csv --out out --z-step <YOUR STEP> --lattice-reference <YOUR SINGLE-PIXEL FILE>
```

Then open `out/zsmooth_parameters_report.txt` and find the `PARAMETER BLOCK` for
the method in question. It is fixed-width and meant to be quoted verbatim. Read
in particular: `W_smooth derived / in use`, `W_smooth 95% CI`,
`W_hampel derived / in use`, `sigma (fitted)` and `sigma (covariance)`,
`alpha (Stage-2 cleaned)`, `outliers`, `warnings`, and `z-step verification`.

## The smoothing window is not determined by this data

**Every method that produced output raises `WINDOW_NOT_DETERMINED`.** The
bootstrap interval on the window spans many odd values on every one of them —
not one or two neighbouring windows, but a wide range.

**This is a correct result, not a defect.** The point estimate is reported and
used, and it is more precise than the data warrants.

> **THIS MUST NOT BE SOFTENED.**
>
> Not in a report, not in a summary, not in a commit message, not in a figure
> caption. Do not write "the window is 7". Do not present the point estimate
> without its interval. Do not describe the interval as "reassuringly narrow" or
> the estimate as "well constrained". Anything downstream that is sensitive at
> the level of the interval must be evaluated **across** the interval, not at
> the point.

## The interval understates the total uncertainty

The reported interval is **conditional on the fit range**, which
`bootstrap_alpha` holds fixed at the range chosen for the point estimate.

The separate dependence on where the fit stops is reported by the fit-range
sensitivity table and is **not folded in**. So the true uncertainty on the
window is **wider than the reported interval**, not narrower.

## Values differ per method; there is no dataset-wide value

There is **no single dataset-wide window, sigma or alpha**. Each input file
yields its own, and they differ — including between methods that agree well
enough to pass the consensus check.

**Quoting one method's interval as though it were the dataset's is a mistake
that has already been made once in this project.** Always name the method
alongside the value.

## One method fails, a different method is flagged

On the current data, **one method fails derivation outright and produces no
output**, and a **different** method is **flagged by the consensus check and
does produce output** (carrying its do-not-use marking).

These are the two distinct mechanisms described in Part A, occurring
simultaneously for unrelated reasons. They are not two symptoms of one problem
and must not be summarised as "the radius methods are unusable".

## The effect of Stage 2 cleaning on alpha is unmeasured

`alpha (no rejection)` is **NOT AVAILABLE for any method** on this data — for
some because the anomalous model does not converge on the uncleaned MSD at any
fit range, for others because the uncleaned MSD has no stable sigma plateau of
its own.

The tool deliberately reports this as unavailable rather than forcing the fit
over a range where it is not conditioned. The consequence is that **the size of
the Stage 2 artifact on alpha is currently unknown for every method**, even
though Stage 2 cleaning is one of the three named dependencies of the window.

## Per-track motion parameters are not estimable on this data

Fitting the tool's own model **per track** instead of pooled does not work on
this data.

On every method checked, roughly **half the tracks produce no converged fit at
all**; of those that do fit, a **small number return a negative Gamma**, which
is **physically impossible** and therefore evidence of estimation error rather
than of genuine heterogeneity between cells; and a further group return a
**non-positive noise intercept**, meaning sigma is unresolvable for that track.
Fitted per-track alpha spans **nearly the entire search grid, including its
bounds** — the signature of a fit that is not identified.

This is **not** the justification for pooling — Part A gives that, and it holds
regardless. It is the answer to "could we do per-track here anyway?", and the
answer is no.

**Scope:** measured under the tool's own model and its pooled fit range applied
per track, on Stage-2-cleaned data. A different per-track procedure was not
tried. Numbers are in `prompt_outputs/002-zsmooth-governance-phaseB.md`.

## Pooling weights tracks by their pair count

The pooled MSD sums squared displacements across tracks and divides by the total
pair count, so **a track contributes in proportion to how many displacement
pairs it has.** Long tracks dominate the fit.

Track lengths here vary by roughly a **factor of six**.

**Whether long and short tracks differ systematically is UNTESTED.** If they do,
the pooled estimate is weighted toward whatever the long tracks are doing, and
nothing currently detects that.

**A heterogeneity detector is planned and has not been built.** Until it exists,
this is an open question, not a resolved one.

## No parameter may be selected by reproducing an expected result

**No parameter may ever be chosen by checking which value reproduces an expected
result** — not the window, not `k`, not the stability tolerances, not the fit
range.

This is stated in Part B rather than Part A because the temptation is specific
and concrete: this dataset has a known expected behaviour, and several
parameters can be moved to reach almost any window and therefore almost any
downstream speed. The report says as much about `k` explicitly.

If a parameter is changed, the justification must be independent of what the
change does to the result.
