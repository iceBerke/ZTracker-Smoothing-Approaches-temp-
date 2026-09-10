# zsmooth

Post-processing for Z-coordinate trajectories exported by the ZTracker_Fiji
Tool 3 (TopoJ) plugin. It rejects transient outliers and then smooths Z(t), so
that speeds derived downstream are not dominated by measurement noise or
single-frame artifacts.

This is a standalone tool. It does not read from, write to, or depend on the
ZTracker_Fiji Maven project.

## Install and run

```
pip install -r requirements.txt

python zsmooth.py data/*.csv --out out --z-step 2.0 \
    --lattice-reference single_pixel_results_table.csv

python zsmooth.py data/single_pixel_results_table.csv -o out --z-step 2.0 \
    --lattice-reference single_pixel_results_table.csv --frame-interval 0.5
```

Pass `--lattice-reference` whenever a single-pixel file is among the inputs. It is
the only thing that can verify `--z-step`. Without it the run still works, but the
Z step is unverified and the report says so — see "The Z-step cross-check" below.

From VS Code, run the file directly with arguments, or use a `launch.json`
configuration whose `args` list mirrors the command line above.

Outputs, all written into `--out`:

* `<input-stem>_smoothed.csv`, one per input file that processed successfully
* `zsmooth_parameters_report.txt`, a single plain-text report covering the whole run
* `<input-stem>_diagnostics.png`, one per input file, only with `--plot`

Everything the tool prints to the terminal also goes into the report file. The
report is intended to be sufficient on its own: the command line, the supplied
parameters, every measured quantity, every parameter derived from it, and every
warning are all recorded there.

## CLI

| Argument | Required | Meaning |
| --- | --- | --- |
| `CSV [CSV ...]` | yes | One or more input CSVs, one per sampling method. |
| `-o`, `--out DIR` | yes | Output directory; created if absent. |
| `--z-step MICROMETRES` | **yes** | The Z step. Used as the Hampel MAD floor and cross-checked against the data. |
| `--lattice-reference CSV` | no | Which input file was produced by single-pixel sampling. The only file that can verify `--z-step`. |
| `--frame-interval SECONDS` | no | Report-only. Adds micrometres-per-second speeds alongside the per-frame ones. |
| `--mad-threshold MAD` | no | Stage 4 Hampel threshold in MAD units. Default 4.0. |
| `--noise-margin K` | no | Stage 3d noise-margin factor *k*. Default 2.0. |
| `--plot` | no | Write a per-method diagnostic PNG. Requires matplotlib. |
| `--hampel-window FRAMES` | no | Override the derived Stage 4 Hampel window. Odd, >= 3. |
| `--smooth-window FRAMES` | no | Override the derived smoothing window. Odd, >= 1. |

When either window is overridden, the report records both the derived value and
the override that replaced it. The same applies to `--noise-margin`: the report
records the value in use and the default alongside it, whether or not it was
overridden.

`--plot` is the only feature with an extra dependency. Without matplotlib
installed the tool runs exactly as it always does; `--plot` then fails
immediately, before any work is done, with a message telling you what to
install. Nothing else in the run is affected.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | All methods processed. |
| 2 | The run stopped: bad arguments, unusable inputs, or a failed derivation. |
| 3 | At least one method failed. Any remaining methods processed and were written. This includes the case where every method failed, since the failure is per-method rather than a stopped run. |

## Input format

CSV with the header `Track_ID,Frame,X,Y,Z`. One file per sampling method, all
describing the same tracks at the same frames. Frames within a track may be
non-contiguous; gaps are expected and are handled throughout. `Z` may be blank
or non-numeric, in which case those rows are carried through untouched with
`Z_smoothed` empty and are excluded from every statistic.

## Output format

Every original column is reproduced **verbatim from the input text**, in the
original row order. Nothing is overwritten. Three columns are appended:

| Column | Meaning |
| --- | --- |
| `Z_raw` | The original Z value, unmodified. |
| `Z_smoothed` | The result. Empty where undefined. |
| `outlier_flag` | `True` if the point was rejected in Stage 4. |
| `run_stamp` | Derivation stamp of the run that wrote the file — how it was produced, **not** what from. Constant down the file. |
| `derivation_note` | Semicolon-joined list of every check that fired for this method, most serious first. Empty if none did. Constant down the file. |

`derivation_note` is driven by the checks themselves, never by method name, so on
another dataset it follows whatever the data warrants. Entries are ordered by what
they cost a reader who acts on the file: **output that should not be used at all**
(`DO_NOT_USE:flagged-inconsistent`), then **anything that scales every value in it**
(`Z_STEP_MISMATCH`, `Z_STEP_UNVERIFIED`, `Z_STEP_REFERENCE_NOT_LATTICE`), then
**caveats on the derived numbers** (`WINDOW_NOT_DETERMINED` first, as the single most
important one attached to these files), then **data-quality notes**. Codes absent
from the ranking sort after it alphabetically, so a check added later still reaches
the CSV. Warnings about the run as a whole reach every file; the rest reach only the
method they were raised for. The full ranking is `NOTE_SEVERITY_ORDER` in the
source.

**The column set changed.** `run_stamp` and `derivation_note` were added at
derivation-4. **A `_smoothed.csv` without these two columns predates that change**
and was produced by an earlier derivation — regenerate it rather than comparing it
with current output.

Both are constant down the file, which is redundant per row and deliberate: a
reader who opens the CSV and never sees the report is exactly the person who needs
to know that the method was flagged as unusable, and that warning has to survive
being filtered, sorted or sliced. A reader that asserts an exact column count will
break on these; that was accepted, on the grounds that a downstream tool failing
loudly is better than one silently consuming a flagged method's output.

`Z_smoothed` is empty at any row whose own Z was blank, and at any row that was
rejected. Rejected points are **removed**, not interpolated, forward-filled or
imputed; producing a smoothed value at a rejected point would be imputation, so
the tool does not do it.

## Design rule: dataset independence

The tool is meant to be run on other datasets with different Z step sizes, frame
rates and motion characteristics. Accordingly:

* The only hardcoded **statistical** constant is the Hampel threshold in MAD
  units (default 4.0, overridable). It is scale-free by construction.
* The Z step is supplied by the user and cross-checked against the data. It is
  never inferred as the source of truth and never assumed.
* The Hampel window is derived from the measured motion timescale.
* The smoothing window is derived from the measured noise and confinement
  timescale.
* All analysis is in **frame units**. No derived quantity depends on the frame
  interval in seconds. `--frame-interval`, when supplied, only adds a second set
  of speed figures to the report.
* When a derivation fails, the tool says so and stops. It never falls back to a
  hardcoded value.

Everything that remains hardcoded is a scale-free ratio or tolerance (for
example "the MSD fit range extends while the relative residual stays below
10%"). Each of these is printed in full at the top of every report under
"Declared constants", so a reader always sees the complete set of choices the
run was made under.

## Processing stages

### Stage 1 — Diagnose

1. **Cross-file consistency.** `Track_ID`, `Frame`, `X` and `Y` must be
   identical, row for row, across all input files. If not, the run stops.
2. **Z-step cross-check.** See the dedicated section below.
3. **Pairwise cross-method comparison and consensus check.** See below.
4. **Per-file description.** Row count, track count, NaN count, Z range, track
   length and span distributions, and frame-gap statistics.

### Stage 2 — Strict first pass

A deliberately conservative, gap-aware Hampel pass whose only job is to keep
gross outliers out of the Stage 3 fit. Threshold 5.0 MAD; MAD floored at
`--z-step`; window set to a quarter of the **measured** median track length,
rounded up to odd. This pass is provisional and its output is discarded — it is
never the final result.

### Stage 3 — Measure the timescale

The mean squared displacement of Z is computed against frame lag, per file,
pooled across tracks, using only pairs where both endpoints are present.

`MSD(tau) = 2*sigma^2 + Gamma * tau^alpha` is fitted over the initial rising
portion — an **anomalous-diffusion** model in which the exponent `alpha` is
fitted, not assumed. The smoothing and Hampel windows follow from the fitted
`sigma`, `Gamma` and `alpha`.

The earlier version of this tool assumed `alpha = 1` (normal diffusion). The
linear model is **not** retained as a fallback or an option; it is computed only
to populate the comparison column of the fit-range sensitivity table, and nothing
is derived from it.

### The data is not subdiffusive — that was a fitting artifact

This was believed for a while and is worth recording, because the belief was
produced by the tool itself.

When the fit range was allowed to extend over the whole usable lag range, `alpha`
came out between 0.06 and 0.53 for every method, and the tool reported strong
subdiffusion. It was not there. `alpha` measured over the range where `sigma` is
actually identifiable is close to 1:

```
four_neighbor_median, alpha by fit range
  1..5  1.145      1..9   0.990
  1..6  1.075      1..10  0.840
  1..7  1.095      1..13  0.490   <- sigma already unidentifiable (intercept <= 0)
  1..8  1.120      1..37  0.500   <- sigma already unidentifiable
```

The exponent only collapses at exactly the ranges where the intercept has already
gone negative. The two failures are the same failure: a flexible power law fitted
too far absorbs the short-lag structure into its exponent, taking the noise floor
with it. **Three of the four surviving methods now fit `alpha` between 1.06 and
1.18 — consistent with normal diffusion.**

The anomalous model was still the correct change. Fitting `alpha` rather than
assuming it is what made the artifact visible at all: under the linear model the
same over-extended range simply inflated the intercept and nothing looked wrong.
But what it revealed was **a fitting problem, not anomalous physics**.

Because the model has three free parameters it is not identifiable from three
points, so the fit range starts at five lags.

For any fixed `alpha` the model is linear in `2*sigma^2` and `Gamma`, so the fit
is exact least squares at each `alpha` and only `alpha` is searched — on a dense
grid over [0.05, 2.0], evaluated in one vectorised pass. There is no starting
point, no convergence criterion and no local minimum to fall into. If the best
`alpha` lands on a search bound, the fit is treated as **not converged** and the
method fails rather than returning a value that is an artifact of the bound.

### Stage 4 — Reject and smooth

The Hampel filter is re-run with the Stage 3 window and the user threshold.
Flagged points are set to NaN and removed. The surviving points are smoothed
with a gap-aware centred moving average at the Stage 3 smoothing window.

Both operations are **gap-aware**: a point's window contains only those points
whose *frame number* lies within the window's span of that point's own frame
number. Neighbouring rows separated by a frame gap are excluded, so a gap is
never silently treated as contiguous time. On the current dataset this changes
the window contents for roughly a quarter of all points.

## Derived parameters — what they mean

All are reported per file, next to the measured quantities they came from.

**`sigma`, the localisation noise.** From the MSD intercept: `2*sigma^2` is the
value MSD extrapolates to at zero lag. Two measurements of a stationary object
differ by `sqrt(2)*sigma`, so a non-zero intercept is the part of the
frame-to-frame scatter that is measurement, not movement. Units are Z units.

**`Gamma`, the transport coefficient.** The scale of the motion term, in Z units
squared per frame^alpha. With `alpha != 1` it is not a diffusion constant and its
units depend on `alpha`, so it is not comparable across methods with different
exponents.

**`sigma_cov`, the model-free localisation noise.** A cross-check on `sigma` that
depends on no model at all. Two successive displacements share an endpoint, so
independent localisation noise on that shared point enters one displacement
positively and the other negatively:

```
Cov(delta_i, delta_i+1) = -sigma^2
```

provided the genuine motion increments are uncorrelated. No MSD model, no power
law, no fit range. It is computed gap-aware — only triples of frames
`(f, f+1, f+2)` all present and finite — so a displacement never spans a gap and
"successive" means genuinely successive.

The report prints it beside the fitted `sigma`, along with the **noise share of
`MSD(1)`**, `2*sigma_cov^2 / MSD(1)`. That percentage is the quantitative
justification for smoothing at all: it is how much of the frame-to-frame
variation is measurement rather than movement. On the current dataset it runs
from 52% to 71% depending on method.

`sigma_cov` is a **cross-check only**. It is not used in the window derivation,
and the report says so wherever it appears. `SIGMA_ESTIMATORS_DISAGREE` fires
when the two estimates differ by more than a factor of **1.5**, or when the
fitted `sigma` is unresolvable while `sigma_cov` is not.

**`alpha`, the anomalous exponent.** How the motion accumulates with lag.
`alpha = 1` is normal diffusion; **below 1 is subdiffusive** (displacement
accumulates more slowly than a random walk — confinement, crowding, or a
measurement that suppresses short-lag motion); **above 1 is superdiffusive or
directed**. It is reported with every fit.

`alpha` is measured on **Stage-2-cleaned** data and is therefore partly an
artifact of that pass: the strict Hampel filter removes large single-frame
excursions, which suppresses short-lag MSD and changes the apparent exponent. The
report prints `alpha` both with and without rejection so the size of that artifact
is visible. Neither value is "the" exponent of the underlying motion.

The uncleaned `alpha` is fitted over **its own** stability plateau, not over the
cleaned data's fit range, and the two ranges are both printed because they
generally differ. Forcing the raw fit onto the cleaned range would fit it where it
is not conditioned — reintroducing exactly the over-extended-range misspecification
the stability cap exists to remove. Where the raw MSD has no plateau of its own,
the report says `NOT AVAILABLE` **with the reason**, and the size of the Stage 2
artifact is simply unknown for that method. It is never manufactured.

**Single-frame motion scale, `sqrt(Gamma)`.** How far the object genuinely moves
in one frame — the motion term at `tau = 1` is `Gamma * 1^alpha = Gamma`. This is
the scale that smoothing must not erase, taken from the fitted model rather than
from any linear substitute.

**Fit range.** Always starting at lag 1 — the model's intercept *is* the noise
term. Two independent criteria bound how far it extends, and the smaller wins.
Both are printed with the chosen range.

*1. Model adequacy.* Extend while the RMS fit residual stays within 10% of the
mean MSD over the range.

*2. `sigma` identifiability.* `sigma` is the **zero-lag intercept**, so only short
lags carry information about it. Fitted over a long range, a flexible power law
absorbs the short-lag structure into its exponent and the intercept slides toward
zero and then goes negative — `sigma` becomes unidentifiable. **Tracking the whole
curve is not the objective; resolving the noise floor is.** The cap is therefore
the end of the **plateau** over which the fitted `sigma` is stable: the first run
of at least 3 consecutive fit ranges whose `sigma` values agree to within 10%. No
lag count is hardcoded — the plateau is wherever the data puts it. The run need
not begin at the shortest admissible range, because the very shortest fits can be
erratic; the first run long enough to count is taken, since the earliest plateau
is the one least contaminated by long-lag structure.

If no such plateau exists, the method **fails**. The tool does not fall back to
the largest positive-intercept range or to any other rule.

**Why stability rather than intercept positivity.** Capping at the last range
before the intercept goes negative sounds equivalent and is not: by that point the
intercept is already collapsing. On `four_neighbor_median` that rule returns
`sigma = 1.76`, which is 56% below the independent model-free estimate of 3.97.
The stability plateau returns 4.40, within 11% of it. **The stability cap was
chosen because it produces agreement with an estimator that shares none of its
assumptions, and that agreement is the justification for the rule.** The report
prints both `sigma` values side by side so the agreement can be checked on every
run.

The full fit-range table is still printed as sensitivity information — capping the
range does not hide the dependence.

**Confinement lag.** The lag at which the MSD ceases to rise: the first lag `L`
such that no later usable lag exceeds `MSD(L)` by more than 5%. The claim is
only made when it can be sustained over at least a quarter of the usable lag
range, so that a few noisy points at the end of the curve are not read as a
plateau. If the MSD is still rising at the end of the range, the confinement
timescale is **unbounded by this data** and no upper cap on the smoothing window
can be derived — the tool says so rather than inventing a cap.

**Smoothing window.** Averaging `W` points reduces the noise contribution to a
difference of two smoothed values to `sigma*sqrt(2)/sqrt(W)`. The window is the
smallest odd `W` for which that falls below the single-frame motion scale by the
noise-margin factor `k` — that is, `W >= 2 * k^2 * sigma^2 / Gamma`. It is then
capped at half the confinement lag, when one exists, so that smoothing cannot
span the timescale on which the motion itself changes character.

### The smoothing window is not a measured quantity

It depends on **three** arbitrary choices, and the report states all three where
the window is reported:

1. **`k`, the noise margin.** The window scales as `k^2`. See the warning below.
2. **The MSD fit range.** The report fits both models over a spread of ranges and
   prints the resulting windows side by side, with **two** max/min spreads:
   * the **live** spread, over the ranges *inside* the stability cap — the ranges
     the tool could actually have chosen. This is the dependence that remains.
   * the **counterfactual** spread, over all ranges up to the usable maximum —
     what would happen *without* the cap. It is labelled as such and is not live
     instability; the cap removes it.

   The verdict on whether the model reduced the sensitivity is judged on the live
   spread. If it did not, the report says so.
3. **The Stage 2 cleaning parameters.** `sigma`, `Gamma` and `alpha` are all
   measured on Stage-2-cleaned data. `alpha` alone can move substantially between
   the cleaned and uncleaned MSD, and both values are printed.

The anomalous model addresses (2) only, and on this dataset it does not fully
resolve it. Read the reported window as one point in that space, not as a
measurement.

`k` defaults to 2, meaning residual noise is held to at most half the
single-frame motion, and is set with `--noise-margin`. Because the window scales
as `k^2`, small changes matter: `k = 1` accepts residual noise equal to the
motion scale and gives a much narrower window, `k = 4` demands a window sixteen
times wider. Raising `k` is the wrong way to get more smoothing if the window it
produces exceeds the track length — see the degenerate-window failure below.

**Do not select `k` by checking which value reproduces an expected result.**
Because the window scales as `k^2` and `k` is bounded by nothing in the data,
almost any window — and therefore almost any downstream speed — can be reached by
adjusting it; a `k` chosen that way encodes the answer you were looking for
rather than anything the measurement said. When the MSD does not flatten, `k` is
the *only* thing setting the window, and the report says so explicitly in that
method's section. Judge the window against the sensitivity table, not against
whether the result comes out where you expected.

A derived window at or above the median track span is refused outright. See
"When a method fails".

**Hampel window.** From the same timescale. The crossover lag
`tau* = (2*sigma^2/Gamma)^(1/alpha)` is where genuine motion overtakes
localisation noise. With `alpha < 1` the motion accumulates more slowly, so
`tau*` is longer than a linear model would imply. Points closer together in time
than `tau*` are statistically indistinguishable,
so they are the legitimate local neighbourhood for a median and MAD. The window
is the smallest odd `W >= 2*tau* + 1`. A window below 3 points cannot form a
median and MAD at all, so it is raised to 3 and the raise is reported
explicitly.

**Sensitivity table.** Mean `|dZ|` per frame across a range of smoothing
windows, with and without outlier rejection. It is printed for every file
regardless of which window was chosen, because it is the evidence the choice
rests on. Read it as a curve: the window that was chosen should sit where the
steep initial fall has flattened. If the curve is still falling steeply at the
chosen window, more smoothing is still removing noise; if it fell to near zero
well before, the chosen window is erasing signal.

## The Z-step cross-check, and why it exists

A wrong Z step shifts every value in the output while leaving the file looking
entirely normal — correct row count, plausible-looking numbers, no error
anywhere. **This has happened before on this data and was not detected.** The
cross-check exists to make that failure visible.

The tool therefore detects, independently of anything the user said, the
smallest consistent spacing between distinct observed Z values in each file: the
smallest `g` such that at least 99% of the distinct Z values are integer
multiples of `g` **and** the resulting lattice slots are at least 5% occupied.
The occupancy test is what stops the file's decimal print precision (1e-4, say)
from being mistaken for a physical Z step in continuously valued data.

### Only one kind of file can answer the question

A method's output granularity is set by its sampling window:

* **Single-pixel** sampling returns a raw lattice value, so its granularity *is*
  the Z step.
* A **median** returns either a sampled value (odd window) or the mean of the two
  middle sampled values (even window). Both are multiples of half the step, so a
  median's granularity is at worst half the Z step and **never finer**,
  regardless of window size.
* A **mean of N** values has granularity of order step/N, becoming effectively
  continuous for large N.

The five-method dataset shows exactly this: `single_pixel` values are all exact
multiples of 2.0; both median files are all exact multiples of 1.0 and of nothing
coarser, despite being different median methods; `four_neighbor_mean` sits on
0.5; `radius_mean` is on no lattice at all.

It follows that **only a single-pixel file reveals the true Z step**. An
aggregate file bounds it from below and never identifies it, and the coarsest
granularity across files is not a safe proxy either — a set of inputs containing
no single-pixel file simply does not contain the answer.

That is why `--lattice-reference` exists, and why it must be given explicitly.
It is never inferred from filenames: a filename is a claim about provenance that
the tool cannot check, and the whole point of this check is to not take the
Z step on trust.

The argument accepts a bare filename when that is unambiguous. If two inputs in
different directories share a basename, the tool **refuses** rather than picking
one, names both candidate paths, and asks for a full path — naming the wrong file
would verify `--z-step` against the wrong lattice, which is the failure this
check exists to prevent. A full path is then resolved positionally against the
input list, so it identifies the intended file even when basenames collide.

### Two earlier versions of this check, both wrong

Recording these because both failures are instructive, and neither was visible
from the output at the time.

**Version 1** compared the detected minimum spacing directly against `--z-step`
for equality, across every file. Because every aggregate method is finer by
construction, it warned on four of the five files in normal operation. A check
that fires during normal operation trains the reader to ignore it, which defeats
the purpose of having it — the one run where it meant something would have looked
exactly like all the others.

**Version 2** tested whether `--z-step` was an integer multiple of the detected
spacing. That fixed the noise but broke the check: it **silently accepts a Z step
that is too large by a whole factor**. With a true lattice of 2.0, a supplied
`--z-step 4.0` reported "2 x detected [exact]" and raised nothing at all, while
every Z value downstream was double what it should be. A supplied 8.0 read as
"4 x detected [exact]", equally silently. That is precisely the error the check
exists to catch, so version 2 was worse than version 1: quiet and wrong rather
than noisy and useless.

### What the check does now

* The per-file granularity table is printed every run as **information**, never
  as a warning. Granularity is diagnostic of the sampling method, not a fault.
* If `--lattice-reference` names a file, that file's spacing is compared to
  `--z-step` for **equality**, to a relative tolerance of 1e-6. They must be
  equal, because a single-pixel file returns raw lattice values. A difference
  raises `Z_STEP_MISMATCH` naming both values.
* The named file is checked for plausibility first: single-pixel output must lie
  on one consistent lattice. If it does not, `Z_STEP_REFERENCE_NOT_LATTICE` says
  the file does not look like single-pixel output and the check is unavailable.
* If `--lattice-reference` is not given, **no check is performed and no proxy is
  substituted**. `Z_STEP_UNVERIFIED` says so.

When a warning fires the supplied value is still what gets used. **The
disagreement is reported, not resolved** — the tool has no way to know which
number is right, and quietly preferring either would recreate the failure this
check exists to catch.

### A median-granularity check was considered and dropped

Do not re-propose this. The reasoning is recorded here so it is not revisited.

The idea: since a median's granularity can never be finer than half the Z step,
a file known to be a median method whose granularity comes out finer than
`--z-step / 2` would indicate something wrong, and could be warned about.

**The arithmetic is correct.** A median returns either a sampled value or the
mean of the two middle sampled values, both of which are multiples of half the
step. This was verified over 20 000 synthetic tracks at window sizes 2, 4, 6, 8
and 12: not one value ever landed finer than half the step.

**It was dropped because the tool cannot know which inputs are medians.**

* Filenames cannot be trusted. A filename is a claim about provenance that the
  tool cannot check, and this is precisely the area where claims must not be
  taken on trust.
* The values cannot answer it either. A median over an even window and a mean of
  two values both land exactly on the half-step lattice and are indistinguishable
  from the numbers alone.
* Applying the check to every file would fire on any legitimate mean — the
  four-neighbour mean sits at a quarter of the step, entirely correctly — which
  is the false-positive problem that made version 1 of the Z-step check useless.

A `--median-method` declaration would work only if the declaration were right,
and a wrong declaration would produce a confident warning about nothing. That
trades a check the tool cannot perform for a new way to be misled.

The per-file granularity table already puts the same information in front of a
human reader, who does know which method produced which file. That is sufficient,
and it is where this belongs.

### Your responsibility

**When no single-pixel file is supplied as `--lattice-reference`, the Z step is
unverified and you carry that responsibility.** The tool will run, produce
complete output, and give you no independent reason to believe the value you
passed. Confirm it against the acquisition Z spacing yourself. Nothing in the
output will look wrong if it is wrong.

## The cross-method consensus check, and why it exists

A sampling method whose window straddles a height discontinuity produces
confidently wrong values — values that are internally consistent and carry no
sign of being wrong. Comparing methods against each other is how such a method
is caught.

Every pair of methods is compared, counting the points that differ by more than
1x, 5x and 25x the supplied Z step. Then, for each method, the fraction of rows
differing from the median of the **other** methods by more than 5x the Z step
becomes that method's consensus score, and a Hampel test across those scores
identifies any method that stands apart. The warning names the affected point
count.

The check needs at least three methods to form a consensus. With one or two
input files the tool says so and skips it.

## Warnings — how to interpret them

Every warning is printed where it arises and again in an "ALL WARNINGS RAISED"
block at the end of the report.

**`Z_STEP_MISMATCH`** — the file named by `--lattice-reference` has a lattice
spacing different from `--z-step`. Both values and the ratio are named. A
single-pixel file returns raw lattice values, so these two numbers must be equal.
One of them is wrong. Resolve it before using the output; every value in the
output is conditioned on the supplied value.

**`Z_STEP_UNVERIFIED`** — no `--lattice-reference` was given, so the Z step was
not checked against anything and no proxy was used. If a single-pixel file is
among your inputs, name it and re-run. If not, confirm the Z step against the
acquisition yourself.

**`Z_STEP_REFERENCE_NOT_LATTICE`** — the file named as the single-pixel reference
does not lie on one consistent lattice, which single-pixel output must. Either
the wrong file was named or it is not single-pixel output. The check is
unavailable until that is resolved.

**`METHOD_DISAGREES_WITH_CONSENSUS`** — one method disagrees with the others by
more than the spread among them. Investigate that method's sampling geometry
before trusting its output; a window straddling a height discontinuity is the
usual cause.

A flagged method's **derived windows are also unsound**, and the report says so
wherever they appear — a banner in that method's section and a marked `STATUS` in
its parameter block. The windows come from that method's `sigma`, `Gamma` and
`alpha`, so they inherit the inconsistency: they describe whatever the flagged
method measured, which the other methods contradict. The numbers are reported in
full and the derivation is unchanged — they are simply not a sound basis for
smoothing parameters. Resolve the disagreement, or take windows from a method that
is consistent with the consensus.

**`HIGH_OUTLIER_RATE`** — more than 5% of points were rejected. At that rate the
rejection is a symptom of a data-quality problem, not a filtering step.
Investigate the acquisition or the sampling method rather than raising the
threshold to make the number smaller.

**`CONFINEMENT_UNBOUNDED`** — the MSD does not flatten within the available lag
range, so no confinement timescale exists in this data and no upper cap on the
smoothing window could be derived. The window is then fixed entirely by `k`, a
chosen parameter, with only `sigma` and `D` coming from the data. The report
spells this out under "HOW THIS SMOOTHING WINDOW WAS SET" in that method's
section, with the windows `k/2` and `2k` would have produced. If the window comes
out large, nothing in the data contradicts it — but nothing in the data supports
it either. Consider longer tracks, or set `--smooth-window` yourself with the
sensitivity table as evidence.

**`HAMPEL_WINDOW_SPANS_TRACK`** — the Hampel window **actually in use** is at or
above the median track span, so over a typical track the median and MAD become
whole-track statistics and the filter loses its local character: it rejects
points that differ from the track as a whole rather than from their
neighbourhood. Unlike the smoothing-window case this degrades the filter rather
than collapsing it to a constant, so processing continues. Set
`--hampel-window` below the median track span if a local window is wanted.

The check is applied after override resolution, so an override that avoids the
problem suppresses the warning and an override that creates one raises it. If the
derived value would have triggered the warning but an override avoided it, the
report says so in one line without raising anything.

**`NOISE_DOMINATED`** — `sigma` exceeds 10% of the total observed Z range. The
measurement noise is a substantial fraction of everything the experiment
observed. Smoothed values remain the best available estimate, but derived speeds
should be treated as upper bounds.

**`NAN_Z_PRESENT`** — blank or non-numeric Z values are present. Those rows are
carried through with `Z_smoothed` empty and are excluded from every statistic.
Expected in some datasets; unexpected in others, so it is always stated.

**`TOO_FEW_TRACKS` / `TOO_FEW_PAIRS_FOR_MSD`** — fewer than 5 tracks, or fewer
than 100 displacement pairs at the top fit lag. The MSD fit and every window
derived from it rest on weak statistics. The run continues, but treat the
derived windows as provisional.

**`SIGMA_ESTIMATORS_DISAGREE`** — the fitted `sigma` (from the MSD intercept,
dependent on the model and the fit range) and `sigma_cov` (model-free, from
successive-displacement covariance) differ by more than a factor of 1.5, or the
fitted one is unresolvable while `sigma_cov` is not. They measure the same
quantity, so a gap this large means at least one is not measuring what it claims.
The **fitted** value is what the windows are derived from. When the fitted value
is unresolvable but `sigma_cov` is not, the model is saying there is no noise
floor while a model-free estimator on the same data says there is — read that as
a statement about the fit, not about the data.

**`ANOMALOUS_DIFFUSION`** — the fitted `alpha` departs from 1 by more than **0.2**
(the stated threshold). The motion is not normal diffusion, so the linear model
the tool used to assume would have been misspecified: it would have absorbed the
curvature into the intercept and the slope, making both the localisation noise
and the motion scale depend on where the fit range stopped. The fitted model is
used instead. Consult the fit-range sensitivity table to see what that changes —
a better-specified model does not automatically mean a more stable answer.

**`SIGMA_UNRESOLVABLE`** — the fitted MSD intercept is not positive, so the
localisation noise cannot be resolved from this data. `sigma` is reported as 0,
which makes the smoothing-window derivation ask for no smoothing. No value has
been substituted.

This is a common and meaningful outcome under the anomalous model. A concave MSD
can be described by curvature alone, with no positive noise floor left over. When
that happens the honest reading is that **this data does not exhibit a
localisation-noise floor that the noise criterion can measure**, so that criterion
cannot justify smoothing. It is not a failure of the fit, and it must not be
worked around by forcing the intercept positive or by reverting to the linear
model — the linear model's positive intercept was the curvature in disguise.
Judge the window from the sensitivity table, or set `--smooth-window` explicitly.

One condition stops the whole run rather than warning, because there is no honest
way to continue: input files that are not row-for-row comparable, a missing
required column, duplicate `(Track_ID, Frame)` rows, two inputs sharing a
basename, or invalid arguments. The partial report is written before exiting,
with status 2.

**Colliding input basenames are rejected up front.** Every per-file output — the
`_smoothed.csv` name, the report sections, the per-method statistics — is keyed on
the input basename, so two inputs in different directories with the same filename
would overwrite each other's output and collide in the report while the run exited
0 as though nothing were wrong. The error names every conflicting path. Rename or
copy the files to distinct names.

## When a method fails

Two conditions fail a **single method** while every other method in the run
processes and is written normally. No `_smoothed.csv` is produced for the failed
method, the failure is listed in a "METHOD FAILURES" section at the end of the
report and marked in the summary table, and the run exits with status 3.

**`DERIVATION_FAILED`** — a parameter could not be derived from that method's
data: an MSD that is not linear over its first three lags, a non-positive fitted
slope, or too few usable lags. The tool reports what failed and refuses rather
than guessing. If the failure happened after the MSD was characterised, `--plot`
still writes the MSD panel, since that is the evidence for what went wrong.

**`SMOOTHING_WINDOW_DEGENERATE`** — the derived smoothing window came out at or
above the median track span. A window that wide spans every frame a typical
track has, so the moving average reduces those tracks to a single track mean.
That is not a smoothed trajectory and the tool will not emit one: no
`_smoothed.csv` is written for that method.

The report states the derived window, the median track span, and how many tracks
and points the window swallows end to end. Everything that led there is still
printed for that method — the MSD table, the derived parameters, the outlier
counts, the per-track breakdown and the full sensitivity table — because that is
the evidence you need in order to choose a window yourself. With `--plot`, the
diagnostic PNG is written too.

If a window that wide is genuinely intended, pass `--smooth-window` explicitly.
An explicit override is you stating the intent, so it bypasses the refusal; the
report then records the derived value, notes that it would have been refused,
and records the override that replaced it.

This is the same rule that governs failed derivations — refuse rather than
guess — applied at the point where the derivation succeeds arithmetically but
produces something that cannot be honestly called a smoothed trajectory.

## Per-track outlier breakdown

Stage 4 reports the distribution of outlier rates across tracks, not just the
overall figure: the track count, how many tracks have no outliers at all, the
min/q25/median/q75/max of the per-track rate, and every track above a stated 10%
rate named individually with its counts.

Read it to tell one bad track from a global problem. If a handful of named
tracks contribute most of the outliers, the problem is those tracks — a lost
object, a collision, a track that wandered off the surface. If the rate is
spread evenly and no individual track stands out, the problem is the method or
the acquisition, and rejecting harder will not fix it.

## Plots

`--plot` writes one PNG per method with two panels:

* **MSD vs lag** — the pooled MSD points, the fitted line with `sigma` and `D`
  in the legend, the fit range shaded, the intercept marked, and the confinement
  lag drawn if one was found. A fit range that covers only the first few lags
  while the points climb far above the fitted line is the visual signature of a
  slope that under-describes the motion, which is what produces an implausibly
  wide smoothing window.
* **Sensitivity** — mean `|dZ|` per frame against smoothing window, with and
  without rejection, and the window in use marked. When the window in use lies
  beyond the standard sampled range, intermediate windows are sampled to cover
  the gap, so no plotted segment spans ground that was never measured. Those
  extra windows appear in the sensitivity table too. They are spaced
  **logarithmically**: the curve falls steeply at small windows and flattens out,
  so even spacing would spend most of the points on the flat tail and
  under-resolve the part that actually changes.

## `--mad-threshold` is not a fourth dependency

Measured across `--mad-threshold` 3.0, 3.5, 4.0, 5.0 and 6.0: `sigma`, `alpha`,
`Gamma`, `W_smooth` and `W_hampel` are **completely invariant**, to every printed
digit. This is structural, not luck — `--mad-threshold` enters only the Stage 4
rejection and the cross-method consensus test. Stage 2 uses its own fixed 5.0 MAD,
and Stage 3 fits the Stage-2-cleaned series, so nothing in the derivation can see
it.

It does move the **output**: the outlier rate ranges 1.34%–3.13% over that span, a
2.3× swing in how many points are removed. That is a dependency of the smoothed
series, not of the derived parameters, and it is a different kind of thing from the
three the report already names. **The three-dependency statement stays three.**

## What remains is not on the tool

The tool is complete as an instrument. What it now reports about this dataset is a
result, not a defect: **this data does not determine the smoothing window.** Two
things would change that, and neither is a software change.

**The interval is wide because the data is thin for this fit.** 70 tracks of median
span 74 frames is not much for a three-parameter MSD fit, and the 95% window
interval of `[3, 21]` around a point estimate of 7 follows directly from that. More
tracks, or longer ones, would narrow it. That is an acquisition question.

**Both radius-based methods fail, from two independent checks.** `radius_mean` is
flagged by the cross-method consensus check; `radius_median` fails derivation and
its MSD is non-monotonic in a way no diffusive process can be. The two checks share
no machinery and point at the same place. That is a TopoJ sampling-geometry
question.

## Cost note: the transfer measurement

The per-run transfer measurement adds roughly two seconds and scales as
`max_span^2` through the Cholesky factorisation used to generate the fractional
Brownian motion. On this dataset (max span 281) that is negligible. On a
substantially larger dataset — much longer tracks, not merely more of them — it
could come to dominate the run. No change made; recorded so the cause is obvious
if a future run is unexpectedly slow.

## Uncertainty on `alpha`, and on the window

`alpha` is fitted, so it has an uncertainty, and the `1/alpha` exponent amplifies
it. The report gives a 95% interval on both.

**Method: bootstrap over tracks**, 200 replicates, percentile interval, fixed seed.
Tracks are the independent units — the MSD is pooled across them, while within a
track the lags are strongly correlated and the residuals are not independent. That
correlation rules out a residual-based interval and would force a profile likelihood
to assume a noise model for the MSD points that is intractable to get right. A
track-level bootstrap needs no such model: it resamples the thing that would
actually vary between repeat experiments. Each track's contribution to the pooled
sums is additive, so the per-track sums are computed once and a replicate is a sum
over sampled tracks rather than a re-pass over the data.

The **fit range is held fixed** at the range chosen for the point estimate, so the
interval is conditional on it. The separate dependence on where the fit stops is the
fit-range sensitivity table's job and is not folded in.

**The amplification is real and was confirmed, not assumed.** On this dataset the
window's relative interval is 2.4–4.9× the width of `alpha`'s, and the `1/alpha`
exponent alone accounts for a 2.3–3.5× amplification on the sound methods; the rest
comes from `sigma` and `Gamma` varying in the same replicates.

**The intervals are wide.** On this dataset every method raises
`WINDOW_NOT_DETERMINED`: `four_neighbor_median` gives `W = 7` with a 95% interval of
`[3, 21]`. The point estimate is still what gets used, but it is far more precise
than the data warrants, and anything downstream sensitive at that level should be
checked across the interval rather than at the point.

For `radius_mean` the `alpha` interval reaches 0.13, where `1/alpha` diverges and
the implied window runs away without bound. The report says so rather than printing
the resulting number — an `alpha` that poorly determined cannot support an exponent
at all.

## Derivation stamp

Every report and every parameter block carries a short hash — the **derivation
stamp** — over the derivation version, every declared constant, and the CLI
arguments the derivation reads. Report-only settings (`--plot`,
`--frame-interval`) are excluded so they do not perturb it.

Two runs sharing a stamp produced their numbers the same way. An output carrying a
different stamp came from a different derivation and must not be compared with the
current one. The version history is in `DERIVATION_VERSION` in the source, so a
stale file can be placed from its stamp alone:

```
  -1  linear MSD model, 2*sigma^2 + D*tau
  -2  anomalous model, 2*sigma^2 + Gamma*tau^alpha, fit range by residual only
  -3  sigma-stability cap on the fit range
  -4  1/alpha correction on the smoothing-window requirement
```

**Any `_smoothed.csv` written before derivation-4 is stale.** The `1/alpha`
correction moved the sound methods from `W = 9, 9, 7` to `7, 7, 7` and
`radius_mean` from 5 to 11. Regenerate anything already taken downstream.

### What the stamp does NOT cover

The stamp hashes the derivation version, the declared constants and the
derivation-relevant arguments. **It does not hash the input data.** Two runs on
completely different datasets with identical arguments produce the identical stamp —
verified directly: four unrelated inputs, including a synthetic dataset with a
different track count, frame count and Z lattice, all stamp `7bb10d0dfaa2`.

So: **a `run_stamp` identifies how a file was produced, not what it was produced
from.** It answers "was this made by the current derivation?" and cannot answer "was
this made from the current data?". The input filenames live in the report — in the
`Inputs:` block at the top and in each method's `input` field — and that is the only
place they are recorded.

This is a documented limitation rather than an oversight. Content-hashing the inputs
would close it, at the cost of making the stamp churn every time anything upstream is
re-exported, which is more noise than signal for routine use.

**Constraint on future work.** A planned extension would derive a window once and
apply it across several datasets, so that grouped datasets are not each smoothed by a
different amount. That feature must be able to tell runs on different input data
apart, and **the stamp as currently scoped cannot do that** — every dataset in the
group would carry the same one. Whoever builds it should decide at that point whether
to widen the stamp to include an input identifier, or to add a separate one alongside
it, and should not assume the existing stamp is sufficient.

The stamp is currently in the **report only**. Putting it in the CSV would change
the column set, so it has not been done — see the note below.

## Two decisions about flagged methods

Both recorded so they are not revisited without new evidence.

**Flagged methods' windows are computed and printed.** Withholding them would remove
the evidence that makes the method's brokenness legible: `radius_mean`'s
`alpha = 0.54` against 1.06–1.18 everywhere else is one of the clearest signals in
the report that it is not measuring the same thing, and it exists only because the
window was derived. A blank says "we don't know"; the number with the banner says
"we know, and here is why not to use it". This tool's failures have come from
silence, not from loud bad numbers.

**Flagged methods' `_smoothed.csv` is still written**, for the same reason.

**`radius_mean`'s `alpha = 0.54` is a genuine property of that method's output, not
a fitting failure.** This was checked directly: `alpha` is low from the shortest
admissible fit range (0.62 at L=5), sits on a proper stability plateau at L = 6–9
with `sigma` stable across it at 15.0–16.6, and the cap already excludes the region
where it collapses. That is structurally the opposite of `four_neighbor_median`'s
artifact, where `alpha` ran 1.12 → 0.49 as the range extended. The anomalous
exponent is a symptom of the sampling problem, not of the fit.

## Cross-method agreement

The report ends with a section comparing derived `sigma`, `alpha` and both windows
across the methods **not** flagged by the consensus check.

These methods sample the same tracks at the same frames through different
geometry, so their noise and motion estimates are arrived at independently.
**Independent methods converging on the same derived parameters is the strongest
available evidence that those parameters reflect the data rather than the
derivation rules** — a rule artifact would have no reason to land in the same place
from different inputs. Divergence means the opposite: at least one number is being
set by the procedure rather than by what was measured.

Flagged methods are excluded. Including a method already known to disagree with the
others would corrupt the comparison, because its divergence is expected and would
drown the signal. Methods whose derivation failed are excluded too, having no
parameters to compare. Both exclusions are listed with their reasons.

> **STALE NUMBERS BELOW — derivation-3, not reproduced by the current
> derivation.** Everything from here to the end of this section that quotes a
> smoothing window, a `w_req` value or a cross-method spread predates the
> `1/alpha` correction and was **not** updated when derivation-4 landed.
> Specifically: the smoothing windows given as `9, 9 and 7` in the next
> sentence (this README's own "Derivation stamp" section records that the
> correction moved the sound methods to `7, 7, 7`); the `1.2812×` spread; and
> the three `w_req` values `4.4977, 3.9662 and 3.5105` rounding to
> `W_smooth = 5`, where the current derivation gives `5.8230, 5.7196 and
> 5.6264` rounding to `7`.
>
> The `sigma_fit within 1.025×` and `identical Hampel windows` claims in the
> next sentence were checked and are current. The surrounding *argument* — that
> `k` cancels out of any ratio between methods, and that rounding hides real
> disagreement — is unaffected and still holds; only the illustrative figures
> are stale.
>
> **Read current values from `out/zsmooth_parameters_report.txt`, never from
> here.** Stale and current figures per
> `prompt_outputs/001-zsmooth-recon-audit.md`; annotated by task 002.

On the current dataset the three eligible methods give `sigma_fit` within 1.025×
of each other and identical Hampel windows, with smoothing windows of 9, 9 and 7.

**The `W_smooth` column is not evidence that the window is well determined.** The
requirement is `W >= 2*k^2*sigma^2/Gamma`, so `k` multiplies every method's
requirement by the same factor and **cancels exactly out of any ratio between
methods**. The cross-method spread is 1.2812× at k = 1.5, at k = 2 and at k = 3 —
identical to four decimal places, because no value of `k` could make these methods
disagree. Agreement here is strong evidence about `sigma` and `alpha`, which each
method measures independently. It is *structurally void* as evidence about the
window. The absolute window still scales as k², and `k` is still chosen by hand.

The table prints `w_req`, the continuous requirement before odd-rounding, beside
the integer. Rounding hides real disagreement at small windows: at k = 1.5 three
genuinely different requirements — 4.4977, 3.9662 and 3.5105 — all display as
`W_smooth = 5`. Read agreement from `w_req`.

## The noise transfer function of the moving average

Measured on this data's own track and gap structure, by smoothing synthetic pure
noise and a synthetic pure random walk over the real frame patterns:

```
  noise  contribution at lag 1 = 2*sigma^2 / W^2
  motion contribution at lag 1 = Gamma * W^(alpha-2)
```

Both exponents are **re-measured on every run**, per method, over that method's own
track and gap structure — synthetic uncorrelated noise and a fractional Brownian
motion at Hurst `alpha/2`, smoothed at seven windows and regressed in log-log, from
a fixed seed so the figures are reproducible. The report prints the measured
exponent beside its structural expectation. Nothing is stated as measured that was
not measured on that run.

The motion exponent depends on `alpha` and was verified against synthetic
subdiffusive walks from `alpha = 0.5` to `1.2`, matching `alpha - 2` to within
0.06 throughout:

```
 alpha    measured   alpha-2        alpha    measured   alpha-2
  0.50      -1.443     -1.50         0.90      -1.105     -1.10
  0.60      -1.383     -1.40         1.00      -0.979     -1.00
  0.70      -1.289     -1.30         1.10      -0.907     -0.90
  0.80      -1.180     -1.20         1.20      -0.774     -0.80
```

**The noise does not divide by `W`.** Successive moving-average windows overlap in
`W-1` of their `W` points, so their difference is `(1/W)*(eps[t+1+h] - eps[t-h])`
and its variance falls as `1/W²`. The motion falls only as `1/W`, because the same
difference spans `W` frames of genuine displacement. The two contributions add:
measured combined MSD matched noise + motion to within 1% at every window tested.

This matters for reading the derivation. The rationale originally given for the
smoothing window — noise falls as `sigma*sqrt(2)/sqrt(W)`, compared against the
un-attenuated single-frame motion scale — is wrong in **two** places. Requiring
instead that the ratio of the two measured contributions stay below a fraction `f`
gives

```
  ratio(W) = 2*sigma^2 / (Gamma * W^alpha)   =>   W >= (2*k^2*sigma^2/Gamma)^(1/alpha)
```

**This correction is now applied to the default derivation.** The formula used
previously, `W >= 2*k^2*sigma^2/Gamma`, is the `alpha = 1` special case. On a
genuinely subdiffusive or superdiffusive dataset it returns a **systematically
wrong window with no warning** — nothing about the output would look wrong. The
report prints both the corrected and uncorrected requirement for every method, so
the size of the correction is visible on any dataset, and raises
`ALPHA_DRIVES_WINDOW` when it exceeds 1.5×.

On this dataset the correction is small for the three sound methods and large for
the flagged one:

```
  method                  alpha   w_req uncorr  W   w_req corr   W    ratio
  four_neighbor_mean      1.180        7.9959   9       5.8230   7    1.373
  four_neighbor_median    1.120        7.0510   9       5.7196   7    1.233
  single_pixel            1.060        6.2409   7       5.6264   7    1.109
  radius_mean             0.540        3.3791   5       9.5336  11    2.821
```

**The correction improved cross-method agreement.** The three sound methods now
land on the same window (7, 7, 7 rather than 9, 9, 7) and their continuous
requirements agree to **1.035×**, against 1.281× before. Three methods measuring
the same tracks through different geometry converging more tightly under the
corrected formula is independent evidence that the correction is right — it was
not fitted to produce that outcome.

One consequence: `k` now enters each method as `k^(2/alpha)` rather than `k^2`, so
it no longer cancels *exactly* from cross-method ratios when methods have different
`alpha`. The residual dependence is weak — the spread measures 1.094×, 1.035× and
1.044× at k = 1.5, 2 and 3 — but it is no longer identically zero.

## The model-free alternative window (reported, not used)

Each method's section reports an alternative window derived entirely from measured
quantities: `sigma` from the covariance estimator, and `Gamma` from
`MSD(1) - 2*sigma_cov^2` rather than from the MSD fit.

**It does not remove a free parameter.** `f` is exactly `1/k²` and plays the
identical role — the rule is renamed, not made parameter-free. What it changes is
where the inputs come from: both `sigma` and `Gamma` are measured, so the window
stops depending on the MSD model and the fit range. That is a robustness gain, not
a reduction in free choices, and the report says so in those words.

With the `1/alpha` correction applied it gives 9, 5 and 5 against the current rule's
9, 9 and 7 on this dataset.

### Decision: the model-free rule was NOT adopted

Recorded so it is not revisited without new evidence.

`W_alt` removes the MSD model and fit-range dependence, and on the Stage-2 settings
where both rules produce a number it is the more stable of the two. It was still
**not adopted**, for one reason:

**The current rule declines to answer precisely when the noise floor becomes
unidentifiable. That is a detector, not a weakness.** It fails to derive at 2–3 of
5 Stage-2 settings — exactly the ones where `MSD(1)` doubles — while `W_alt`
returns a confident number in those same conditions (a window of 3 where the other
settings give 9). Across the whole of this project the recurring failure mode has
been confident wrong answers rather than loud failures: a Z step accepted at twice
its value, a subdiffusive exponent that was a fitting artifact, a window derived
from a method that disagreed with every other. A rule without a detector is the
wrong trade.

`W_alt` remains reported alongside as a cross-check.

### Which derivation is more robust to Stage 2?

Measured across five Stage-2 settings (window/threshold 17/5.0, 17/4.0, 7/4.0,
17/3.0, 9/3.0), the answer is **not** a straightforward win for either:

* On the settings where **both** produce a number, `W_alt` is the more stable:
  spreads of 1.024×, 1.070×, 1.017× against the current rule's 1.279×, 1.475×,
  1.030×.
* Across **all five** settings, `W_alt` is far **less** stable: 6.21×, 3.05×,
  4.71×. `MSD(1)` moves by 2.2–2.4× across these settings while `sigma_cov` moves
  only 1.08–1.19×, so `Gamma_meas = MSD(1) - 2*sigma_cov^2` absorbs nearly the
  whole swing.
* The current rule looks stable partly **because it refuses**. It fails to derive
  at 2–3 of the 5 settings — precisely the ones where `MSD(1)` doubles. `W_alt`
  never refuses, and at those settings returns a confidently different window
  (e.g. 3 instead of 9).

That difference in failure behaviour, not the spread numbers, is the substantive
distinction between them.

## radius_median is not a trajectory

`radius_median` has never produced output. That is correct behaviour, not a tool
limitation, and a statistic entirely independent of the consensus check says so.

**MSD must increase monotonically for any diffusive process.** Over the short-lag
region where the derivation actually lives (lags 1–12), the three sound methods
decrease at **no lag at all**. `radius_median` decreases at **five**: lags 2, 5, 9,
10 and 11. Over the full usable range 1–37 the contrast persists — 5, 5 and 6
decreasing lags for the sound methods, against 14 for `radius_median`. Its MSD at
lag 1 is 154.1 against 60.6 and 65.0 for `four_neighbor_median` and `single_pixel`,
about **2.5×** theirs.

Non-monotonic MSD is the signature of a **two-state process**: values flipping
between two surfaces and back. A displacement measured across one flip is large;
one measured across two flips returns near zero. That produces exactly this
pattern, and no diffusive model can describe it.

This is independent confirmation, from a completely different statistic, of the
sampling-geometry problem the cross-method consensus check already identified. The
two checks share no machinery: one compares methods against each other, the other
looks only at the internal time structure of a single method.

**`radius_median`'s derivation failure is therefore the right answer.** Its output
is not a trajectory, so no smoothing parameters should exist for it. Do not try to
make it produce output; fix the sampling geometry, or drop the method.

## The parameter block

Each method's section ends with a fixed-width `PARAMETER BLOCK` holding every
derived number for that method in one place: inputs and counts, the Z-step
verification status, Stage 2 settings, the full MSD fit, `sigma`, `Gamma`, `alpha`
with and without rejection, `tau*`, the confinement lag, `k`, both windows derived
and in use, the fit-range spread, outlier counts, the per-track summary, the speed
proxy, and the warnings raised for that method by code.

Methods that fail also get a block, marked `[FAILED]`, holding everything known
before the failure plus a `STATUS` line and the failure text — so their numbers
are not confined to prose either.

The cross-method summary table deliberately **omits `Gamma`**: its units are
Z² per frame^alpha, so with a different `alpha` per method the column would not be
comparable across rows. `Gamma` lives in each method's parameter block, where it
sits next to the `alpha` it belongs to.

**Quote it verbatim.** Do not re-type values out of the prose. Re-typing is how a
number belonging to one method ends up attributed to another — which has already
happened once in this project's history, when a residual from `radius_mean` was
reported as `four_neighbor_median`'s and then propagated into a follow-up
analysis.

## State at handover

For a reader who has not followed how this tool was built.

**This section deliberately contains no numbers.** Every figure it would otherwise
quote lives in the parameters report, which the tool writes on every run. Numbers
copied into prose go stale silently — the derivation stamp catches a changed
derivation but not changed input data, so a transcribed table can look authoritative
while disagreeing with the tool. This project already lost a round to a value
mis-copied between two methods. Read the numbers from the report; they cannot
disagree with themselves.

### Where the numbers are

```
python zsmooth.py data/*.csv --out out --z-step <YOUR STEP>     --lattice-reference <YOUR SINGLE-PIXEL FILE>
```

Then open `out/zsmooth_parameters_report.txt` and find the **`PARAMETER BLOCK`** for
your chosen method. It is fixed-width and meant to be quoted verbatim. It carries,
among others:

| Field | What it tells you |
| --- | --- |
| `derivation stamp` | Which derivation produced these numbers (not which data — see "Derivation stamp") |
| `input` | Which file they were produced from |
| `z-step verification` | Whether the Z step was checked against a single-pixel lattice, or not |
| `rows / tracks / NaN Z` | How much data the fit had |
| `sigma (fitted)` / `sigma (covariance)` | Localisation noise, two independent estimates |
| `alpha (Stage-2 cleaned)` | The anomalous exponent, with its 95% CI |
| `W_smooth derived / in use` | The smoothing window |
| `W_smooth 95% CI` | **The interval around it — read this before using the window** |
| `W_hampel derived / in use` | The outlier-rejection window |
| `outliers` / `per-track outlier rate` | How much was removed, and whether it was concentrated |
| `speed raw / smoothed` | The downstream quantity this tool exists to protect |
| `warnings` | Every check that fired for that method, by code |

The same codes appear in each output CSV's `derivation_note` column, so a reader who
opens only the CSV sees the same caveats.

### Which method to use

Use a method that is **consistent with the cross-method consensus**. The report's
`CROSS-METHOD AGREEMENT` section lists exactly those and excludes the rest, with
reasons. Consistent methods sample the same tracks through different geometry, so
their agreement on `sigma`, `alpha` and the window is the strongest evidence
available that those values reflect the data rather than the derivation rules.

**Do not use** any method whose section carries the `DO NOT USE THESE WINDOWS`
banner, or whose CSV carries `DO_NOT_USE:flagged-inconsistent`. Do not use a method
that failed derivation — no output is written for it, and that is the correct
outcome rather than something to work around.

### What the smoothing window rests on

Three arbitrary choices, all named in the report wherever the window appears:

1. **`k`, the noise margin** (`--noise-margin`, default 2.0). The window scales as
   `k^(2/alpha)`.
2. **The MSD fit range**, capped by `sigma` stability.
3. **The Stage 2 cleaning parameters**, from which `sigma`, `Gamma` and `alpha` are
   all measured.

`--mad-threshold` is *not* a fourth: it moves the outlier rate but leaves every
derived parameter untouched.

### What to conclude from the window, and what not to

Conclude that the derived window is the best available estimate, and — where the
consensus-consistent methods agree on it — that independent sampling geometries
support it.

Do **not** conclude that the data determines it. Check `W_smooth 95% CI` in the
parameter block and the `WINDOW_NOT_DETERMINED` warning. Where that warning is
present, the point estimate is more precise than the data warrants, and anything
downstream sensitive to the difference across that interval should be evaluated
across it rather than at the point.

## Reading the report

The report is ordered: header and declared constants, then Stage 1 for the whole
run, then one section per input file covering Stages 2 to 4, then a summary
table and the collected warnings. Within a file's section, the measured
quantities always appear immediately above the parameters derived from them, so
any number in the output can be traced back to what produced it.
