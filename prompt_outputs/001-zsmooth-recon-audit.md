# PHASE A — zsmooth reconnaissance audit

**Status line:** `PHASE A - zsmooth-recon - 934f617e87bf00e2767497f225659b5b018b17c6 - 4 decisions needed`

Date of audit: 2026-09-09
Auditor: read-only reconnaissance, two exceptions taken as authorised (TASK 2 scratch runs,
TASK 6 this file).

Everything below marked CONFIRMED / CONTRADICTED / UNKNOWN was checked by me against the
actual source and/or a live run. Everything attributed to "the handover" is the prompt's
claim, not my finding. Where I did not check something, it is stated under
"What I could NOT check".

---

## 0. Decisions needed (4)

These are places where the handover's wording is materially wrong or materially incomplete
against the code and the data. Each needs a ruling from you before it is written into
CLAUDE.md / RULES.md, because the wrong wording would be enshrined as a rule.

### D1. "Every parameter that affects the result is derived per dataset rather than hardcoded"

**CONTRADICTED as stated.** Several hardcoded values change the derived numbers. The source
itself makes the narrower claim and the handover has widened it.

Source docstring (`zsmooth.py`, module docstring):

> Design rule: the tool is dataset-independent.  Every temporal window is
> DERIVED from a quantity measured in the data.  The only scale-free
> statistical constant that is hardcoded is the Hampel threshold in MAD units
> (default 4.0, user-overridable).

Hardcoded values that demonstrably change the result:

| Constant | Value | Effect |
| --- | --- | --- |
| `DEFAULT_NOISE_MARGIN_FACTOR` (k) | `2.0` | `W_smooth` scales as `k^(2/alpha)`. The report itself says at k=1 the window would be 3 and at k=4 about 19, against 7 in use. |
| `STAGE2_MAD_THRESHOLD` | `5.0` | Sets which points enter the Stage 3 fit, hence sigma, Gamma, alpha, hence both windows. |
| `STAGE2_WINDOW_TRACK_FRACTION` | `0.25` | Same path. The *fraction* is hardcoded; only the track length it multiplies is measured. |
| `DEFAULT_MAD_THRESHOLD` | `4.0` | Stage 4 rejection rate and the cross-method consensus flag. |
| `SIGMA_STABILITY_TOL` / `SIGMA_STABILITY_MIN_RUN` | `0.10` / `3` | Sets the fit-range cap, hence sigma/Gamma/alpha. Directly responsible for `radius_median` failing. |
| `MSD_FIT_REL_RESID_TOL`, `MSD_MIN_FIT_LAGS`, `MSD_MIN_PAIR_FRACTION`, `CONFINEMENT_*`, `MIN_HAMPEL_WINDOW`, `ALPHA_SEARCH_*` | various | All bound or select the fit / the windows. |

The accurate statement is: **every temporal window is derived from a measured quantity; the
ratios, tolerances and thresholds that turn measurements into windows are hardcoded
constants, all of which are printed in the parameters report and hashed into the derivation
stamp.** Which of these two statements goes into the rules file is your call.

### D2. "WINDOW_NOT_DETERMINED fires for every sampling method"

**CONTRADICTED.** It fires for **4 of the 5** input methods. `radius_median_results_table.csv`
fails at Stage 3 (`DERIVATION_FAILED`) *before* `bootstrap_alpha` is ever called, so it
raises no warning at all and produces no CSV. Verbatim, from my run:

```
  warnings                   : none
  STATUS                     : FAILED -- DERIVATION_FAILED (MSD not characterised)
```

The four that do fire are `four_neighbor_mean`, `four_neighbor_median`, `radius_mean`,
`single_pixel`. The README (line 808) makes the same over-broad claim: "On this dataset
every method raises `WINDOW_NOT_DETERMINED`". Decide whether to say "every method that
produced output" or to keep "every method" and accept the inaccuracy.

### D3. "W_smooth = 7 and W_hampel = 5" and "the applied window W = 7 has a 95% bootstrap interval of [3, 21]"

**Both are true of a subset only, and the handover states them as if global.**

| Method | W_smooth | W_hampel | W_smooth 95% CI |
| --- | --- | --- | --- |
| four_neighbor_mean | 7 | 5 | **[5, 19]** |
| four_neighbor_median | 7 | 5 | **[3, 21]** |
| single_pixel | 7 | 5 | **[3, 23]** |
| radius_mean | **11** | **3** | **[1, 37]** |
| radius_median | — failed, no window derived — | | |

`[3, 21]` is `four_neighbor_median`'s interval specifically. The three CIs on the sound
methods are all different. Decide whether the rules file quotes per-method values or
forbids quoting values at all (the README's "State at handover" section takes the latter
position — see D4 / TASK 5).

### D4. "The recommended sampling method is four_neighbor_median, and the radius-based methods are flagged as unusable"

**Neither half is what the tool or the README actually says.**

* The tool recommends **no** method. There is no recommendation logic anywhere in
  `zsmooth.py`. The README's `### Which method to use` says: *"Use a method that is
  **consistent with the cross-method consensus**."* Three methods are consensus-consistent
  today — `four_neighbor_mean`, `four_neighbor_median`, `single_pixel` — not one.
* "The radius-based methods are flagged as unusable" collapses two entirely different
  outcomes. `radius_mean` is **flagged** by the Stage 1c consensus check and still gets a
  CSV with a `DO_NOT_USE:flagged-inconsistent` note. `radius_median` is **not flagged at
  all** — it fails derivation for an unrelated reason (no stable sigma plateau) and gets no
  CSV. Verbatim from the consensus table in my run, `radius_median` was never named:

```
  [WARNING: METHOD_DISAGREES_WITH_CONSENSUS] radius_mean_results_table.csv disagrees with the consensus of the other methods: 2730 of 5465 points (49.95%) differ from the median of the other methods by more than 10 (median deviation 9.972).
```

Decide the wording. Conflating "flagged" with "failed" would make a rules file that
misdescribes both mechanisms.

---

## 1. Blockers

**None.** Every task was completed. Both TASK 2 runs executed to completion. Nothing was
written into the project tree except `prompt_outputs/001-zsmooth-recon-audit.md`.

---

## 2. Proposed deviations

Listed, not done.

1. **`out/` is tracked in git and contains stale generated output.** `out/*.png` and
   `out/zsmooth_parameters_report.txt` are committed; `out/*_smoothed.csv` are not (blocked
   by the `*.csv` rule in `.gitignore`). This is an inconsistent half-tracked output
   directory. Proposal: either add `out/` to `.gitignore` or deliberately commit the CSVs
   too. Not touched.
2. **`README.md` contains at least one stale result number.** Line 925–926 states *"at k =
   1.5 three genuinely different requirements — 4.4977, 3.9662 and 3.5105 — all display as
   `W_smooth = 5`"*, and line 917 quotes a cross-method spread of `1.2812×`. These are
   pre-`1/alpha`-correction (derivation-3) figures; the current run gives requirements
   5.8230 / 5.7196 / 5.6264 and `W_smooth = 7`. The README's own "State at handover"
   section warns against exactly this. Proposal: mark or refresh those numbers. Not touched.
3. **`--lattice-reference` is not in the derivation stamp.** Verified: a run *with* the
   reference and a run *without* it both stamp `7bb10d0dfaa2`. But its presence changes
   whether `Z_STEP_UNVERIFIED` fires, which changes the `derivation_note` column written
   into every CSV. So two CSVs can carry the same `run_stamp` and different notes. This is
   arguably correct (the stamp covers *derived numbers*, and the note is not a number), but
   it is not documented in the README's "What the stamp does NOT cover". Proposal: document
   it. Not touched.
4. **`__pycache__/zsmooth.cpython-314.pyc` exists on disk.** Correctly gitignored, harmless.
   Proposal: none needed; noted only for completeness.
5. **No tests exist.** Reported as fact under TASK 1, not proposed as work here.

---

## TASK 1 — Repository and environment inventory

### 1.1 Git

Command and verbatim output:

```
$ git rev-parse --abbrev-ref HEAD
main

$ git rev-parse HEAD
934f617e87bf00e2767497f225659b5b018b17c6

$ git status --short
(no output — working tree clean)

$ git log --oneline
934f617 Add initial python files for running smoothing screening on ZTracker output data
```

Note: the session's opening git context reported the branch as `HEAD` (detached). At the
time I ran the command it reports `main`. Single commit, clean tree.

### 1.2 File tree

Tracked files (`git ls-files`):

```
.gitignore
README.md
out/four_neighbor_mean_results_table_diagnostics.png
out/four_neighbor_median_results_table_diagnostics.png
out/radius_mean_results_table_diagnostics.png
out/single_pixel_results_table_diagnostics.png
out/zsmooth_parameters_report.txt
requirements.txt
zsmooth.py
```

Full on-disk tree excluding `.git` (bytes, path):

```
       418  .gitignore
     66222  README.md
       286  requirements.txt
    155749  zsmooth.py
    197931  data\four_neighbor_mean_results_table.csv        [gitignored]
    197939  data\four_neighbor_median_results_table.csv      [gitignored]
    197528  data\radius_mean_results_table.csv               [gitignored]
    197935  data\radius_median_results_table.csv             [gitignored]
    197933  data\single_pixel_results_table.csv              [gitignored]
    104689  out\four_neighbor_mean_results_table_diagnostics.png    [tracked]
    652864  out\four_neighbor_mean_results_table_smoothed.csv       [gitignored]
    103470  out\four_neighbor_median_results_table_diagnostics.png  [tracked]
    652632  out\four_neighbor_median_results_table_smoothed.csv     [gitignored]
    109145  out\radius_mean_results_table_diagnostics.png           [tracked]
    923192  out\radius_mean_results_table_smoothed.csv              [gitignored]
    102908  out\single_pixel_results_table_diagnostics.png          [tracked]
    652241  out\single_pixel_results_table_smoothed.csv             [gitignored]
    105922  out\zsmooth_parameters_report.txt                       [tracked]
    194224  __pycache__\zsmooth.cpython-314.pyc              [gitignored]
```

`zsmooth.py` is 2703 lines. `README.md` is 952 lines. `out/zsmooth_parameters_report.txt`
is 1394 lines.

Note: `data/` holds **five** input CSVs, and `out/` holds only **four** `_smoothed.csv`
files. `radius_median_results_table_smoothed.csv` is absent, and there is no
`radius_median_results_table_diagnostics.png`. That is consistent with a derivation failure
for that method, which my run reproduces.

`.gitignore` verbatim:

```
# ---- Data: inputs and outputs are not tracked ----
# Record input identity (filename + SHA-256) in run output instead.
data/
input/
inputs/
output/
outputs/
results/
*.csv
!tests/fixtures/*.csv

# ---- Python ----
__pycache__/
*.py[cod]
.venv/
venv/
env/
.ipynb_checkpoints/

# ---- Editors / OS ----
.vscode/
.idea/
.DS_Store
Thumbs.db

# ---- Logs and scratch ----
*.log
scratch/
tmp/
```

The header comment says *"Record input identity (filename + SHA-256) in run output instead."*
The tool records the input **filename and absolute path** (in the `Inputs:` block and in each
parameter block's `input` field). It does **not** compute a SHA-256 of any input. `hashlib`
is imported and used only in `derivation_stamp`, which hashes arguments and constants, not
data. This is a mismatch between the `.gitignore` comment and the code.

### 1.3 Entry point and full CLI

Single entry point: `zsmooth.py`, `main(argv)` under `if __name__ == "__main__": raise
SystemExit(main())`. No package, no console-script, no `__main__.py`.

`python zsmooth.py --help`, verbatim:

```
usage: zsmooth.py [-h] -o DIR --z-step MICROMETRES [--lattice-reference CSV]
                  [--frame-interval SECONDS] [--mad-threshold MAD]
                  [--noise-margin K] [--plot] [--hampel-window FRAMES]
                  [--smooth-window FRAMES]
                  CSV [CSV ...]

Reject transient outliers and smooth Z(t) in ZTracker_Fiji Tool 3 (TopoJ) trajectory exports.

positional arguments:
  CSV                   one or more input CSVs, one per sampling method

options:
  -h, --help            show this help message and exit
  -o, --out DIR         output directory (created if absent)
  --z-step MICROMETRES  Z step in micrometres. REQUIRED. Used as the Hampel
                        MAD floor and cross-checked against the lattice
                        spacing found in the data.
  --lattice-reference CSV
                        which of the input files was produced by SINGLE-PIXEL
                        sampling. Only such a file carries the raw Z lattice,
                        so only it can verify --z-step. Give it exactly as it
                        appears in the input list (or as a bare filename).
                        Without it the Z step is NOT verified and a warning
                        says so.
  --frame-interval SECONDS
                        frame interval in seconds. OPTIONAL. Used ONLY to
                        additionally express speeds in micrometres per second
                        in the report; no analysis step and no derived window
                        depends on it.
  --mad-threshold MAD   Hampel threshold in MAD units for the Stage 4 pass
                        (default 4.0)
  --noise-margin K      Stage 3d noise-margin factor k: the smoothing window
                        is the smallest odd W whose residual noise
                        contribution falls below the single-frame motion scale
                        by this factor (default 2)
  --plot                write a per-method diagnostic PNG (MSD curve with the
                        fit and fit range marked, plus the sensitivity curve).
                        Requires matplotlib, which is otherwise not needed.
  --hampel-window FRAMES
                        override the derived Stage 4 Hampel window (odd, >=
                        3). Both the derived value and this override are
                        recorded in the report.
  --smooth-window FRAMES
                        override the derived smoothing window (odd, >= 1).
                        Both the derived value and this override are recorded
                        in the report.
```

Argument-by-argument, with defaults as declared in `build_parser`:

| Argument | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `inputs` (`CSV [CSV ...]`) | str, `nargs="+"` | yes | — | Basenames must be unique; `validate_args` raises `FatalDataError` on collision. |
| `-o` / `--out DIR` | str | **yes** | — | Created with `os.makedirs(exist_ok=True)`. |
| `--z-step MICROMETRES` | float | **yes** | — | Must be > 0. Doubles as the Hampel MAD floor. |
| `--lattice-reference CSV` | str | no | `None` | Must be one of the inputs; ambiguous basenames are refused. |
| `--frame-interval SECONDS` | float | no | `None` | Must be > 0 if given. Report-only. |
| `--mad-threshold MAD` | float | no | `DEFAULT_MAD_THRESHOLD = 4.0` | Must be > 0. |
| `--noise-margin K` | float | no | `DEFAULT_NOISE_MARGIN_FACTOR = 2.0` | Must be > 0. |
| `--plot` | flag | no | `False` | Fails fast if matplotlib is absent. |
| `--hampel-window FRAMES` | int | no | `None` | Must be odd and >= `MIN_HAMPEL_WINDOW` (3). |
| `--smooth-window FRAMES` | int | no | `None` | Must be odd and >= 1. Bypasses the degenerate-window refusal. |

There is **no** `--seed` argument, and no CLI control over any RNG. See TASK 2.

Exit codes, from `main`: `0` all methods processed; `2` `FatalDataError` or a run-stopping
`DerivationError`; `3` at least one per-method failure (`return 3 if failures else 0`).
Both my TASK 2 runs returned **3**.

### 1.4 Virtual environment

**None in the project folder.** Directories present at top level: `.git`, `data`, `out`,
`__pycache__`. No `.venv`, `venv`, or `env` (all three are gitignored but none exists).

### 1.5 Python interpreter

```
$ (Get-Command python).Source
C:\Users\berke.santos\AppData\Local\Programs\Python\Python314\python.exe

$ python -c "import sys; print(sys.executable); print(sys.version)"
C:\Users\berke.santos\AppData\Local\Programs\Python\Python314\python.exe
3.14.2 (tags/v3.14.2:df79316, Dec  5 2025, 17:18:21) [MSC v.1944 64 bit (AMD64)]
```

Corroborated by `__pycache__/zsmooth.cpython-314.pyc`. This is the machine-wide interpreter,
not a project environment.

### 1.6 Third-party imports and installed versions

`zsmooth.py` imports, third-party only: `numpy` (as `np`), `pandas` (as `pd`), and
`matplotlib` (lazily, inside `matplotlib_available()` and `plot_diagnostics`, only when
`--plot` is given). Standard library: `argparse`, `hashlib`, `math`, `os`, `sys`,
`dataclasses`, `typing`, `__future__`.

Pinned list as reported by the interpreter above:

```
numpy==2.4.1
pandas==3.0.0
matplotlib==3.10.8   # optional, only needed for --plot
# interpreter: CPython 3.14.2 (C:\Users\berke.santos\AppData\Local\Programs\Python\Python314\python.exe)
# pip 26.2.1
```

`requirements.txt` declares only lower bounds:

```
# zsmooth.py -- standard scientific stack only.
# scipy is not required: the MSD fit is a first-degree numpy.polyfit and the
# median/MAD statistics are numpy primitives.
numpy>=1.24
pandas>=2.0

# Optional. Needed only for --plot; the tool runs unchanged without it.
# matplotlib>=3.5
```

The installed versions satisfy those bounds. `pandas 3.0.0` is a major version ahead of
anything the file anticipated; my run produced **no** warnings on stderr (`runA_stderr.txt`
was empty), so it is working today, but the requirements file does not pin an upper bound.

### 1.7 Tests

**No tests exist.** There is no `tests/` directory. A recursive search for `test_*.py`,
`*_test.py`, `conftest.py`, `pytest.ini`, `tox.ini`, `pyproject.toml`, `setup.py`,
`setup.cfg` and `noxfile.py` returned **0** matches. There is no test runner configured and
no CI configuration of any kind. `.gitignore` carries a `!tests/fixtures/*.csv` negation for
a `tests/` tree that does not exist.

---

## TASK 2 — RNG and determinism

### 2.1 Every randomness hit in the source

Search over `zsmooth.py` for `seed|np.random|default_rng|random_state|random.|bootstrap|
resample|permutation|rng.|geomspace|standard_normal|.normal(|integers(`, case-insensitive.
Every hit, with its enclosing scope:

| Line | Enclosing scope | Text |
| --- | --- | --- |
| 85 | module level (constant) | `TRANSFER_PROBE_SEED = 20240917        # fixed, so the measurement is reproducible run to run` |
| 86 | module level (constant) | `ALPHA_BOOTSTRAP_REPLICATES = 200      # track-level bootstrap replicates for the alpha interval` |
| 87 | module level (constant) | `ALPHA_BOOTSTRAP_SEED = 20240918` |
| 889 | `def bootstrap_alpha(...)` | function definition |
| 899 | `bootstrap_alpha` docstring | `intractable. A track-level bootstrap needs no such model -- it resamples the` |
| **929** | **`bootstrap_alpha`** | **`rng = np.random.default_rng(ALPHA_BOOTSTRAP_SEED)`** |
| **934** | **`bootstrap_alpha`** | **`idx = rng.integers(0, n_tracks, n_tracks)`** |
| **1016** | **`measure_transfer_exponents`** | **`rng = np.random.default_rng(TRANSFER_PROBE_SEED)`** |
| **1030** | **`measure_transfer_exponents`** | **`noise = rng.normal(0.0, 1.0, mf.z.size)`** |
| **1034** | **`measure_transfer_exponents`** | **`inc = chol[:span, :span] @ rng.standard_normal(span)`** |
| 1747 | `sensitivity_table` | `for v in np.geomspace(top, chosen_window, SENSITIVITY_BRIDGE_POINTS + 2)[1:-1]:` — deterministic, not random; matched only because of the search term |
| 2239 | `main` | `boot = bootstrap_alpha(mf, z_stage2, msd_res.fit_lags, args.noise_margin)` |
| 2248–2251, 2257, 2300, 2318 | `main` | report strings only |

So there are exactly **two** stochastic sites in the whole tool:

1. `bootstrap_alpha` — the track-level bootstrap that produces the alpha CI and the
   `W_smooth 95% CI`, and which raises `WINDOW_NOT_DETERMINED`.
2. `measure_transfer_exponents` — the synthetic noise / fBm probe used only for the
   report-only measured transfer exponents.

There is **no** `random_state`, no `random` module import, no `np.random.permutation`, and
no unseeded RNG anywhere.

### 2.2 How the RNG is seeded

Both sites use a **`np.random.default_rng(...)` Generator instance**, not the legacy global
`np.random.seed`. `np.random.seed` does not appear in the file at all. Each function
constructs its own generator, so neither perturbs the other and neither is affected by any
global state.

Both seeds are **hardcoded module constants** and are **not exposed as CLI arguments**:

```python
TRANSFER_PROBE_SEED = 20240917        # fixed, so the measurement is reproducible run to run
ALPHA_BOOTSTRAP_SEED = 20240918
```

Consequence: the seeds cannot be varied without editing the source, so the reported
confidence interval cannot be re-drawn under a different seed from the command line. Neither
seed is included in `derivation_stamp` (which hashes `DERIVATION_VERSION`, the CLI args it
reads, and a fixed list of constants that does **not** include `ALPHA_BOOTSTRAP_SEED`,
`TRANSFER_PROBE_SEED`, `ALPHA_BOOTSTRAP_REPLICATES`, `ALPHA_CI_PERCENTILES` or
`TRANSFER_PROBE_WINDOWS`). Changing a seed in the source would therefore change the reported
CI without changing the stamp. Recorded as a fact; not proposed as work.

Also note `bootstrap_alpha` is *called with the fit range fixed*
(`bootstrap_alpha(mf, z_stage2, msd_res.fit_lags, args.noise_margin)`), and its docstring
says so explicitly: *"The FIT RANGE IS HELD FIXED at the range chosen for the point
estimate. The interval is therefore conditional on that range."*

### 2.3 Two identical runs — the empirical test

Scratch directory used (absolute, outside the project):

```
C:\Users\BERKE~1.SAN\AppData\Local\Temp\claude\C--Users-berke-santos-Documents-Python-Projects-ZTracker-Plugin-Smoothing\eba820a8-e41c-4d5f-9c32-37d3cbd14eaa\scratchpad
```

with `runA\` and `runB\` beneath it. Nothing was written into the project by these runs.

Commands (identical apart from `--out`; `--plot` deliberately omitted so no matplotlib
nondeterminism enters the comparison):

```
python zsmooth.py data/four_neighbor_mean_results_table.csv data/four_neighbor_median_results_table.csv data/radius_mean_results_table.csv data/radius_median_results_table.csv data/single_pixel_results_table.csv --out <scratch>\runA --z-step 2.0 --frame-interval 0.5 --lattice-reference single_pixel_results_table.csv
runA exit: 3

python zsmooth.py ... --out <scratch>\runB --z-step 2.0 --frame-interval 0.5 --lattice-reference single_pixel_results_table.csv
runB exit: 3
```

Exit code 3 in both cases = one method failed (`radius_median`), the other four were written.
`runA_stderr.txt` was empty.

**File-level comparison, SHA-256:**

```
four_neighbor_mean_results_table_smoothed.csv           IDENTICAL 16396E92A73F4064243AEB1ECE04EA5637B25642F234EB9BA0A489E0F0D3D630
four_neighbor_median_results_table_smoothed.csv         IDENTICAL DB8E4E71948D4FACF4ED737414B941108D3B9EC48DA7A299397E71E8B6F0F839
radius_mean_results_table_smoothed.csv                  IDENTICAL BC6711B7BEF2923B6033AE78DE5D6C9BDF635DA977F1E7E38D03007183ABB567
single_pixel_results_table_smoothed.csv                 IDENTICAL 8A3AB2245D9850854280EB8095807A054DB9B84EE67EBC5C70B7904FE10D9F3B
zsmooth_parameters_report.txt                           DIFFER
  A=82D10218BE4266E91BD687F78624B25F27CB0680EA7EC4E20B21A8CA044C1D57
  B=B3960811F14F622EE7D43C92DBD47148600D077210D712B1F826B0701FDC48C2
```

A line-by-line `Compare-Object` on the two reports returns **only** lines containing the
output path (`...\runA\...` vs `...\runB\...`): the echoed command line, the
`Output directory:` line, four `Wrote ...` lines and four `output :` fields. **No numeric
line differs.** The reports are otherwise identical.

**The stochastic quantities, verbatim from both runs.**

runA:

```
    Method: bootstrap over TRACKS, 200 of 200 replicates converged, 95% percentile interval, seed 20240918.
    alpha      = 1.1800  [0.7199, 1.4005]
    W_smooth   = 7  [5, 19]   (requirement 5.8230 [3.1802, 18.2885])
      noise  ~ W^-1.930   (structurally expected -2.00)
      motion ~ W^-0.788   (structurally expected alpha-2 = -0.82; fBm at Hurst 0.590)
  W_alt (model-free, unused)      : 7 (w_req 5.7595, f=1/k^2=0.2500)
  W_smooth 95% CI                 : [5, 19] (requirement [3.1802, 18.2885])
    Method: bootstrap over TRACKS, 200 of 200 replicates converged, 95% percentile interval, seed 20240918.
    alpha      = 1.1200  [0.7297, 1.6919]
    W_smooth   = 7  [3, 21]   (requirement 5.7196 [2.0277, 20.9510])
      noise  ~ W^-1.930   (structurally expected -2.00)
      motion ~ W^-0.841   (structurally expected alpha-2 = -0.88; fBm at Hurst 0.560)
  W_alt (model-free, unused)      : 5 (w_req 3.6897, f=1/k^2=0.2500)
  W_smooth 95% CI                 : [3, 21] (requirement [2.0277, 20.9510])
    Method: bootstrap over TRACKS, 192 of 200 replicates converged, 95% percentile interval, seed 20240918.
    alpha      = 0.5400  [0.1316, 0.9684]
    W_smooth   = 11  [1, 37]   (requirement 9.5336 [0.2059, 35.6289])
      noise  ~ W^-1.930   (structurally expected -2.00)
      motion ~ W^-1.389   (structurally expected alpha-2 = -1.46; fBm at Hurst 0.270)
  W_alt (model-free, unused)      : 69 (w_req 68.0056, f=1/k^2=0.2500)
  W_smooth 95% CI                 : [1, 37] (requirement [0.2059, 35.6289])
    Method: bootstrap over TRACKS, 200 of 200 replicates converged, 95% percentile interval, seed 20240918.
    alpha      = 1.0600  [0.6344, 1.4116]
    W_smooth   = 7  [3, 23]   (requirement 5.6264 [1.3961, 21.4971])
      noise  ~ W^-1.930   (structurally expected -2.00)
      motion ~ W^-0.895   (structurally expected alpha-2 = -0.94; fBm at Hurst 0.530)
  W_alt (model-free, unused)      : 5 (w_req 4.9833, f=1/k^2=0.2500)
  W_smooth 95% CI                 : [3, 23] (requirement [1.3961, 21.4971])
```

runB:

```
    Method: bootstrap over TRACKS, 200 of 200 replicates converged, 95% percentile interval, seed 20240918.
    alpha      = 1.1800  [0.7199, 1.4005]
    W_smooth   = 7  [5, 19]   (requirement 5.8230 [3.1802, 18.2885])
      noise  ~ W^-1.930   (structurally expected -2.00)
      motion ~ W^-0.788   (structurally expected alpha-2 = -0.82; fBm at Hurst 0.590)
  W_alt (model-free, unused)      : 7 (w_req 5.7595, f=1/k^2=0.2500)
  W_smooth 95% CI                 : [5, 19] (requirement [3.1802, 18.2885])
    Method: bootstrap over TRACKS, 200 of 200 replicates converged, 95% percentile interval, seed 20240918.
    alpha      = 1.1200  [0.7297, 1.6919]
    W_smooth   = 7  [3, 21]   (requirement 5.7196 [2.0277, 20.9510])
      noise  ~ W^-1.930   (structurally expected -2.00)
      motion ~ W^-0.841   (structurally expected alpha-2 = -0.88; fBm at Hurst 0.560)
  W_alt (model-free, unused)      : 5 (w_req 3.6897, f=1/k^2=0.2500)
  W_smooth 95% CI                 : [3, 21] (requirement [2.0277, 20.9510])
    Method: bootstrap over TRACKS, 192 of 200 replicates converged, 95% percentile interval, seed 20240918.
    alpha      = 0.5400  [0.1316, 0.9684]
    W_smooth   = 11  [1, 37]   (requirement 9.5336 [0.2059, 35.6289])
      noise  ~ W^-1.930   (structurally expected -2.00)
      motion ~ W^-1.389   (structurally expected alpha-2 = -1.46; fBm at Hurst 0.270)
  W_alt (model-free, unused)      : 69 (w_req 68.0056, f=1/k^2=0.2500)
  W_smooth 95% CI                 : [1, 37] (requirement [0.2059, 35.6289])
    Method: bootstrap over TRACKS, 200 of 200 replicates converged, 95% percentile interval, seed 20240918.
    alpha      = 1.0600  [0.6344, 1.4116]
    W_smooth   = 7  [3, 23]   (requirement 5.6264 [1.3961, 21.4971])
      noise  ~ W^-1.930   (structurally expected -2.00)
      motion ~ W^-0.895   (structurally expected alpha-2 = -0.94; fBm at Hurst 0.530)
  W_alt (model-free, unused)      : 5 (w_req 4.9833, f=1/k^2=0.2500)
  W_smooth 95% CI                 : [3, 23] (requirement [1.3961, 21.4971])
```

**Verdict: the reported bootstrap confidence interval is exactly reproducible** on this
machine, this interpreter and this numpy version, and so is the report-only transfer-exponent
measurement. Both are byte-identical between runs.

Scope of that claim: it is reproducibility of *repeat runs*, not portability. Both RNGs are
`np.random.default_rng`, i.e. PCG64, whose stream numpy guarantees to be stable across
versions; the values also depend on floating-point summation order in `pooled_msd` /
`fit_anomalous`, which I did not test across platforms or numpy versions.

### 2.4 Project tree unchanged

```
$ git status --short
(no output)
```

Run immediately after runB. Clean. The only project-tree change in this whole session is
`prompt_outputs/001-zsmooth-recon-audit.md`, created under TASK 6.

---

## TASK 3 — Claimed TOOL PROPERTIES

### 3.1 "Outliers are removed, never interpolated" — **CONFIRMED**

Three independent pieces of evidence.

`main`, Stage 4:

```python
z_rejected = mf.z.copy()
z_rejected[flags4] = np.nan
```

`gap_aware_moving_average` refuses to produce a value at a missing point — docstring and code:

```python
Points whose own Z is missing (absent or rejected) get NaN: computing a value
there would be imputation, which is deliberately not done.
...
out[~valid] = np.nan
```

The output writer emits an empty cell rather than a filled one:

```python
out_df["Z_smoothed"] = ["" if not np.isfinite(v) else f"{v:.6f}" for v in smoothed_orig]
```

And the report says so at run time: *"Flagged points are set to NaN and REMOVED. They are not
interpolated, forward-filled or imputed."* There is no `interpolate`, `ffill`, `bfill` or
`fillna` anywhere in the file.

Empirically, `Z_smoothed` is defined at 5356/5465 (98.01%), 5333/5465 (97.58%), 5195/5465
(95.06%) and 5299/5465 (96.96%) rows for the four written methods — i.e. the rejected points
are genuinely blank, not filled.

### 3.2 "Z_raw is always preserved; the original Z column is never overwritten" — **CONFIRMED**

`main`, output section:

```python
out_df = mf.raw_text.copy()
z_raw_text = mf.raw_text["Z"].to_numpy()
...
out_df["Z_raw"] = z_raw_text
out_df["Z_smoothed"] = [...]
```

`mf.raw_text` is loaded with `pd.read_csv(path, dtype=str, keep_default_na=False)` — the
original columns as verbatim strings. `Z_raw` is a copy of that same verbatim `Z`. The `Z`
column is never assigned to. `Z_smoothed` is a new column.

Verified on the real output — every written CSV header, and a first data row:

```
header: Track_ID,Frame,X,Y,Z,Z_raw,Z_smoothed,outlier_flag,run_stamp,derivation_note
row1  : 7,0,258.8370,1053.5801,350.5000,350.5000,346.625000,False,7bb10d0dfaa2,WINDOW_NOT_DETERMINED;CONFINEMENT_UNBOUNDED
```

`Z` = `350.5000` and `Z_raw` = `350.5000` — identical, and both distinct from `Z_smoothed`.
The same holds for all four written files.

One caveat worth recording, since it is the sort of thing a rules file would want to be
precise about: `Z_raw` is technically **redundant** — it duplicates the untouched `Z` column
rather than preserving something that would otherwise be lost. Both are preserved; the claim
holds; the column is belt-and-braces.

### 3.3 "Smoothing is gap-aware — it does not treat a frame gap as contiguous" — **CONFIRMED**

The mechanism is `window_bounds`, which resolves a window in **frame numbers**, not row
offsets:

```python
def window_bounds(frames: np.ndarray, half: int) -> tuple[np.ndarray, np.ndarray]:
    """
    Row-index bounds of the gap-aware window for every point.

    The window of a point at frame f is the set of rows whose FRAME lies in
    [f - half, f + half].  ...
    """
    lo = np.searchsorted(frames, frames - half, side="left")
    hi = np.searchsorted(frames, frames + half, side="right")
    return lo, hi
```

It is used by **both** `gap_aware_moving_average` and `hampel_flags`, so gap-awareness applies
to rejection as well as smoothing. `gap_aware_moving_average_all` and `run_hampel` apply these
per track slice, so a window never crosses a track boundary either.

`covariance_sigma` is independently gap-aware, by a different route — it requires three
consecutive frames:

```python
step_ok = (fr[1:] - fr[:-1]) == 1
for i in range(fr.size - 2):
    if not (step_ok[i] and step_ok[i + 1]):
        continue
```

`pooled_msd` and `bootstrap_alpha` both lay each track onto a dense frame-indexed array with
NaN in the gaps, so a displacement is only counted when both endpoints are actually present:

```python
arr = np.full(span, np.nan)
arr[(fr - lo).astype(np.int64)] = zz
...
d = arr[lag:] - arr[:-lag]
m = np.isfinite(d)
```

The gaps are real in this data: **198 of 5395 within-track intervals (3.67%) are larger than
1 frame**, maximum gap 10 frames, and by my own independent count **54 of 70 tracks contain
at least one gap** (see TASK 4).

Not verified by me: the README's claim (line 231) that gap-awareness *"changes the window
contents for roughly a quarter of all points"*. That specific fraction is not computed
anywhere in the tool and I did not compute it.

### 3.4 "Every parameter that affects the result is derived per dataset rather than hardcoded" — **CONTRADICTED**

See **Decision D1** above for the full evidence and the accurate restatement. Summary: the
*windows* are derived from measured quantities; the *ratios and thresholds* that convert
measurements into windows are hardcoded module constants. The module docstring makes the
narrow claim ("the only scale-free statistical constant that is hardcoded is the Hampel
threshold"), which is itself too narrow — `DEFAULT_NOISE_MARGIN_FACTOR = 2.0` and
`STAGE2_MAD_THRESHOLD = 5.0` are also hardcoded statistical constants and both change the
result.

Mitigating facts, which are real and should be recorded alongside: every one of these
constants is **printed** in the report's "Declared constants" block, and most are **hashed**
into the derivation stamp. From my run:

```
Declared constants (all of them scale-free ratios or tolerances):
  Stage 2 Hampel threshold                     = 5 MAD
  Stage 2 window / median track length         = 0.25
  Stage 3d noise-margin factor k (in use)      = 2 (default 2)
  --z-step equality rel. tolerance             = 1e-06
  --z-step submultiple rel. tolerance (info)   = 1e-06
  Sensitivity bridge points beyond the range   = 8 (log-spaced)
  Per-track outlier naming rate                = 0.1
  MSD fit relative-residual tolerance          = 0.1
  MSD minimum lag pair fraction                = 0.1
  Confinement 'ceases to rise' tolerance       = 0.05
  Confinement min sustained tail / lag range   = 0.25 (never fewer than 3 lags)
  Outlier-rate warning threshold               = 0.05
  sigma/Z-range warning threshold              = 0.1
  Minimum tracks for a stable MSD fit          = 5
  Minimum pairs at the top fit lag             = 100
```

Note that this printed list is **not complete**: `SIGMA_STABILITY_TOL`,
`SIGMA_STABILITY_MIN_RUN`, `ALPHA_SEARCH_*`, `ALPHA_WARN_DEVIATION`,
`SIGMA_ESTIMATOR_DISAGREE_RATIO`, `ALPHA_CORRECTION_WARN_RATIO`, `MSD_MIN_FIT_LAGS`,
`ALPHA_BOOTSTRAP_*`, `TRANSFER_PROBE_*`, `SENSITIVITY_MAX_WINDOW` and
`SENSITIVITY_MIN_MAX_WINDOW` do not appear in it. Several of those (notably
`SIGMA_STABILITY_TOL` and `SIGMA_STABILITY_MIN_RUN`) are stated inline elsewhere in the
report prose, but the block's header claim "Declared constants" reads as exhaustive and is
not.

### 3.5 "Output CSVs carry `run_stamp` and `derivation_note` columns" — **CONFIRMED**

```python
out_df["run_stamp"] = stamp
note = build_derivation_note(mf.name, mf.name in inconsistent, rep.warnings)
out_df["derivation_note"] = note
```

Observed header on all four written CSVs:

```
Track_ID,Frame,X,Y,Z,Z_raw,Z_smoothed,outlier_flag,run_stamp,derivation_note
```

`run_stamp` = `7bb10d0dfaa2` on every row of every file in my run.

### 3.6 "`derivation_note` is a semicolon-joined, severity-ordered list of caveats, such that a WINDOW_NOT_DETERMINED condition reaches every output CSV" — **CONFIRMED for the mechanism; the "every output CSV" half is a dataset fact, not a tool guarantee**

The mechanism, `build_derivation_note`:

```python
codes: list[str] = []
if flagged:
    codes.append("DO_NOT_USE:flagged-inconsistent")
for w in warnings:
    ...
    if code in RUN_LEVEL_WARNING_CODES or f"{method_name}:" in tail:
        codes.append(code)
known = {c: i for i, c in enumerate(NOTE_SEVERITY_ORDER)}
codes.sort(key=lambda c: (known.get(c, len(known)), c))
return ";".join(codes)
```

Semicolon-joined: yes. Severity-ordered: yes, by `NOTE_SEVERITY_ORDER`, with unknown codes
sorting after the known ones alphabetically (so a check added later still reaches the CSV).
`WINDOW_NOT_DETERMINED` is 5th in that ranking.

Observed `derivation_note` values from my run:

```
four_neighbor_mean_results_table_smoothed.csv    WINDOW_NOT_DETERMINED;CONFINEMENT_UNBOUNDED
four_neighbor_median_results_table_smoothed.csv  WINDOW_NOT_DETERMINED;CONFINEMENT_UNBOUNDED
radius_mean_results_table_smoothed.csv           DO_NOT_USE:flagged-inconsistent;WINDOW_NOT_DETERMINED;ALPHA_DRIVES_WINDOW;ANOMALOUS_DIFFUSION
single_pixel_results_table_smoothed.csv          WINDOW_NOT_DETERMINED;CONFINEMENT_UNBOUNDED
```

Severity ordering holds: `DO_NOT_USE:flagged-inconsistent` (index 0) precedes
`WINDOW_NOT_DETERMINED` (index 4) precedes `ALPHA_DRIVES_WINDOW` (index 9) precedes
`ANOMALOUS_DIFFUSION` (index 10).

**The important precision.** `WINDOW_NOT_DETERMINED` is not in `RUN_LEVEL_WARNING_CODES`
(which holds only the three Z-step codes). It reaches a given method's CSV **only** because
`bootstrap_alpha`'s warning text begins `f"{mf.name}: ..."` and therefore matches the
`f"{method_name}:" in tail` test. So the routing is **per-method**, not run-wide. It reaches
every output CSV on this dataset because it happened to fire for every method that produced
output. It is not a structural guarantee, and on a dataset where one method's bootstrap were
tight, that method's CSV would correctly carry no such note.

Two related mechanical observations, recorded for accuracy:

* The `f"{method_name}:" in tail` substring test is fragile — a method whose basename is a
  prefix of another's (e.g. `a.csv` and `a.csv.csv`) could cross-attribute a note. Not a
  problem on this dataset (all five basenames are distinct and none is a prefix of another).
* `rep.warnings` is a growing list and the note is built at output time, so a method's note
  can include a run-level Z-step warning raised in Stage 1 — which is the intent.

### 3.7 "The derivation stamp records HOW a file was produced but not WHAT it was produced FROM; two runs on different input data with identical arguments produce the same stamp" — **CONFIRMED**

`derivation_stamp` reads only the derivation version, five CLI values, and a fixed constant
string. It never touches `args.inputs`:

```python
parts = [
    DERIVATION_VERSION,
    f"zstep={args.z_step!r}", f"mad={args.mad_threshold!r}",
    f"k={args.noise_margin!r}", f"hw={args.hampel_window!r}",
    f"sw={args.smooth_window!r}",
    f"c={DEFAULT_MAD_THRESHOLD},{STAGE2_MAD_THRESHOLD},...",
]
return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]
```

Direct probe:

```
baseline                : 7bb10d0dfaa2
same args (repeat)      : 7bb10d0dfaa2
mad_threshold 6.0       : e385d6b8b3b5
z_step 4.0              : 3d56856b8bfb
stamp reads inputs?     : False
```

End-to-end confirmation: a run on a **single, different** input set and with **no**
`--lattice-reference` still produced the same stamp:

```
$ python zsmooth.py data/four_neighbor_mean_results_table.csv --out <scratch>\runC --z-step 2.0 --frame-interval 0.5
DERIVATION STAMP : 7bb10d0dfaa2   (zsmooth-derivation-4)
runC exit: 0
```

And within a single run, all five different input files carry the identical stamp
`7bb10d0dfaa2`.

The README documents this explicitly and correctly (`### What the stamp does NOT cover`),
including the forward constraint that a planned multi-dataset feature *"must be able to tell
runs on different input data apart, and the stamp as currently scoped cannot do that."*

Additional finding not in the handover: **`--lattice-reference` is also not in the stamp**,
yet it changes whether `Z_STEP_UNVERIFIED` fires, which changes the `derivation_note` column
in every CSV. So two CSVs can share a `run_stamp` and carry different notes. See PROPOSED
DEVIATION 3.

### 3.8 "Methods flagged by the cross-method consensus check still have their CSVs written, with a do-not-use banner rather than being withheld" — **CONFIRMED**

Being in `inconsistent` never causes a `continue`; it only adds report text, a
`derivation_note` code and a `STATUS` string. The banner, in `main`:

```python
if mf.name in inconsistent:
    rep.rule("*")
    rep.line(f"  DO NOT USE THESE WINDOWS. {mf.name} was flagged in Stage 1c as disagreeing with the")
    ...
```

Empirically, `radius_mean_results_table.csv` was flagged:

```
  [WARNING: METHOD_DISAGREES_WITH_CONSENSUS] radius_mean_results_table.csv disagrees with the consensus of the other methods: 2730 of 5465 points (49.95%) differ from the median of the other methods by more than 10 (median deviation 9.972). A sampling window that straddles a height discontinuity produces confidently wrong values; this is that check.
```

…and its CSV **was** written, 923192 bytes, with the note
`DO_NOT_USE:flagged-inconsistent;WINDOW_NOT_DETERMINED;ALPHA_DRIVES_WINDOW;ANOMALOUS_DIFFUSION`
on every row, and parameter-block status:

```
  STATUS                          : OK -- WINDOWS NOT SOUND: method flagged as inconsistent with the consensus of the others (Stage 1c); do not use them
```

Note the contrast that matters for D4: a flagged method is written with a banner; a method
that **fails derivation** (`radius_median`) is a different mechanism and produces no CSV at
all. The README records both decisions deliberately under `## Two decisions about flagged
methods`.

### 3.9 "`--lattice-reference` exists, and when not supplied the Z-step cross-check is skipped with a warning" — **CONFIRMED**

The argument exists (see the `--help` output above). `stage1_zstep`:

```python
if lattice_reference_index is None:
    rep.line("No --lattice-reference was supplied, so the Z step has NOT been verified "
             "against the data.")
    rep.warn(
        "Z_STEP_UNVERIFIED",
        f"No --lattice-reference was given, so the supplied --z-step {z_step:.6g} could "
        f"not be verified against the data at all. ...",
    )
    return detected, "NOT VERIFIED (no --lattice-reference)"
```

One precision on "skipped": the *verification* is skipped, but a per-file **granularity
table** is still printed, explicitly labelled as information rather than a check:

```
Per-file granularity. This is INFORMATION, not a check: granularity is diagnostic of
the sampling method, not a fault. No warning is raised from this table.
```

With the reference supplied, my run reported:

```
  Z step VERIFIED: the reference lattice spacing is 2, equal to the supplied 2
  within a relative tolerance of 1e-06.
```

Two further branches exist and are not "skip": `Z_STEP_REFERENCE_NOT_LATTICE` (named
reference has no lattice) and `Z_STEP_MISMATCH` (spacing ≠ supplied step). All three of
these codes are in `RUN_LEVEL_WARNING_CODES`, so they reach every method's CSV note.
`validate_args` refuses a `--lattice-reference` that is not among the inputs, and refuses an
ambiguous basename.

### 3.10 "A W_alt estimator (window from a covariance-based sigma and a measured Gamma) exists as a cross-check and is NOT used to set the applied window" — **CONFIRMED**

`alternative_window` — docstring opens `REPORT ONLY. An alternative smoothing window built
from model-free quantities.` It takes `sigma_cov` (from `covariance_sigma`) and
`msd1`, computes `gamma_meas = msd1 - 2*sigma_cov**2`, and returns
`window = next_odd_at_least(w_req)`.

Its result is used in exactly two places, both of them report text:

* `rep.line(f"    ... => W_alt = {altw['window']}")` in `main`;
* the `("W_alt (model-free, unused)", ...)` parameter-block field and the `w_alt` key of the
  `results` dict, which feeds only the CROSS-METHOD AGREEMENT display table.

The applied window comes from `derive_windows` → `smoothing_window_requirement`, which uses
`msd_res.intercept` (the **fitted** sigma) and `msd_res.gamma`, never `covsig`. `w_smooth` is
never assigned from `altw`.

The report states it in-line: `"ALTERNATIVE WINDOW (report only -- NOT used, nothing below
depends on it)"`, and the README has a whole section `### Decision: the model-free rule was
NOT adopted`.

Empirically the two disagree, which is exactly why this matters: for `radius_mean`,
`W_alt = 69` while the applied `W_smooth = 11`.

Same status for `covariance_sigma` itself: reported as
`"Model-free localisation noise (cross-check, NOT used in any derivation)"` and used only for
the `SIGMA_ESTIMATORS_DISAGREE` warning, the noise-share line, and `W_alt`.

### 3.11 "The MSD fit range is capped by a sigma-stability plateau rule" — **CONFIRMED**

`measure_timescale` applies two criteria and takes the smaller:

```python
sigmas = sigma_by_range(fits)
plateau, l_stab = stable_plateau(fits, sigmas)

if l_stab is None:
    raise DerivationError(... "the fitted sigma has no stable plateau" ...)

best = None
if l_resid is not None:
    L = min(l_resid, l_stab)
```

`stable_plateau` extends a run of consecutive fit ranges while
`(max(vals) / min(vals) - 1.0) <= SIGMA_STABILITY_TOL` (0.10), requiring at least
`SIGMA_STABILITY_MIN_RUN` (3) ranges, and returns the **first** long-enough run. When no run
qualifies the tool **fails the method** rather than falling back — the error text says so
explicitly: *"The tool does NOT fall back to the largest positive-intercept range, nor to any
other rule."*

This is not decorative: it is the sole cause of `radius_median`'s failure in my run:

```
  failure                    : radius_median_results_table.csv: the fitted sigma has no stable plateau. Starting from lag 5, no run of at least 3 consecutive fit ranges holds sigma to within 10% (longest stable run found: 2 range(s), over fit ranges 1..5 through 1..6), so there is no range over which the noise floor is identifiable. No fit range is chosen and no window is derived.
```

And the cap is what binds on the sound methods — usable lags run to 37 but the chosen fit
range is 1..8 (or 1..9 for `radius_mean`). The "no cap" counterfactual spread is recorded in
each parameter block, e.g. `fit-range spread (no cap) : lin 8.60x / anom 7.00x` against
`fit-range spread (live, in cap) : lin 1.00x / anom 1.00x`.

The same plateau rule is applied independently to the uncleaned MSD for the
`alpha (no rejection)` cross-check, and reported as unavailable rather than manufactured when
that has no plateau of its own.

---

## TASK 4 — Claimed DATASET FACTS

For every item below: **COMPUTED** means the number is produced from the data at runtime;
**WRITTEN IN** means it is a constant or default in the source. This is the distinction the
prompt flagged as most important, so it heads each entry.

All values are from my own run (`runA`), which reproduces the committed
`out/zsmooth_parameters_report.txt` (same derivation stamp `7bb10d0dfaa2`).

### 4.1 "W_smooth = 7 and W_hampel = 5" — **COMPUTED. Partially confirmed (3 of 5 methods).**

**COMPUTED**, not written in. Neither `7` nor `5` appears as a smoothing/Hampel default
anywhere. The chain is:
`derive_windows` → `smoothing_window_requirement(intercept, gamma, k, alpha)` →
`next_odd_at_least(...)`, and for the Hampel window
`tau_star = (intercept/gamma)**(1/alpha)`, `w_hampel = next_odd_at_least(2*tau_star + 1)`.
The only hardcoded floor is `MIN_HAMPEL_WINDOW = 3`, a structural minimum for forming a
median/MAD.

Actual values today:

| Method | W_smooth derived / in use | W_hampel derived / in use |
| --- | --- | --- |
| four_neighbor_mean | 7 / 7 | 5 / 5 |
| four_neighbor_median | 7 / 7 | 5 / 5 |
| single_pixel | 7 / 7 | 5 / 5 |
| **radius_mean** | **11 / 11** | **3 / 3** |
| radius_median | failed — none derived | failed — none derived |

Note `radius_mean`'s W_hampel = 3 is the `MIN_HAMPEL_WINDOW` clamp firing (its
`tau* = 0.7317` gives `2*tau*+1 = 2.46`, i.e. a raw window of 3 anyway — the clamp and the
derivation agree here).

See Decision D3.

### 4.2 "Localisation noise sigma ≈ 4.3 to 4.4" — **COMPUTED. CONFIRMED for the three sound methods only.**

**COMPUTED.** `sigma = math.sqrt(intercept / 2.0)` in `measure_timescale`;
`sigma_cov = math.sqrt(-cov)` in `covariance_sigma`. Nothing near 4.3 is written into the
source.

| Method | sigma (fitted) | sigma (covariance) |
| --- | --- | --- |
| four_neighbor_mean | **4.31109** | 4.41256 |
| four_neighbor_median | **4.39702** | 3.96672 |
| single_pixel | **4.41805** | 4.33655 |
| radius_mean | **14.9904** | 18.7827 |
| radius_median | not resolved (failed) | 5.72363 |

The fitted sigmas of the three sound methods are 4.311, 4.397, 4.418 — squarely inside
4.3–4.4. The covariance sigmas are 4.413, 3.967, 4.337, so `four_neighbor_median`'s
model-free estimate sits *below* 4.3. `radius_mean` is 3.4× higher on both estimators. The
claim is correct if scoped to "the fitted sigma of the consensus-consistent methods" and
wrong if stated of the dataset as a whole.

No `SIGMA_ESTIMATORS_DISAGREE` warning fired for any method (all ratios are under
`SIGMA_ESTIMATOR_DISAGREE_RATIO = 1.5`; the largest is 4.397/3.967 = 1.108).

### 4.3 "Outlier rate ≈ 2 to 3 percent" — **COMPUTED. CONFIRMED for the sound methods; radius_mean is higher.**

**COMPUTED.** Stage 4 `run_hampel(mf, mf.z, w_hampel, args.mad_threshold, args.z_step)`,
`rate = n4 / max(n_finite, 1)`. The *thresholds* around it are written in
(`DEFAULT_MAD_THRESHOLD = 4.0`, `OUTLIER_RATE_WARN_FRACTION = 0.05`,
`PER_TRACK_OUTLIER_NAME_RATE = 0.10`), but the rate itself is measured.

| Method | outliers / finite points | rate |
| --- | --- | --- |
| four_neighbor_mean | 109 of 5465 | **1.995%** |
| four_neighbor_median | 132 of 5465 | **2.415%** |
| single_pixel | 166 of 5465 | **3.038%** |
| radius_mean | 270 of 5465 | **4.941%** |
| radius_median | — (failed before Stage 4) | — |

So 2.0%, 2.4%, 3.0% for the sound methods — the claim holds, with `single_pixel` marginally
over 3%. `radius_mean` at 4.94% is just under the 5% `HIGH_OUTLIER_RATE` threshold, so **no
warning fired** for it. Worth knowing: it is 0.06 percentage points from tripping a warning.

Stage 2's provisional pass (a different, stricter pass whose output is discarded) removed
2.086% / 2.013% / 2.580% / 2.562% / 2.452%.

Per-track: median rates 1.48% / 1.96% / 4.26% / 2.25%, with 23 / 19 / 5 / 19 entirely clean
tracks, and 1 / 1 / 3 / 4 tracks above the 10% naming rate.

### 4.4 "Alpha ≈ 1.06 to 1.18 for the sound sampling methods" — **COMPUTED. CONFIRMED exactly.**

**COMPUTED.** `fit_anomalous` searches alpha on a dense grid; the *grid bounds and step* are
written in (`ALPHA_SEARCH_MIN = 0.05`, `ALPHA_SEARCH_MAX = 2.00`, `ALPHA_SEARCH_STEP = 0.005`),
the fitted value is not.

```
four_neighbor_mean      alpha = 1.1800   95% CI [0.7199, 1.4005]
four_neighbor_median    alpha = 1.1200   95% CI [0.7297, 1.6919]
single_pixel            alpha = 1.0600   95% CI [0.6344, 1.4116]
radius_mean             alpha = 0.5400   95% CI [0.1316, 0.9684]   [SUBDIFFUSIVE]
radius_median           — failed, no alpha —
```

1.06, 1.12, 1.18 — the claimed range is exactly right, and all three are labelled
`[consistent with normal diffusion]` (within `ALPHA_WARN_DEVIATION = 0.20` of 1). The
`ALPHA_SEARCH_STEP = 0.005` grid is why these land on such round values.

`alpha (no rejection)` is **NOT AVAILABLE** for all four methods that got that far — for the
three sound methods because *"the anomalous model does not converge on the uncleaned MSD at
any fit range"*, and for `radius_mean` because *"the uncleaned MSD has no stable sigma
plateau of its own (longest run 2 range(s), needs 3)"*. So the size of the Stage 2 artifact
on alpha is currently unmeasured for **every** method. The README's `### The data is not
subdiffusive` section quotes an alpha-by-fit-range table for `four_neighbor_median` that the
current run does not reproduce as output (it is a historical hand-computed table, not tool
output).

### 4.5 "The applied window W = 7 has a 95% bootstrap interval of [3, 21]" — **COMPUTED. True of `four_neighbor_median` only.**

**COMPUTED**, by `bootstrap_alpha` with a hardcoded seed (`ALPHA_BOOTSTRAP_SEED = 20240918`),
hardcoded replicate count (`ALPHA_BOOTSTRAP_REPLICATES = 200`) and hardcoded percentiles
(`ALPHA_CI_PERCENTILES = (2.5, 97.5)`). The interval bounds themselves are measured; the
seed, replicate count and percentiles are written in and are not CLI-exposed.

```
four_neighbor_mean      W_smooth = 7   [5, 19]    (requirement 5.8230 [3.1802, 18.2885])   200/200 replicates converged
four_neighbor_median    W_smooth = 7   [3, 21]    (requirement 5.7196 [2.0277, 20.9510])   200/200 replicates converged
single_pixel            W_smooth = 7   [3, 23]    (requirement 5.6264 [1.3961, 21.4971])   200/200 replicates converged
radius_mean             W_smooth = 11  [1, 37]    (requirement 9.5336 [0.2059, 35.6289])   192/200 replicates converged
```

`[3, 21]` is `four_neighbor_median`'s. See Decision D3.

### 4.6 "WINDOW_NOT_DETERMINED fires for every sampling method" — **COMPUTED. CONTRADICTED — 4 of 5.**

**COMPUTED.** The trigger is a comparison of two measured bootstrap quantities:

```python
if boot["window_lo"] != boot["window_hi"]:
    rep.warn("WINDOW_NOT_DETERMINED", ...)
```

Fires for `four_neighbor_mean`, `four_neighbor_median`, `radius_mean`, `single_pixel`. Does
**not** fire for `radius_median`, which raises `warnings : none` because it fails at Stage 3
before the bootstrap is reached. See Decision D2.

### 4.7 "The recommended sampling method is four_neighbor_median, and the radius-based methods are flagged as unusable" — **CONTRADICTED as stated.**

Neither the tool nor the README names a single recommended method, and the two radius methods
are excluded by two different mechanisms. Full evidence under Decision D4.

The complete `ALL WARNINGS RAISED` section from my run, verbatim:

```
  [WARNING: METHOD_DISAGREES_WITH_CONSENSUS] radius_mean_results_table.csv disagrees with the consensus of the other methods: 2730 of 5465 points (49.95%) differ from the median of the other methods by more than 10 (median deviation 9.972). A sampling window that straddles a height discontinuity produces confidently wrong values; this is that check.
  [WARNING: WINDOW_NOT_DETERMINED] four_neighbor_mean_results_table.csv: the smoothing window is not determined to a single value by this data. The 95% bootstrap interval on alpha (0.7199, 1.4005) maps to windows 5..19, spanning more than one odd window. The point estimate 7 is reported and used, but it is more precise than the data warrants; anything downstream that is sensitive at that level should be checked across the interval.
  [WARNING: CONFINEMENT_UNBOUNDED] four_neighbor_mean_results_table.csv: MSD(tau) does not flatten within lags 1..37. The confinement timescale is unbounded by this data, so NO upper cap on the smoothing window can be derived. The smoothing window below is set by the noise criterion alone.
  [WARNING: WINDOW_NOT_DETERMINED] four_neighbor_median_results_table.csv: the smoothing window is not determined to a single value by this data. The 95% bootstrap interval on alpha (0.7297, 1.6919) maps to windows 3..21, spanning more than one odd window. The point estimate 7 is reported and used, but it is more precise than the data warrants; anything downstream that is sensitive at that level should be checked across the interval.
  [WARNING: CONFINEMENT_UNBOUNDED] four_neighbor_median_results_table.csv: MSD(tau) does not flatten within lags 1..37. The confinement timescale is unbounded by this data, so NO upper cap on the smoothing window can be derived. The smoothing window below is set by the noise criterion alone.
  [WARNING: ALPHA_DRIVES_WINDOW] radius_mean_results_table.csv: the 1/alpha correction changes the smoothing-window requirement by 2.82x (uncorrected 3.3791 -> corrected 9.5336; alpha = 0.5400, 1/alpha = 1.8519), above the stated 1.5x threshold. On this dataset alpha materially drives the window, so the window is only as trustworthy as the fitted exponent. Check the fit-range sensitivity table and the plateau before relying on it.
  [WARNING: WINDOW_NOT_DETERMINED] radius_mean_results_table.csv: the smoothing window is not determined to a single value by this data. The 95% bootstrap interval on alpha (0.1316, 0.9684) maps to windows 1..37, spanning more than one odd window. The point estimate 11 is reported and used, but it is more precise than the data warrants; anything downstream that is sensitive at that level should be checked across the interval.
  [WARNING: ANOMALOUS_DIFFUSION] radius_mean_results_table.csv: the fitted anomalous exponent is alpha = 0.5400, which departs from 1 by more than the stated 0.2. The motion is subdiffusive, so a linear MSD model would have been misspecified here: it would have absorbed the curvature into the intercept and the slope, making the localisation noise and the motion scale both depend on where the fit range stopped. The fitted model is used instead. See the fit-range sensitivity table for what that changes.
  [WARNING: WINDOW_NOT_DETERMINED] single_pixel_results_table.csv: the smoothing window is not determined to a single value by this data. The 95% bootstrap interval on alpha (0.6344, 1.4116) maps to windows 3..23, spanning more than one odd window. The point estimate 7 is reported and used, but it is more precise than the data warrants; anything downstream that is sensitive at that level should be checked across the interval.
  [WARNING: CONFINEMENT_UNBOUNDED] single_pixel_results_table.csv: MSD(tau) does not flatten within lags 1..37. The confinement timescale is unbounded by this data, so NO upper cap on the smoothing window can be derived. The smoothing window below is set by the noise criterion alone.
```

And `METHOD FAILURES`, verbatim:

```
  [FAILED: DERIVATION_FAILED] radius_median_results_table.csv: the fitted sigma has no stable plateau. Starting from lag 5, no run of at least 3 consecutive fit ranges holds sigma to within 10% (longest stable run found: 2 range(s), over fit ranges 1..5 through 1..6), so there is no range over which the noise floor is identifiable. No fit range is chosen and no window is derived. The tool does NOT fall back to the largest positive-intercept range, nor to any other rule.

  1 of 5 methods produced no smoothed output. The remaining 4 processed normally.
```

Not fired anywhere: `HIGH_OUTLIER_RATE`, `NOISE_DOMINATED`, `SIGMA_UNRESOLVABLE`,
`SIGMA_ESTIMATORS_DISAGREE`, `HAMPEL_WINDOW_SPANS_TRACK`, `TOO_FEW_TRACKS`,
`TOO_FEW_PAIRS_FOR_MSD`, `NAN_Z_PRESENT`, and all three `Z_STEP_*` codes.

### 4.8 "radius_mean yields alpha ≈ 0.54" — **COMPUTED. CONFIRMED exactly.**

`alpha (Stage-2 cleaned) : 0.5400  [SUBDIFFUSIVE]  95% CI [0.1316, 0.9684]`.

Not written in anywhere. The grid step of 0.005 means the fitted optimum landed exactly on
0.540. Consequences visible in the same run: `ANOMALOUS_DIFFUSION` fired, `ALPHA_DRIVES_WINDOW`
fired at 2.82× (uncorrected requirement 3.3791 → corrected 9.5336), and the `1/alpha = 1.8519`
exponent is what lifts `W_smooth` from 5 to 11.

### 4.9 "70 tracks, median span ≈ 74 frames, 54 of 70 contain frame gaps" — **COMPUTED. CONFIRMED, all three.**

**COMPUTED** by `stage1_describe` (tracks, spans, gap histogram). The 54-of-70 figure is
**not** computed by the tool — the tool reports gap *intervals*, not gapped *tracks* — so I
computed it independently:

```
$ python -c "... groupby('Track_ID') ..."
columns: ['Track_ID', 'Frame', 'X', 'Y', 'Z']
rows: 5465 tracks: 70
median span: 74.0 median length: 67.5
tracks containing frame gaps: 54 of 70
```

The tool's own per-file description, identical across all five files (they share Track_ID,
Frame, X and Y by construction — Stage 1a verifies this):

```
  rows                : 5465
  tracks              : 70
  NaN / blank Z       : 0 (0.000%)
  track length (pts)  : min 42  q25 49  median 68  q75 97  max 264  mean 78.1
  track span (frames) : min 43  median 74  max 281
  frame gaps          : 5395 intervals, 198 (3.67%) larger than 1 frame; max gap 10 frames
  gap histogram (gap:count, first 8): 1:5197, 2:72, 3:26, 4:21, 5:18, 6:15, 7:13, 8:16
```

All three claims hold. Note the tool prints median track *length* as `68` where the true
median is 67.5 — an artifact of `f"{67.5:.0f}"` rounding half-to-even. That rounded 68 is
what feeds the printed Stage 2 window description; the Stage 2 window itself is computed from
the unrounded 67.5 (`next_odd_at_least(0.25 * 67.5) = next_odd_at_least(16.875) = 17`), which
matches the reported `window : 17 frames`. Cosmetic, not a numeric error, but it is the kind
of thing that looks like an inconsistency when quoted out of the report.

### 4.10 "MSD fitting is pooled across all tracks — one sigma, one Gamma, one alpha for the whole dataset rather than per-track" — **CONFIRMED, with one precision.**

`pooled_msd` accumulates squared displacements into per-lag sums over **all** track slices
and divides once:

```python
ssum = np.zeros(max_lag + 1, dtype=float)
scnt = np.zeros(max_lag + 1, dtype=np.int64)
for start, stop in mf.slices:
    ...
    ssum[lag] += float(np.dot(dv, dv))
    scnt[lag] += int(m.sum())
msd = np.where(scnt > 0, ssum / np.maximum(scnt, 1), np.nan)
```

`fit_anomalous` is then called once on the pooled curve, yielding a single
`(intercept, gamma, alpha)` per file. There is no per-track fit anywhere.

**The precision:** it is one set of values per **input file (method)**, not one for the whole
run. The five files each get their own sigma/Gamma/alpha, which is exactly what makes the
CROSS-METHOD AGREEMENT section possible. So "one for the whole dataset" is right in the sense
the claim intends (not per-track) and wrong if read as "one for the whole run".

Tracks *are* used as independent units in exactly one place — `bootstrap_alpha` resamples
tracks with replacement, exploiting the additivity of each track's contribution to the pooled
sums:

```python
Each track's contribution to the pooled sums is additive, so the per-track sums
are computed once and a replicate is a sum over sampled tracks rather than a
re-pass over the data.
```

---

## TASK 5 — Dependencies and documentation

### 5.1 "Three dependencies of the derived window: k, the MSD fit range, the Stage 2 cleaning parameters; and `--mad-threshold` is NOT among them" — **CONFIRMED**

The tool prints exactly those three, verbatim from my run (`four_neighbor_mean` section):

```
  HOW THIS SMOOTHING WINDOW WAS SET -- read before using it.
  It is NOT a measured quantity. It depends on THREE arbitrary choices:
    1. k, the noise margin (--noise-margin, in use 2). The window scales as k^(2/alpha) = k^1.695:
       at k = 1 it would be about 3, at k = 4 about 19, against 7 here.
       (k^2 exactly only at alpha = 1.) k can therefore be moved to reach almost any window,
       and any downstream speed.
    2. The MSD fit range. See the fit-range sensitivity table above: the window varies by
       1.00x across fit ranges under the model in use.
    3. The Stage 2 cleaning parameters (window 17, 5 MAD). sigma, Gamma and alpha are all
       measured on Stage-2-cleaned data.
    MSD(tau) never flattened, so no confinement timescale exists in this data and no upper
    cap could be derived. Nothing measured bounds the window from above at all.
    The sensitivity table below is the evidence for judging whether the window in use is
    right. None of the three choices is self-justifying.
```

`--mad-threshold` is **not** among the three, in the tool or in the README. The README devotes
a section to why (`## --mad-threshold is not a fourth dependency`), reporting that across
`--mad-threshold` 3.0/3.5/4.0/5.0/6.0 the derived parameters are *"completely invariant, to
every printed digit"* while the outlier rate swings 1.34%–3.13%.

**Structurally this is right**, and I traced the reason: `--mad-threshold` enters only
(a) the Stage 4 `run_hampel` call, which happens *after* every parameter is derived, and
(b) `stage1_cross_method`'s consensus flag test. Stage 2 uses its own `STAGE2_MAD_THRESHOLD`,
and Stage 3 fits the Stage-2-cleaned series, so nothing in the derivation can see it.

**Two precisions the rules file should carry, because "no dependency" is slightly stronger
than the truth:**

1. `--mad-threshold` **does** enter the consensus test —
   `abs(scores[k] - centre) > mad_threshold * mad_used` in `stage1_cross_method` — so it can
   change *which methods are flagged*, and therefore change the `DO_NOT_USE:flagged-inconsistent`
   code in a CSV's `derivation_note` and which methods appear in CROSS-METHOD AGREEMENT. The
   README states this ("enters only the Stage 4 rejection and the cross-method consensus
   test") but does not draw out the consequence.
2. `--mad-threshold` **is** hashed into the derivation stamp
   (`f"mad={args.mad_threshold!r}"`), so changing it changes the stamp even though it changes
   no derived window. Verified: `mad_threshold 6.0 : e385d6b8b3b5` against baseline
   `7bb10d0dfaa2`.

Neither of these makes it a fourth dependency *of the window*, which is what the claim says.
The claim stands.

### 5.2 "The tool prints a sensitivity table" — **CONFIRMED. Two distinct tables, in fact.**

The handover says "a sensitivity table". There are **two**, with different purposes, and a
rules file should not conflate them.

**(a) The smoothing sensitivity table** — `sensitivity_table()`, printed in Stage 4.
Columns: `window`, `no rejection`, `with rejection`, `pairs (rej.)`. Verbatim header and
first rows from my run:

```
  Sensitivity table (mean |dZ| per frame vs smoothing window; window range 1..33 derived from half the median track length [68], capped at 51):
     window   no rejection   with rejection  pairs (rej.)
          1        5.95427           3.9929          5190
          3        2.43481          1.70787          5190
          5        1.62582          1.20593          5190
          7        1.31869          1.00543          5190  <-- chosen
          9        1.10218         0.856577          5190
         11       0.984615         0.759012          5190
         13       0.896528         0.717096          5190
         15       0.826918         0.662362          5190
```

The chosen window is marked `<-- chosen`. The window range is derived
(`prev_odd_at_most(min(max(median_track_length/2, 11), 51))`) and log-spaced bridge points
are added if the chosen window lies beyond the standard range. It is printed for **every**
method regardless of outcome — including one that is about to fail on
`SMOOTHING_WINDOW_DEGENERATE`, deliberately, because it is the evidence a user needs to pick
an override.

**(b) The fit-range sensitivity table** — `fit_range_sensitivity()`, printed in Stage 3.
Columns: `range` | `lin 2sig^2`, `lin D`, `lin W` | `2sig^2`, `Gamma`, `alpha`, `W`, `relres`.
Header from the source:

```python
rep.line(f"    {'range':>8s} | {'lin 2sig^2':>10s} {'lin D':>9s} {'lin W':>6s} | "
         f"{'2sig^2':>10s} {'Gamma':>9s} {'alpha':>7s} {'W':>6s} {'relres':>7s}")
```

Rows are marked `<-- in use` or `(within cap)`. It reports a LIVE spread (ranges inside the
cap) and a COUNTERFACTUAL spread (all ranges, i.e. without the cap), and prints one of three
verdict strings. The discarded linear model is shown for comparison only.

### 5.3 README: exists, and mixes hardcoded result numbers with a numbers-free handover section

**A README exists**: `README.md`, 952 lines / 66222 bytes, tracked. Its section headings:

```
# zsmooth
## Install and run
## CLI
## Exit codes
## Input format
## Output format
## Design rule: dataset independence
## Processing stages
### Stage 1 — Diagnose
### Stage 2 — Strict first pass
### Stage 3 — Measure the timescale
### The data is not subdiffusive — that was a fitting artifact
### Stage 4 — Reject and smooth
## Derived parameters — what they mean
### The smoothing window is not a measured quantity
## The Z-step cross-check, and why it exists
### Only one kind of file can answer the question
### Two earlier versions of this check, both wrong
### What the check does now
### A median-granularity check was considered and dropped
### Your responsibility
## The cross-method consensus check, and why it exists
## Warnings — how to interpret them
## When a method fails
## Per-track outlier breakdown
## Plots
## `--mad-threshold` is not a fourth dependency
## What remains is not on the tool
## Cost note: the transfer measurement
## Uncertainty on `alpha`, and on the window
## Derivation stamp
### What the stamp does NOT cover
## Two decisions about flagged methods
## Cross-method agreement
## The noise transfer function of the moving average
## The model-free alternative window (reported, not used)
### Decision: the model-free rule was NOT adopted
### Which derivation is more robust to Stage 2?
## radius_median is not a trajectory
## The parameter block
## State at handover
### Where the numbers are
### Which method to use
### What the smoothing window rests on
### What to conclude from the window, and what not to
## Reading the report
```

**The answer to the question as posed is: it does both, in different sections.**

*It points the reader at the parameter block* — `## State at handover` is explicit:

> **This section deliberately contains no numbers.** Every figure it would otherwise
> quote lives in the parameters report, which the tool writes on every run. Numbers
> copied into prose go stale silently — the derivation stamp catches a changed
> derivation but not changed input data, so a transcribed table can look authoritative
> while disagreeing with the tool. This project already lost a round to a value
> mis-copied between two methods. Read the numbers from the report; they cannot
> disagree with themselves.

followed by `### Where the numbers are`, which gives the command and a table of which
`PARAMETER BLOCK` fields to read.

*But the explanatory sections are full of hardcoded result numbers.* Examples I located:

| Line | Text |
| --- | --- |
| 193–198 | An `alpha` by fit-range table for `four_neighbor_median` (1..5 → 1.145, … 1..37 → 0.500) |
| 203–204 | "Three of the four surviving methods now fit `alpha` between 1.06 and 1.18" |
| 323 | "The stability plateau returns 4.40, within 11% of it" |
| 764 | "70 tracks of median …" |
| 809–810 | "`four_neighbor_median` gives `W = 7` with a 95% interval of `[3, 21]`" |
| 838–840 | "`W = 9, 9, 7` to `7, 7, 7` and `radius_mean` from 5 to 11" |
| 848 | "all stamp `7bb10d0dfaa2`" |
| 877, 885, 889–890 | `alpha = 0.54`, `alpha` ran 1.12 → 0.49 |
| 917 | "The cross-method spread is 1.2812× at k = 1.5, at k = 2 and at k = 3" |
| 925–926 | "at k = 1.5 three genuinely different requirements — 4.4977, 3.9662 and 3.5105 — all display as `W_smooth = 5`" |
| 953–955 | A measured transfer-exponent table |
| 986–989 | A four-row per-method table: `1.180 7.9959 9 5.8230 7 1.373` etc. |
| 1066–1070 | `radius_median` decreasing-lag counts and MSD(1) = 154.1 |

I spot-checked these against my run. Most are **current**: line 986–989's table matches
exactly (`four_neighbor_mean 1.180 / 7.9959 / 9 / 5.8230 / 7`), and line 848's stamp
`7bb10d0dfaa2` matches. But at least one block is **stale**: lines 917 and 925–926 quote a
cross-method spread of `1.2812×` and requirements `4.4977, 3.9662, 3.5105` all rounding to
`W_smooth = 5`, whereas the current derivation-4 requirements are `5.8230, 5.7196, 5.6264`
rounding to `W_smooth = 7`. Those are pre-`1/alpha`-correction figures that survived the
derivation-3 → derivation-4 change. See PROPOSED DEVIATION 2.

The README contains **no** hardcoded numbers in the one place that matters most for a
handover — `## State at handover` — and does contain them throughout the explanatory and
decision-record sections, where they function as evidence for decisions rather than as
values to be used. That distinction is probably the intent, but the stale block shows the
risk the README itself warns about has already materialised once.

---

## What I could NOT check

Stated plainly, because an unstated gap reads as a clean bill of health.

1. **Cross-platform / cross-version reproducibility of the bootstrap CI.** I ran twice on one
   machine, one interpreter (CPython 3.14.2), one numpy (2.4.1). I did **not** test a
   different OS, interpreter or numpy version. `default_rng`/PCG64 streams are
   version-stable by numpy policy, but the fitted values also depend on floating-point
   summation order in `pooled_msd` and `fit_anomalous`, which I did not test.
2. **Correctness of the physics or the statistics.** I verified that the code does what the
   claims say it does. I did not verify that the anomalous-diffusion model, the
   sigma-stability rule, the covariance sigma estimator or the track-level bootstrap are the
   *right* choices, nor that the fitted numbers are *true* of the underlying motion.
3. **The README's "roughly a quarter of all points" gap-awareness claim** (line 231). The
   tool computes no such statistic and I did not compute it.
4. **The README's `--mad-threshold` invariance sweep** (3.0/3.5/4.0/5.0/6.0, outlier rate
   1.34%–3.13%). I confirmed the invariance *structurally*, by tracing where
   `args.mad_threshold` is read. I did **not** re-run the five-point sweep.
5. **Any behaviour of `--plot`.** Both TASK 2 runs omitted it, deliberately, to keep
   matplotlib out of the determinism comparison. So `plot_diagnostics` is unexercised in this
   audit; the four committed PNGs in `out/` came from an earlier run I did not reproduce.
6. **Any behaviour on inputs other than the five files in `data/`.** All error paths —
   `FatalDataError` on missing columns / duplicate `(Track_ID, Frame)` / basename collisions
   / row-mismatched files, the `Z_STEP_MISMATCH` and `Z_STEP_REFERENCE_NOT_LATTICE` branches,
   `SMOOTHING_WINDOW_DEGENERATE`, `HAMPEL_WINDOW_SPANS_TRACK`, the override paths — were read
   in source but **not executed**. Exit code 2 was never observed.
7. **Whether the committed `out/` artifacts match the current source.** The committed report
   carries the same stamp (`7bb10d0dfaa2`) and the same command line I re-ran, and the values
   I sampled match, but I did not diff the committed report against my run line by line (it
   would differ in the output path anyway).
8. **Git history beyond one commit.** There is one commit; there is no history to check a
   claim against.
9. **`Z_smoothed` numerical correctness.** I confirmed the columns exist and that rejected
   points are blank. I did not independently recompute a moving average to verify the
   `Z_smoothed` values.
10. **Whether `data/` contains the same files the committed `out/` was produced from.**
    Inputs are gitignored and the tool records no input hash (see the `.gitignore` comment
    mismatch under TASK 1.2), so this is not checkable from the repository. My run
    reproducing the same derived values is suggestive but not proof.

---

## Provenance of this file

Written under TASK 6 as the second authorised exception to read-only. It is the complete
record; the chat report is derived from it and is a strict subset. No other file was created,
edited, moved or deleted in the project tree. `git status --short` was clean immediately
before this file was written, and the only entry it shows afterwards is this file itself.

--- END OF REPORT ---
