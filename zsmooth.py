#!/usr/bin/env python3
"""
zsmooth.py -- post-process Z-coordinate trajectories exported by the
ZTracker_Fiji Tool 3 (TopoJ) plugin.

Rejects transient outliers, then smooths Z(t), so that speeds derived
downstream are not dominated by measurement noise or single-frame artifacts.

Design rule: the tool is dataset-independent.  Every temporal window is
DERIVED from a quantity measured in the data.  The only scale-free
statistical constant that is hardcoded is the Hampel threshold in MAD units
(default 4.0, user-overridable).  All analysis is in FRAME units; the frame
interval in seconds, if supplied, is used only to additionally express speeds
in micrometres per second in the report.

Usage:
    python zsmooth.py data/*.csv --out out --z-step 2.0
    python zsmooth.py data/a.csv data/b.csv -o out --z-step 2.0 --frame-interval 0.5
"""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Declared constants.
#
# STATISTICAL (scale-free, in MAD units) -- the only permitted hardcoded
# statistical constant, per the design rule, is the Hampel threshold.
# ---------------------------------------------------------------------------
DEFAULT_MAD_THRESHOLD = 4.0        # Stage 4 Hampel threshold, user-overridable
STAGE2_MAD_THRESHOLD = 5.0         # Stage 2 provisional pass, deliberately conservative

# STRUCTURAL constants.  These are ratios / tolerances, not physical scales.
# None of them carries a unit; none of them encodes a Z step, a frame rate or a
# motion magnitude.  Every one of them is printed in the parameters report.
STAGE2_WINDOW_TRACK_FRACTION = 0.25   # Stage 2 window = this fraction of the MEASURED median track length
DEFAULT_NOISE_MARGIN_FACTOR = 2.0     # Stage 3d "stated factor" k, user-overridable: residual noise must be
                                      # this many times smaller than the single-frame motion scale
ALPHA_SEARCH_MIN = 0.05               # anomalous exponent search bounds. Hitting a bound is treated as
ALPHA_SEARCH_MAX = 2.00               # non-convergence, not as a result.
ALPHA_SEARCH_STEP = 0.005
ALPHA_WARN_DEVIATION = 0.20           # |alpha - 1| above this: the discarded linear model would have misled
SIGMA_ESTIMATOR_DISAGREE_RATIO = 1.5  # fitted vs covariance sigma differing by more than this factor is material
SIGMA_STABILITY_TOL = 0.10            # fitted sigma is "stable" while its relative spread over a run of
                                      # consecutive fit ranges stays within this
SIGMA_STABILITY_MIN_RUN = 3
ALPHA_CORRECTION_WARN_RATIO = 1.5     # the 1/alpha correction changing the window requirement by more than
                                      # this factor means alpha materially drives the window on this dataset           # a plateau needs at least this many consecutive ranges to be one
FITRANGE_STABLE_RATIO = 2.0           # max/min smoothing window across fit ranges below this = "largely stable"
FITRANGE_IMPROVEMENT_FACTOR = 0.5     # anomalous spread <= this x linear spread = "reduced but not removed"
MSD_FIT_REL_RESID_TOL = 0.10          # MSD fit range extends while RMS residual / mean(MSD) stays below this
MSD_MIN_FIT_LAGS = 5                  # the model has THREE free parameters (2*sigma^2, Gamma, alpha), so it is
                                      # not identifiable from 3 points; 5 lags leaves 2 degrees of freedom
MSD_MIN_PAIR_FRACTION = 0.10          # a lag is usable while it retains this fraction of the lag-1 pair count
CONFINEMENT_RISE_TOL = 0.05           # MSD has "ceased to rise" at lag L if no later lag exceeds MSD(L) by more than this
CONFINEMENT_MIN_SUSTAIN_FRACTION = 0.25  # ... asserted over a tail at least this fraction of the usable lag range,
CONFINEMENT_MIN_SUSTAIN = 3              #     and never over fewer than this many lags
MIN_TRACKS_FOR_MSD = 5                # fewer tracks than this -> MSD fit is not stable
MIN_PAIRS_AT_MAX_FIT_LAG = 100        # fewer displacement pairs than this at the top fit lag -> not stable
MIN_HAMPEL_WINDOW = 3                 # a median/MAD needs at least 3 points
OUTLIER_RATE_WARN_FRACTION = 0.05     # outlier rate above this is a data-quality problem, not a filtering step
SIGMA_RANGE_WARN_FRACTION = 0.10      # sigma above this fraction of the observed Z range -> noise-dominated
CROSS_METHOD_THRESHOLD_MULTIPLES = (1.0, 5.0, 25.0)   # in units of the supplied --z-step
CROSS_METHOD_SCORE_MULTIPLE = 5.0     # which of the above is used for the consensus score
LATTICE_MULTIPLE_FRACTION = 0.99      # a spacing g explains the data if this fraction of distinct Z are multiples of g
LATTICE_MIN_OCCUPANCY = 0.05          # ... and the lattice slots are at least this densely occupied
LATTICE_ATOL = 1e-6                   # absolute tolerance when testing "is a multiple of"
Z_STEP_EQUALITY_RTOL = 1e-6           # --z-step matches the lattice-reference spacing g when
                                      # |z_step - g| <= this fraction of z_step
Z_STEP_MULTIPLE_RTOL = 1e-6           # a detected spacing counts as an exact submultiple of --z-step when
                                      # |z_step - round(z_step/g)*g| <= this fraction of z_step.
                                      # INFORMATIONAL ONLY -- see stage1_zstep for why this is not the check.
TRANSFER_PROBE_WINDOWS = (3, 5, 7, 9, 11, 15, 21)  # windows at which the moving-average transfer
                                      # functions are measured on each run
TRANSFER_PROBE_SEED = 20240917        # fixed, so the measurement is reproducible run to run
ALPHA_BOOTSTRAP_REPLICATES = 200      # track-level bootstrap replicates for the alpha interval
ALPHA_BOOTSTRAP_SEED = 20240918
ALPHA_CI_PERCENTILES = (2.5, 97.5)    # a 95% interval
SENSITIVITY_BRIDGE_POINTS = 8         # extra sampled windows, LOG-spaced, when the chosen window lies beyond the
                                      # standard range, so no plotted segment spans unmeasured ground
# derivation_note severity ranking, most serious first. Entries are ordered by what
# they cost a reader who acts on the file: output that should not be used at all,
# then anything that scales every value in it, then caveats on the derived numbers,
# then data-quality notes. Codes absent from this ranking sort after it,
# alphabetically, so a check added later still reaches the CSV.
NOTE_SEVERITY_ORDER = (
    "DO_NOT_USE:flagged-inconsistent",
    "Z_STEP_MISMATCH",
    "Z_STEP_REFERENCE_NOT_LATTICE",
    "Z_STEP_UNVERIFIED",
    "WINDOW_NOT_DETERMINED",
    "HIGH_OUTLIER_RATE",
    "NOISE_DOMINATED",
    "SIGMA_UNRESOLVABLE",
    "SIGMA_ESTIMATORS_DISAGREE",
    "ALPHA_DRIVES_WINDOW",
    "ANOMALOUS_DIFFUSION",
    "CONFINEMENT_UNBOUNDED",
    "HAMPEL_WINDOW_SPANS_TRACK",
    "TOO_FEW_TRACKS",
    "TOO_FEW_PAIRS_FOR_MSD",
    "NAN_Z_PRESENT",
)
# Warnings about the run as a whole rather than one method. They apply to every
# output file, so they reach every file's note.
RUN_LEVEL_WARNING_CODES = frozenset({
    "Z_STEP_MISMATCH", "Z_STEP_REFERENCE_NOT_LATTICE", "Z_STEP_UNVERIFIED",
})
PER_TRACK_OUTLIER_NAME_RATE = 0.10    # per-track outlier rate above which a track is named individually
SENSITIVITY_MAX_WINDOW = 51           # hard cap on the sensitivity-table window range
SENSITIVITY_MIN_MAX_WINDOW = 11       # the sensitivity table always spans at least this far


class DerivationError(Exception):
    """A required parameter could not be derived from the data."""


class FatalDataError(Exception):
    """The inputs violate an assumption that the tool refuses to work around."""


class MethodFailure(Exception):
    """
    One method cannot be processed, but the rest of the run can continue.

    Unlike DerivationError, which aborts the whole run, this is recorded against
    the affected method: no smoothed output is written for it and the run exits
    non-zero, while every other method processes normally.
    """


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
class Report:
    """Collects the parameters report; echoes everything to stdout as it goes."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.warnings: list[str] = []
        self.failures: list[str] = []

    def line(self, text: str = "") -> None:
        self.lines.append(text)
        print(text)

    def rule(self, char: str = "-", width: int = 78) -> None:
        self.line(char * width)

    def section(self, title: str) -> None:
        self.line()
        self.rule("=")
        self.line(title)
        self.rule("=")

    def sub(self, title: str) -> None:
        self.line()
        self.line(title)
        self.rule("-")

    def warn(self, code: str, text: str) -> None:
        msg = f"[WARNING: {code}] {text}"
        self.warnings.append(msg)
        self.line(msg)

    def fail(self, code: str, text: str) -> None:
        """Record a per-method failure. Not a warning: no output was produced."""
        self.failures.append(f"[FAILED: {code}] {text}")

    def write(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(self.lines) + "\n")


# ---------------------------------------------------------------------------
# Small numeric helpers
# ---------------------------------------------------------------------------
def next_odd_at_least(x: float) -> int:
    """Smallest odd integer >= x (and >= 1)."""
    w = int(math.ceil(x - 1e-12))
    if w < 1:
        w = 1
    if w % 2 == 0:
        w += 1
    return w


def prev_odd_at_most(x: float) -> int:
    """Largest odd integer <= x (and >= 1)."""
    w = int(math.floor(x + 1e-12))
    if w < 1:
        return 1
    if w % 2 == 0:
        w -= 1
    return max(w, 1)


def track_slices(track_ids: np.ndarray) -> list[tuple[int, int]]:
    """Contiguous [start, stop) slices, one per track, for an array sorted by track."""
    if track_ids.size == 0:
        return []
    boundaries = np.flatnonzero(track_ids[1:] != track_ids[:-1]) + 1
    starts = np.concatenate(([0], boundaries))
    stops = np.concatenate((boundaries, [track_ids.size]))
    return list(zip(starts.tolist(), stops.tolist()))


def window_bounds(frames: np.ndarray, half: int) -> tuple[np.ndarray, np.ndarray]:
    """
    Row-index bounds of the gap-aware window for every point.

    The window of a point at frame f is the set of rows whose FRAME lies in
    [f - half, f + half].  Because frames are sorted within a track, that set is
    a contiguous row range -- but its size varies with the local frame gaps,
    which is exactly the gap-awareness required.
    """
    lo = np.searchsorted(frames, frames - half, side="left")
    hi = np.searchsorted(frames, frames + half, side="right")
    return lo, hi


def hampel_flags(frames: np.ndarray, z: np.ndarray, window: int,
                 threshold: float, mad_floor: float) -> np.ndarray:
    """
    Gap-aware Hampel filter over a single track.

    A point is flagged when |z - median(window)| > threshold * MAD(window),
    with MAD scaled to a Gaussian sigma estimate and floored at mad_floor.
    """
    n = z.size
    flags = np.zeros(n, dtype=bool)
    if n == 0 or window < MIN_HAMPEL_WINDOW:
        return flags
    half = window // 2
    lo, hi = window_bounds(frames, half)
    valid = ~np.isnan(z)
    for i in range(n):
        if not valid[i]:
            continue
        seg = z[lo[i]:hi[i]]
        seg = seg[~np.isnan(seg)]
        if seg.size < 3:
            continue
        med = np.median(seg)
        mad = 1.4826 * np.median(np.abs(seg - med))
        if mad < mad_floor:
            mad = mad_floor
        if abs(z[i] - med) > threshold * mad:
            flags[i] = True
    return flags


def gap_aware_moving_average(frames: np.ndarray, z: np.ndarray, window: int) -> np.ndarray:
    """
    Centred moving average whose window spans FRAME numbers, not rows.

    Points whose own Z is missing (absent or rejected) get NaN: computing a value
    there would be imputation, which is deliberately not done.
    """
    n = z.size
    out = np.full(n, np.nan)
    if n == 0:
        return out
    if window <= 1:
        return z.copy()
    half = window // 2
    lo, hi = window_bounds(frames, half)
    valid = ~np.isnan(z)
    filled = np.where(valid, z, 0.0)
    csum = np.concatenate(([0.0], np.cumsum(filled)))
    ccnt = np.concatenate(([0], np.cumsum(valid.astype(np.int64))))
    total = csum[hi] - csum[lo]
    count = ccnt[hi] - ccnt[lo]
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(count > 0, total / np.maximum(count, 1), np.nan)
    out[~valid] = np.nan
    return out


def detect_lattice_spacing(z: np.ndarray) -> Optional[float]:
    """
    Smallest consistent spacing between distinct observed Z values.

    A candidate spacing g is accepted when (a) at least LATTICE_MULTIPLE_FRACTION
    of the distinct Z values are integer multiples of g, and (b) the resulting
    lattice slots are at least LATTICE_MIN_OCCUPANCY occupied.  Test (b) is what
    stops the file's decimal print precision (e.g. 1e-4) being mistaken for a
    physical Z step in continuously valued data.
    """
    finite = z[np.isfinite(z)]
    if finite.size < 2:
        return None
    distinct = np.unique(np.round(finite, 9))
    if distinct.size < 2:
        return None
    diffs = np.diff(distinct)
    diffs = diffs[diffs > 1e-9]
    if diffs.size == 0:
        return None
    span = float(distinct[-1] - distinct[0])
    for g in np.unique(np.round(diffs, 9))[:50]:
        g = float(g)
        if g <= 0:
            continue
        ratio = distinct / g
        residual = np.abs(ratio - np.round(ratio)) * g
        if float(np.mean(residual <= LATTICE_ATOL)) < LATTICE_MULTIPLE_FRACTION:
            continue
        slots = span / g + 1.0
        if slots <= 0:
            continue
        if distinct.size / slots < LATTICE_MIN_OCCUPANCY:
            continue
        return g
    return None


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------
@dataclass
class MethodFile:
    name: str
    path: str
    raw_text: pd.DataFrame          # original columns, verbatim strings
    order: np.ndarray               # row order that sorts by (Track_ID, Frame)
    inverse: np.ndarray             # maps sorted position -> original row
    track_id: np.ndarray            # sorted
    frame: np.ndarray               # sorted
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray                   # sorted, float, NaN for blank
    slices: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class MSDResult:
    lags: np.ndarray
    msd: np.ndarray                 # indexed by lag (index 0 unused)
    pairs: np.ndarray               # indexed by lag
    max_usable_lag: int
    fit_lags: int
    intercept: float                # A = 2*sigma^2
    gamma: float                    # transport coefficient of tau^alpha
    alpha: float                    # anomalous exponent
    rel_residual: float
    sigma: float
    sigma_resolvable: bool
    alpha_no_rejection: Optional[float]   # same fit on the UNCLEANED MSD, over ITS own plateau
    alpha_no_rejection_range: Optional[int]
    alpha_no_rejection_reason: Optional[str]
    confinement_lag: Optional[int]


@dataclass
class Derived:
    smoothing_window: int
    hampel_window: int
    smoothing_required_raw: float
    smoothing_required_uncorrected: float
    crossover_lag: float
    confinement_cap: Optional[int]
    hampel_clamped: bool
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Loading and Stage 1
# ---------------------------------------------------------------------------
REQUIRED_COLUMNS = ["Track_ID", "Frame", "X", "Y", "Z"]


def load_method(path: str) -> MethodFile:
    raw_text = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [c for c in REQUIRED_COLUMNS if c not in raw_text.columns]
    if missing:
        raise FatalDataError(
            f"{os.path.basename(path)}: missing required column(s) {missing}. "
            f"Found columns: {list(raw_text.columns)}"
        )

    numeric = pd.read_csv(path)
    track_id = numeric["Track_ID"].to_numpy()
    frame = numeric["Frame"].to_numpy()
    if not np.issubdtype(frame.dtype, np.number):
        raise FatalDataError(f"{os.path.basename(path)}: Frame column is not numeric.")
    frame = frame.astype(np.int64)
    x = pd.to_numeric(numeric["X"], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(numeric["Y"], errors="coerce").to_numpy(dtype=float)
    z = pd.to_numeric(numeric["Z"], errors="coerce").to_numpy(dtype=float)

    order = np.lexsort((frame, track_id))
    inverse = np.empty_like(order)
    inverse[order] = np.arange(order.size)

    mf = MethodFile(
        name=os.path.basename(path),
        path=path,
        raw_text=raw_text,
        order=order,
        inverse=inverse,
        track_id=track_id[order],
        frame=frame[order],
        x=x[order],
        y=y[order],
        z=z[order],
    )
    mf.slices = track_slices(mf.track_id)

    for start, stop in mf.slices:
        seg = mf.frame[start:stop]
        if np.any(np.diff(seg) == 0):
            tid = mf.track_id[start]
            raise FatalDataError(
                f"{mf.name}: track {tid} contains duplicate (Track_ID, Frame) rows. "
                f"Refusing to guess which row is authoritative."
            )
    return mf


def stage1_consistency(methods: list[MethodFile], rep: Report) -> None:
    rep.sub("1a. Cross-file consistency of Track_ID, Frame, X, Y")
    ref = methods[0]
    rep.line(f"Reference file: {ref.name} ({ref.track_id.size} rows)")
    for mf in methods[1:]:
        problems = []
        if mf.track_id.size != ref.track_id.size:
            problems.append(f"row count {mf.track_id.size} != {ref.track_id.size}")
        else:
            if not np.array_equal(mf.track_id, ref.track_id):
                problems.append("Track_ID differs")
            if not np.array_equal(mf.frame, ref.frame):
                problems.append("Frame differs")
            if not np.allclose(mf.x, ref.x, rtol=0, atol=1e-9, equal_nan=True):
                problems.append("X differs")
            if not np.allclose(mf.y, ref.y, rtol=0, atol=1e-9, equal_nan=True):
                problems.append("Y differs")
        if problems:
            raise FatalDataError(
                f"{mf.name} is not row-for-row comparable with {ref.name}: "
                + "; ".join(problems)
                + ". The files must describe the same tracks at the same frames."
            )
        rep.line(f"  {mf.name}: identical Track_ID / Frame / X / Y  [OK]")
    if len(methods) == 1:
        rep.line("  (single input file; nothing to cross-check)")


def stage1_zstep(methods: list[MethodFile], z_step: float,
                 lattice_reference_index: Optional[int],
                 lattice_reference_label: Optional[str],
                 rep: Report) -> tuple[dict[str, Optional[float]], str]:
    """
    Cross-check the supplied Z step against the one file that can answer the
    question, and report every other file's granularity as information.

    Only a single-pixel sampling method returns a raw lattice value, so only such
    a file has the true Z step as its granularity. Every aggregate method is
    strictly finer: a median returns either a sampled value or the mean of the two
    middle sampled values, so it lands at worst on half-steps regardless of window
    size, and a mean of N values lands at roughly step/N. An aggregate file
    therefore bounds the Z step from below and never identifies it, and the
    coarsest granularity across files is not a safe proxy either.

    That is why the check is EQUALITY against a user-named single-pixel file, and
    why there is no check at all when no such file is named. Testing whether the
    supplied step is an integer multiple of a detected spacing -- the previous
    version of this check -- silently accepts a step that is too large by a whole
    factor: with a true lattice of 2.0, a supplied 4.0 reads as "2 x detected,
    exact" while every value in the output is double what it should be. That is
    precisely the error this check exists to catch.
    """
    rep.sub("1b. Z-step cross-check")
    rep.line(f"Supplied --z-step : {z_step:.6g}")
    rep.line("Detected spacing is the smallest value g such that >= "
             f"{LATTICE_MULTIPLE_FRACTION:.0%} of distinct Z values are multiples of g")
    rep.line(f"and the lattice slots are at least {LATTICE_MIN_OCCUPANCY:.0%} occupied.")
    rep.line("")

    detected: dict[str, Optional[float]] = {}
    # Parallel to `methods`. The dict is keyed on basename, which two inputs in
    # different directories can share; the reference is resolved positionally so it
    # can never pick up a different file's lattice.
    spacings: list[Optional[float]] = []
    rows: list[tuple[str, str, str]] = []
    for mf in methods:
        g = detect_lattice_spacing(mf.z)
        detected[mf.name] = g
        spacings.append(g)
        if g is None:
            rows.append((mf.name, "none (continuously valued)",
                         "no lattice: consistent with a mean over many samples"))
            continue
        multiple = z_step / g
        nearest = round(multiple)
        exact = nearest >= 1 and abs(z_step - nearest * g) <= Z_STEP_MULTIPLE_RTOL * z_step
        if exact and nearest == 1:
            rows.append((mf.name, f"{g:.6g}", "= supplied step (raw lattice granularity)"))
        elif exact:
            rows.append((mf.name, f"{g:.6g}", f"= supplied step / {nearest}"))
        else:
            rows.append((mf.name, f"{g:.6g}",
                         f"= supplied step / {multiple:.6g} (not a submultiple)"))

    width = max(len(r[0]) for r in rows)
    rep.line("Per-file granularity. This is INFORMATION, not a check: granularity is "
             "diagnostic of")
    rep.line("the sampling method, not a fault. No warning is raised from this table.")
    rep.line("")
    rep.line(f"  {'file':{width}s} {'detected spacing':>26s}   relationship to --z-step")
    for name, shown, rel in rows:
        rep.line(f"  {name:{width}s} {shown:>26s}   {rel}")
    rep.line("")

    if lattice_reference_index is None:
        rep.line("No --lattice-reference was supplied, so the Z step has NOT been verified "
                 "against the data.")
        rep.warn(
            "Z_STEP_UNVERIFIED",
            f"No --lattice-reference was given, so the supplied --z-step {z_step:.6g} could "
            f"not be verified against the data at all. Only a single-pixel sampling file "
            f"carries the raw Z lattice; every aggregate method is finer by construction, so "
            f"no substitute check has been performed and no proxy has been used. YOU must "
            f"confirm that {z_step:.6g} matches the acquisition Z spacing. A wrong value "
            f"shifts every value in the output by a constant factor while leaving the file "
            f"looking entirely normal -- correct row count, plausible numbers, no error "
            f"anywhere.",
        )
        return detected, "NOT VERIFIED (no --lattice-reference)"

    g = spacings[lattice_reference_index]
    ref_name = methods[lattice_reference_index].path
    rep.line(f"Lattice reference : {lattice_reference_label} (named by --lattice-reference as "
             f"single-pixel sampling)")
    rep.line(f"                    resolved to input #{lattice_reference_index + 1}: "
             f"{os.path.abspath(ref_name)}")
    if g is None:
        rep.warn(
            "Z_STEP_REFERENCE_NOT_LATTICE",
            f"{ref_name} was named as the single-pixel lattice reference, but its Z "
            f"values do not lie on any single consistent lattice, which single-pixel output "
            f"must. The file does not look like single-pixel sampling and the Z-step check is "
            f"therefore UNAVAILABLE: the supplied --z-step {z_step:.6g} has not been verified "
            f"against anything. Check that the right file was named. YOU must confirm that "
            f"{z_step:.6g} matches the acquisition Z spacing; a wrong value shifts every "
            f"value in the output while leaving the file looking entirely normal.",
        )
        return detected, "UNAVAILABLE (named reference is not on a lattice)"

    if abs(g - z_step) <= Z_STEP_EQUALITY_RTOL * z_step:
        rep.line(f"  Z step VERIFIED: the reference lattice spacing is {g:.6g}, equal to the "
                 f"supplied {z_step:.6g}")
        rep.line(f"  within a relative tolerance of {Z_STEP_EQUALITY_RTOL:g}.")
        status = f"VERIFIED against {os.path.basename(ref_name)} (spacing {g:.6g})"
    else:
        rep.warn(
            "Z_STEP_MISMATCH",
            f"{ref_name} is the named single-pixel lattice reference. Its lattice "
            f"spacing is {g:.6g}, but --z-step was given as {z_step:.6g} "
            f"(ratio {z_step / g:.6g}, relative tolerance {Z_STEP_EQUALITY_RTOL:g}). A "
            f"single-pixel file returns raw lattice values, so its spacing IS the Z step: "
            f"these two numbers must be equal and they are not. Every value in the output is "
            f"conditioned on the supplied value, which is what gets used. This disagreement "
            f"is reported, not resolved.",
        )
        status = (f"MISMATCH: reference {os.path.basename(ref_name)} spacing {g:.6g} "
                  f"vs supplied {z_step:.6g}")
    return detected, status


def stage1_cross_method(methods: list[MethodFile], z_step: float, mad_threshold: float,
                        rep: Report) -> set:
    rep.sub("1c. Pairwise cross-method comparison and consensus check")
    if len(methods) < 2:
        rep.line("  Only one input file; no pairwise comparison possible.")
        return set()

    thresholds = [m * z_step for m in CROSS_METHOD_THRESHOLD_MULTIPLES]
    zs = np.column_stack([mf.z for mf in methods])
    names = [mf.name for mf in methods]
    n_rows = zs.shape[0]

    rep.line(f"Thresholds (multiples of the supplied --z-step {z_step:.6g}): "
             + ", ".join(f"{m:g}x = {t:.6g}" for m, t in
                         zip(CROSS_METHOD_THRESHOLD_MULTIPLES, thresholds)))
    rep.line("")
    header = f"  {'method A':26s} {'method B':26s} {'compared':>8s}"
    for m in CROSS_METHOD_THRESHOLD_MULTIPLES:
        header += f" {'>' + format(m, 'g') + 'x':>9s}"
    header += f" {'median|dZ|':>11s}"
    rep.line(header)
    for i in range(len(methods)):
        for j in range(i + 1, len(methods)):
            diff = np.abs(zs[:, i] - zs[:, j])
            usable = np.isfinite(diff)
            n_cmp = int(usable.sum())
            row = f"  {names[i][:26]:26s} {names[j][:26]:26s} {n_cmp:8d}"
            for t in thresholds:
                row += f" {int(np.sum(diff[usable] > t)):9d}"
            med = float(np.median(diff[usable])) if n_cmp else float("nan")
            row += f" {med:11.4g}"
            rep.line(row)

    if len(methods) < 3:
        rep.line("")
        rep.line("  Fewer than 3 methods: no consensus can be formed, "
                 "so no method can be identified as disagreeing with one.")
        return set()

    score_threshold = CROSS_METHOD_SCORE_MULTIPLE * z_step
    rep.line("")
    rep.line(f"Consensus score = fraction of rows where |Z_method - median(Z of the OTHER "
             f"methods)| > {CROSS_METHOD_SCORE_MULTIPLE:g}x z-step = {score_threshold:.6g}.")
    rep.line(f"A method is flagged by a Hampel test across those scores at "
             f"{mad_threshold:g} MAD (MAD floored at 1 row = {1.0/max(n_rows,1):.3g}).")
    rep.line("")

    scores = np.zeros(len(methods))
    counts = np.zeros(len(methods), dtype=int)
    med_dev = np.zeros(len(methods))
    for k in range(len(methods)):
        others = np.delete(zs, k, axis=1)
        with np.errstate(invalid="ignore"):
            consensus = np.nanmedian(others, axis=1)
        dev = np.abs(zs[:, k] - consensus)
        usable = np.isfinite(dev)
        counts[k] = int(np.sum(dev[usable] > score_threshold))
        scores[k] = counts[k] / max(int(usable.sum()), 1)
        med_dev[k] = float(np.median(dev[usable])) if usable.any() else float("nan")

    rep.line(f"  {'method':30s} {'median|Z-consensus|':>20s} {'points over':>12s} {'score':>9s}")
    for k, nm in enumerate(names):
        rep.line(f"  {nm[:30]:30s} {med_dev[k]:20.4g} {counts[k]:12d} {scores[k]:9.4f}")

    centre = float(np.median(scores))
    mad = 1.4826 * float(np.median(np.abs(scores - centre)))
    floor = 1.0 / max(n_rows, 1)
    mad_used = max(mad, floor)
    rep.line("")
    rep.line(f"  score median = {centre:.4f}; score MAD = {mad:.4f} "
             f"(floored to {mad_used:.4f}); flag if |score - median| > "
             f"{mad_threshold:g} x MAD = {mad_threshold * mad_used:.4f}")

    flagged = [k for k in range(len(methods))
               if abs(scores[k] - centre) > mad_threshold * mad_used]
    if not flagged:
        rep.line("  No method disagrees with the consensus of the others.")
        return set()
    for k in flagged:
        rep.warn(
            "METHOD_DISAGREES_WITH_CONSENSUS",
            f"{names[k]} disagrees with the consensus of the other methods: "
            f"{counts[k]} of {n_rows} points ({scores[k]:.2%}) differ from the median of "
            f"the other methods by more than {score_threshold:.6g} "
            f"(median deviation {med_dev[k]:.4g}). A sampling window that straddles a "
            f"height discontinuity produces confidently wrong values; this is that check.",
        )
    return {names[k] for k in flagged}


def stage1_describe(mf: MethodFile, rep: Report) -> dict:
    n_rows = mf.track_id.size
    n_tracks = len(mf.slices)
    n_nan = int(np.sum(~np.isfinite(mf.z)))
    finite = mf.z[np.isfinite(mf.z)]
    lengths = np.array([stop - start for start, stop in mf.slices], dtype=float)
    gaps = []
    spans = []
    for start, stop in mf.slices:
        fr = mf.frame[start:stop]
        spans.append(int(fr[-1] - fr[0] + 1))
        if stop - start > 1:
            gaps.append(np.diff(fr))
    gap_arr = np.concatenate(gaps) if gaps else np.array([], dtype=np.int64)
    spans = np.array(spans, dtype=float)

    rep.line(f"  rows                : {n_rows}")
    rep.line(f"  tracks              : {n_tracks}")
    rep.line(f"  NaN / blank Z       : {n_nan} ({100.0 * n_nan / max(n_rows, 1):.3f}%)")
    if finite.size:
        rep.line(f"  Z range             : {finite.min():.6g} .. {finite.max():.6g} "
                 f"(span {finite.max() - finite.min():.6g})")
        rep.line(f"  Z distinct values   : {np.unique(np.round(finite, 9)).size}")
    else:
        rep.line("  Z range             : (no finite Z values)")
    if lengths.size:
        q = np.percentile(lengths, [0, 25, 50, 75, 100])
        rep.line(f"  track length (pts)  : min {q[0]:.0f}  q25 {q[1]:.0f}  median {q[2]:.0f}  "
                 f"q75 {q[3]:.0f}  max {q[4]:.0f}  mean {lengths.mean():.1f}")
        rep.line(f"  track span (frames) : min {spans.min():.0f}  median "
                 f"{np.median(spans):.0f}  max {spans.max():.0f}")
    if gap_arr.size:
        n_gap = int(np.sum(gap_arr > 1))
        rep.line(f"  frame gaps          : {gap_arr.size} intervals, {n_gap} "
                 f"({100.0 * n_gap / gap_arr.size:.2f}%) larger than 1 frame; "
                 f"max gap {gap_arr.max()} frames")
        vals, cnts = np.unique(gap_arr, return_counts=True)
        top = ", ".join(f"{v}:{c}" for v, c in zip(vals[:8], cnts[:8]))
        rep.line(f"  gap histogram (gap:count, first 8): {top}")
    else:
        rep.line("  frame gaps          : (no within-track intervals)")

    return {
        "n_rows": n_rows,
        "n_tracks": n_tracks,
        "n_nan": n_nan,
        "median_track_length": float(np.median(lengths)) if lengths.size else 0.0,
        "median_span": float(np.median(spans)) if spans.size else 0.0,
        "max_span": float(spans.max()) if spans.size else 0.0,
        "z_range": float(finite.max() - finite.min()) if finite.size else float("nan"),
    }


# ---------------------------------------------------------------------------
# Stage 2 -- strict provisional pass
# ---------------------------------------------------------------------------
def run_hampel(mf: MethodFile, z: np.ndarray, window: int, threshold: float,
               mad_floor: float) -> np.ndarray:
    flags = np.zeros(z.size, dtype=bool)
    for start, stop in mf.slices:
        flags[start:stop] = hampel_flags(
            mf.frame[start:stop], z[start:stop], window, threshold, mad_floor
        )
    return flags


# ---------------------------------------------------------------------------
# Stage 3 -- timescale measurement
# ---------------------------------------------------------------------------
def pooled_msd(mf: MethodFile, z: np.ndarray, max_lag: int) -> tuple[np.ndarray, np.ndarray]:
    ssum = np.zeros(max_lag + 1, dtype=float)
    scnt = np.zeros(max_lag + 1, dtype=np.int64)
    for start, stop in mf.slices:
        fr = mf.frame[start:stop]
        zz = z[start:stop]
        lo = int(fr[0])
        span = int(fr[-1] - lo + 1)
        arr = np.full(span, np.nan)
        arr[(fr - lo).astype(np.int64)] = zz
        upper = min(max_lag, span - 1)
        for lag in range(1, upper + 1):
            d = arr[lag:] - arr[:-lag]
            m = np.isfinite(d)
            if not m.any():
                continue
            dv = d[m]
            ssum[lag] += float(np.dot(dv, dv))
            scnt[lag] += int(m.sum())
    with np.errstate(invalid="ignore", divide="ignore"):
        msd = np.where(scnt > 0, ssum / np.maximum(scnt, 1), np.nan)
    return msd, scnt


def fit_anomalous(lags: np.ndarray, y: np.ndarray) -> Optional[tuple[float, float, float, float]]:
    """
    Fit MSD(tau) = 2*sigma^2 + Gamma * tau^alpha, returning (A, Gamma, alpha, rel_resid).

    For any fixed alpha the model is LINEAR in A and Gamma, so the fit is an exact
    least-squares solution at each alpha and only alpha needs searching. The search
    is a dense grid evaluated in one vectorised pass, which has no starting point,
    no convergence criterion and no local minima to fall into.

    Returns None when the fit does not converge: a degenerate design matrix at every
    alpha, or a best alpha sitting on a search bound (which means the true optimum is
    outside the searched range and the returned value would be an artifact of the
    bound). The caller must report that rather than substitute anything.
    """
    alphas = np.arange(ALPHA_SEARCH_MIN, ALPHA_SEARCH_MAX + 1e-9, ALPHA_SEARCH_STEP)
    n = lags.size
    if n < 3:
        return None
    basis = lags[None, :] ** alphas[:, None]              # (n_alpha, n_lags)
    s_b = basis.sum(axis=1)
    s_bb = (basis * basis).sum(axis=1)
    s_y = float(y.sum())
    s_by = (basis * y).sum(axis=1)
    det = n * s_bb - s_b * s_b
    ok = np.abs(det) > 1e-12
    safe = np.where(ok, det, 1.0)
    a_hat = (s_bb * s_y - s_b * s_by) / safe
    g_hat = (n * s_by - s_b * s_y) / safe
    pred = a_hat[:, None] + g_hat[:, None] * basis
    sse = ((y[None, :] - pred) ** 2).sum(axis=1)
    sse = np.where(ok, sse, np.inf)
    best = int(np.argmin(sse))
    if not np.isfinite(sse[best]):
        return None
    if best == 0 or best == alphas.size - 1:
        return None
    denom = float(np.mean(y))
    if denom <= 0:
        return None
    rel = float(np.sqrt(sse[best] / n) / denom)
    return float(a_hat[best]), float(g_hat[best]), float(alphas[best]), rel


def fit_linear_for_comparison(lags: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    """The discarded MSD(tau) = 2*sigma^2 + D*tau model, kept ONLY to show, in the
    fit-range sensitivity table, what it would have produced. Nothing is derived
    from it."""
    slope, intercept = np.polyfit(lags, y, 1)
    resid = y - (slope * lags + intercept)
    denom = float(np.mean(y))
    rel = float(np.sqrt(np.mean(resid ** 2)) / denom) if denom > 0 else float("nan")
    return float(intercept), float(slope), rel


def smoothing_window_requirement(intercept: float, gamma: float, k: float,
                                 alpha: float) -> tuple[float, float]:
    """
    The window at which the residual noise contribution falls below the motion
    contribution by the factor f = 1/k^2, at lag 1.

    Both contributions are attenuated by the moving average, and NOT at the same
    rate (both exponents are re-measured on every run):

        noise (W)  = 2*sigma^2 * W^-2
        motion(W)  = Gamma     * W^(alpha-2)
        ratio (W)  = 2*sigma^2 / (Gamma * W^alpha)

    Requiring ratio <= 1/k^2 gives  W >= (2*k^2*sigma^2/Gamma)^(1/alpha).

    The exponent 1/alpha is the correction. The formula this tool used previously,
    W >= 2*k^2*sigma^2/Gamma, is the alpha = 1 special case. On a genuinely
    subdiffusive or superdiffusive dataset it returns a systematically wrong window
    and nothing about the output would look wrong.

    Returns (corrected, uncorrected) so the size of the correction is always visible.
    """
    if gamma <= 0:
        return float("nan"), float("nan")
    uncorrected = 2.0 * (k ** 2) * max(intercept, 0.0) / 2.0 / gamma
    if uncorrected <= 0 or alpha <= 0:
        return uncorrected, uncorrected
    return uncorrected ** (1.0 / alpha), uncorrected


def covariance_sigma(mf: MethodFile, z: np.ndarray) -> dict:
    """
    Model-free localisation noise, independent of the MSD model entirely.

    Two successive displacements share an endpoint, so independent localisation
    noise on that shared point enters one displacement positively and the other
    negatively:

        Cov(delta_i, delta_i+1) = -sigma^2

    provided the genuine motion increments are uncorrelated. Nothing here assumes
    normal diffusion, a power law, or any fit range.

    Gap-aware: only triples of frames (f, f+1, f+2) all present and all finite are
    used, so a displacement never spans a frame gap and "successive" means
    genuinely successive.
    """
    d1_list, d2_list = [], []
    for start, stop in mf.slices:
        fr = mf.frame[start:stop]
        zz = z[start:stop]
        if fr.size < 3:
            continue
        step_ok = (fr[1:] - fr[:-1]) == 1
        for i in range(fr.size - 2):
            if not (step_ok[i] and step_ok[i + 1]):
                continue
            a, b, c = zz[i], zz[i + 1], zz[i + 2]
            if np.isfinite(a) and np.isfinite(b) and np.isfinite(c):
                d1_list.append(b - a)
                d2_list.append(c - b)
    n = len(d1_list)
    if n < 2:
        return {"n": n, "cov": float("nan"), "sigma": None}
    d1 = np.array(d1_list)
    d2 = np.array(d2_list)
    cov = float(np.mean((d1 - d1.mean()) * (d2 - d2.mean())))
    sigma = math.sqrt(-cov) if cov < 0 else None
    return {"n": n, "cov": cov, "sigma": sigma}


def bootstrap_alpha(mf: MethodFile, z: np.ndarray, fit_lags: int,
                    noise_margin: float) -> dict:
    """
    Uncertainty on the fitted alpha, and on the window it implies, by resampling
    TRACKS with replacement.

    Tracks are the independent units here: the MSD is pooled across them, while
    within a track the lags are strongly correlated and the residuals are not
    independent. That rules out a residual-based interval, and a profile likelihood
    would need a noise model for the MSD points that this correlation makes
    intractable. A track-level bootstrap needs no such model -- it resamples the
    thing that actually varies between hypothetical repeat experiments.

    Each track's contribution to the pooled sums is additive, so the per-track sums
    are computed once and a replicate is a sum over sampled tracks rather than a
    re-pass over the data.

    The FIT RANGE IS HELD FIXED at the range chosen for the point estimate. The
    interval is therefore conditional on that range; the separate dependence on
    where the fit stops is reported by the fit-range sensitivity table and is not
    folded in here.
    """
    n_tracks = len(mf.slices)
    if n_tracks < 3 or fit_lags < MSD_MIN_FIT_LAGS:
        return {}
    ss = np.zeros((n_tracks, fit_lags + 1))
    cn = np.zeros((n_tracks, fit_lags + 1))
    for t, (start, stop) in enumerate(mf.slices):
        fr = mf.frame[start:stop]
        lo = int(fr[0])
        arr = np.full(int(fr[-1] - lo + 1), np.nan)
        arr[(fr - lo).astype(np.int64)] = z[start:stop]
        for lag in range(1, min(fit_lags, arr.size - 1) + 1):
            d = arr[lag:] - arr[:-lag]
            m = np.isfinite(d)
            if m.any():
                dv = d[m]
                ss[t, lag] = float(np.dot(dv, dv))
                cn[t, lag] = int(m.sum())

    rng = np.random.default_rng(ALPHA_BOOTSTRAP_SEED)
    lags = np.arange(1, fit_lags + 1, dtype=float)
    alphas, wreqs = [], []
    n_unresolvable = 0
    for _ in range(ALPHA_BOOTSTRAP_REPLICATES):
        idx = rng.integers(0, n_tracks, n_tracks)
        s_sum = ss[idx].sum(axis=0)
        c_sum = cn[idx].sum(axis=0)
        if np.any(c_sum[1:] <= 0):
            continue
        msd_b = s_sum[1:] / c_sum[1:]
        fit = fit_anomalous(lags, msd_b)
        if fit is None:
            continue
        a_hat, g_hat, alpha_b, _ = fit
        alphas.append(alpha_b)
        if a_hat <= 0:
            n_unresolvable += 1
            wreqs.append(1.0)
            continue
        w, _unc = smoothing_window_requirement(a_hat, g_hat, noise_margin, alpha_b)
        wreqs.append(w if np.isfinite(w) else 1.0)
    if len(alphas) < 20:
        return {}
    lo_p, hi_p = ALPHA_CI_PERCENTILES
    a_lo, a_hi = np.percentile(alphas, [lo_p, hi_p])
    w_lo, w_hi = np.percentile(wreqs, [lo_p, hi_p])
    return {"n": len(alphas), "alpha_lo": float(a_lo), "alpha_hi": float(a_hi),
            "w_lo": float(w_lo), "w_hi": float(w_hi),
            "window_lo": next_odd_at_least(float(w_lo)),
            "window_hi": next_odd_at_least(float(w_hi)),
            "n_unresolvable": n_unresolvable}


def sigma_by_range(fits: dict) -> dict:
    """sqrt(A/2) per fit range, or None where the intercept is not positive."""
    return {L: (math.sqrt(f[0] / 2.0) if f[0] > 0 else None) for L, f in fits.items()}


def stable_plateau(fits: dict, sigmas: dict) -> tuple[list[int], Optional[int]]:
    """
    The first run of consecutive fit ranges over which the fitted sigma is stable.

    The plateau need not begin at the shortest admissible range -- the very shortest
    fits can be erratic. Every maximal stable run is found and the FIRST one long
    enough to count is taken, because sigma is a short-lag property and the earliest
    plateau is the one least contaminated by long-lag structure.

    Returns (plateau, cap). When no run is long enough, cap is None and the longest
    run found is returned so the caller can report how close it came.
    """
    candidates = sorted(fits)
    longest_seen: list[int] = []
    for i, start in enumerate(candidates):
        if sigmas[start] is None:
            continue
        run = [start]
        for L in candidates[i + 1:]:
            if sigmas[L] is None:
                break
            vals = [sigmas[x] for x in run + [L]]
            if (max(vals) / min(vals) - 1.0) > SIGMA_STABILITY_TOL:
                break
            run.append(L)
        if len(run) > len(longest_seen):
            longest_seen = run
        if len(run) >= SIGMA_STABILITY_MIN_RUN:
            return run, run[-1]
    return longest_seen, None


def measure_transfer_exponents(mf: MethodFile, alpha: float) -> dict:
    """
    Measure, on THIS dataset's own track and gap structure, how the gap-aware moving
    average attenuates the two components of MSD at lag 1.

    Synthetic series are laid over the real frames: uncorrelated noise, and a
    fractional Brownian motion with Hurst H = alpha/2 so that its MSD grows as
    tau^alpha, matching this method's fitted exponent. Both are smoothed at a range
    of windows and the lag-1 MSD is regressed on the window in log-log.

    Expected structurally: noise ~ W^-2 (successive windows overlap in W-1 of W
    points, so their difference is (1/W)(eps[t+1+h] - eps[t-h])), and motion ~
    W^(alpha-2) (the same difference spans W frames of genuine displacement, which
    accumulate as W^alpha). This function measures rather than assumes them.
    """
    h = min(max(alpha / 2.0, 0.05), 0.95)
    rng = np.random.default_rng(TRANSFER_PROBE_SEED)
    spans = [int(mf.frame[b - 1] - mf.frame[a] + 1) for a, b in mf.slices]
    if not spans:
        return {}
    n_max = max(spans)
    k = np.arange(n_max)
    acov = 0.5 * (np.abs(k - 1) ** (2 * h) - 2 * np.abs(k) ** (2 * h)
                  + np.abs(k + 1) ** (2 * h))
    cov = acov[np.abs(np.subtract.outer(k, k))]
    try:
        chol = np.linalg.cholesky(cov + np.eye(n_max) * 1e-9)
    except np.linalg.LinAlgError:
        return {}

    noise = rng.normal(0.0, 1.0, mf.z.size)
    walk = np.empty(mf.z.size)
    for (start, stop), span in zip(mf.slices, spans):
        fr = mf.frame[start:stop]
        inc = chol[:span, :span] @ rng.standard_normal(span)
        walk[start:stop] = np.cumsum(inc)[(fr - fr[0]).astype(np.int64)]

    def msd1_of(z):
        msd, _ = pooled_msd(mf, z, 1)
        return float(msd[1])

    ws = np.array([w for w in TRANSFER_PROBE_WINDOWS], dtype=float)
    y_n = np.array([msd1_of(gap_aware_moving_average_all(mf, noise, int(w))) for w in ws])
    y_m = np.array([msd1_of(gap_aware_moving_average_all(mf, walk, int(w))) for w in ws])
    if np.any(y_n <= 0) or np.any(y_m <= 0):
        return {}
    return {
        "noise_exp": float(np.polyfit(np.log(ws), np.log(y_n), 1)[0]),
        "motion_exp": float(np.polyfit(np.log(ws), np.log(y_m), 1)[0]),
        "noise_exp_expected": -2.0,
        "motion_exp_expected": alpha - 2.0,
        "windows": [int(w) for w in ws],
        "hurst": h,
    }


def alternative_window(sigma_cov: Optional[float], msd1: float,
                       noise_margin: float, alpha: float) -> Optional[dict]:
    """
    REPORT ONLY. An alternative smoothing window built from model-free quantities.

    Measured transfer functions of the gap-aware moving average at lag 1 -- verified
    numerically on this data's own track and gap structure, not assumed:

        noise  contribution:  2*sigma^2 / W^2      (measured exponent -1.93)
        motion contribution:  Gamma / W            (measured exponent -0.96)

    The noise does NOT simply divide by W. Successive windows overlap in W-1 of their
    W points, so their difference is (1/W)*(eps[t+1+h] - eps[t-h]) and its variance
    falls as 1/W^2. The motion falls only as 1/W, because the same difference spans
    W frames of genuine displacement.

    Requiring noise/motion <= f gives W >= 2*sigma^2 / (f*Gamma), and f is reported as
    1/k^2 so it is directly comparable with the k in use. Both sigma and Gamma come
    from measurement here: sigma from the covariance estimator, Gamma from
    MSD(1) - 2*sigma_cov^2. Neither depends on the MSD model or the fit range.
    """
    if sigma_cov is None or not np.isfinite(msd1):
        return None
    noise = 2.0 * sigma_cov ** 2
    gamma_meas = msd1 - noise
    if gamma_meas <= 0:
        return {"gamma_meas": gamma_meas, "w_req": None, "window": None,
                "f": 1.0 / noise_margin ** 2}
    f = 1.0 / noise_margin ** 2
    # ratio(W) = (2 sigma^2 / W^2) / (Gamma * W^(alpha-2)) = 2 sigma^2 / (Gamma * W^alpha)
    # ratio <= f  =>  W >= (2 sigma^2 / (f Gamma))^(1/alpha).
    # The exponent 1/alpha is NOT optional: at alpha = 1 it vanishes, but away from 1
    # it dominates. The formula currently in use omits it and is correct only at alpha = 1.
    base = noise / (f * gamma_meas)
    if base <= 0 or alpha <= 0:
        return {"gamma_meas": gamma_meas, "w_req": None, "window": None, "f": f}
    w_req = base ** (1.0 / alpha)
    return {"gamma_meas": gamma_meas, "w_req": w_req, "base": base,
            "window": next_odd_at_least(w_req), "f": f, "noise": noise,
            "w_req_uncorrected": base}


def describe_alpha(alpha: float) -> str:
    if abs(alpha - 1.0) <= ALPHA_WARN_DEVIATION:
        return "consistent with normal diffusion"
    if alpha < 1.0:
        return "SUBDIFFUSIVE"
    return "SUPERDIFFUSIVE / directed"


def fit_range_sensitivity(msd: np.ndarray, max_usable: int, chosen: int,
                          noise_margin: float, rep: Report) -> dict:
    """
    Both models fitted over several ranges, so the reader can see how much of the
    smoothing window is the data and how much is the choice of fit range.
    """
    span = max_usable - MSD_MIN_FIT_LAGS
    # Every range inside the cap, so the LIVE spread is measured on the ranges the
    # tool could actually have chosen, plus a spread of longer ranges so the
    # counterfactual "without the cap" spread is still visible.
    candidates = set(range(MSD_MIN_FIT_LAGS, chosen + 1)) | {MSD_MIN_FIT_LAGS,
                                                             max_usable, chosen}
    if span > 0:
        for frac in (0.25, 0.5, 0.75):
            candidates.add(int(round(MSD_MIN_FIT_LAGS + frac * span)))
    ranges = sorted(L for L in candidates if MSD_MIN_FIT_LAGS <= L <= max_usable)

    rep.line("  Fit-range sensitivity. The discarded linear model is shown ONLY for "
             "comparison;")
    rep.line("  nothing is derived from it. Ranges span the usable lag range at 0, 25, 50, "
             "75 and 100%,")
    rep.line("  plus the range actually chosen.")
    rep.line(f"    {'range':>8s} | {'lin 2sig^2':>10s} {'lin D':>9s} {'lin W':>6s} | "
             f"{'2sig^2':>10s} {'Gamma':>9s} {'alpha':>7s} {'W':>6s} {'relres':>7s}")
    lin_w, anom_w = [], []
    lin_w_capped, anom_w_capped = [], []
    for L in ranges:
        lags = np.arange(1, L + 1, dtype=float)
        y = msd[1:L + 1]
        li, ld, _ = fit_linear_for_comparison(lags, y)
        lw = next_odd_at_least(2.0 * noise_margin ** 2 * max(li, 0.0) / 2.0 / ld) if ld > 0 else 0
        fit = fit_anomalous(lags, y)
        mark = "  <-- in use" if L == chosen else ("  (within cap)" if L < chosen else "")
        if fit is None:
            rep.line(f"    1..{L:<5d} | {li:10.4g} {ld:9.4g} {lw:6d} | "
                     f"{'(anomalous fit did not converge)':>42s}{mark}")
            if ld > 0:
                lin_w.append(lw)
            continue
        a_hat, g_hat, alpha, rel = fit
        # each range's window uses THAT range's own fitted alpha, since the 1/alpha
        # correction is part of the requirement being compared
        aw = next_odd_at_least(
            smoothing_window_requirement(a_hat, g_hat, noise_margin, alpha)[0]
        ) if g_hat > 0 else 0
        rep.line(f"    1..{L:<5d} | {li:10.4g} {ld:9.4g} {lw:6d} | "
                 f"{a_hat:10.4g} {g_hat:9.4g} {alpha:7.4f} {aw:6d} {rel:7.4f}{mark}")
        if ld > 0:
            lin_w.append(lw)
            if L <= chosen:
                lin_w_capped.append(lw)
        if g_hat > 0:
            anom_w.append(aw)
            if L <= chosen:
                anom_w_capped.append(aw)

    def spread(vals: list[int]) -> Optional[float]:
        vals = [max(v, 1) for v in vals]
        if len(vals) < 2:
            return None
        return max(vals) / min(vals)

    lin_ratio, anom_ratio = spread(lin_w_capped), spread(anom_w_capped)
    lin_ratio_unc, anom_ratio_unc = spread(lin_w), spread(anom_w)
    rep.line("")
    if anom_w and min(anom_w) <= 1:
        rep.line(f"    NOTE: {sum(1 for v in anom_w if v <= 1)} of {len(anom_w)} fit ranges "
                 f"give a window of 1, i.e. no smoothing at all.")
        rep.line(f"    The max/min ratio below is dominated by that and should be read as "
                 f"'the model does not agree with")
        rep.line(f"    itself about whether to smooth', not as a smooth spread of window "
                 f"sizes.")
    rep.line(f"    LIVE spread -- across the ranges INSIDE the cap (1..{MSD_MIN_FIT_LAGS} "
             f"through 1..{chosen}), which are")
    rep.line(f"    the ranges the tool could actually have chosen. This is the dependence that "
             f"remains:")
    rep.line(f"      linear model (discarded): "
             + (f"{lin_ratio:.2f}x" if lin_ratio else "not computable"))
    rep.line(f"      anomalous model (in use): "
             + (f"{anom_ratio:.2f}x" if anom_ratio else "not computable"))
    rep.line(f"    COUNTERFACTUAL spread -- across ALL ranges up to 1..{max_usable}, i.e. what "
             f"would happen if the")
    rep.line(f"    stability cap were NOT applied. This is NOT live instability; the cap "
             f"removes it:")
    rep.line(f"      linear model (discarded): "
             + (f"{lin_ratio_unc:.2f}x" if lin_ratio_unc else "not computable"))
    rep.line(f"      anomalous model (in use): "
             + (f"{anom_ratio_unc:.2f}x" if anom_ratio_unc else "not computable"))
    verdict = "not computable"
    if lin_ratio and anom_ratio:
        if anom_ratio <= FITRANGE_STABLE_RATIO:
            verdict = (f"The anomalous model LARGELY REMOVES the fit-range sensitivity: the "
                       f"window varies by {anom_ratio:.2f}x across fit ranges, below the "
                       f"{FITRANGE_STABLE_RATIO:g}x threshold for calling it stable.")
        elif anom_ratio <= FITRANGE_IMPROVEMENT_FACTOR * lin_ratio:
            verdict = (f"The anomalous model REDUCES BUT DOES NOT REMOVE the fit-range "
                       f"sensitivity: {anom_ratio:.2f}x against the linear model's "
                       f"{lin_ratio:.2f}x, still above the {FITRANGE_STABLE_RATIO:g}x "
                       f"threshold for calling it stable. The window remains a choice, not a "
                       f"measurement.")
        else:
            verdict = (f"The anomalous model DOES NOT REDUCE the fit-range sensitivity: "
                       f"{anom_ratio:.2f}x against the linear model's {lin_ratio:.2f}x. The "
                       f"window still depends as much on where the fit stops as on the data. "
                       f"Do not read the single reported window as a measured quantity.")
    rep.line(f"    {verdict}")
    return {"ranges": ranges, "linear_windows": lin_w, "anomalous_windows": anom_w,
            "linear_ratio": lin_ratio, "anomalous_ratio": anom_ratio,
            "linear_ratio_uncapped": lin_ratio_unc,
            "anomalous_ratio_uncapped": anom_ratio_unc, "verdict": verdict}


def find_confinement_lag(msd: np.ndarray, max_lag: int) -> Optional[int]:
    """
    First lag L beyond which the MSD never again exceeds MSD(L) by more than
    CONFINEMENT_RISE_TOL.  Returns None if the MSD is still rising at the end of
    the usable lag range -- in which case the confinement timescale is unbounded
    by this data.

    The flatness claim is only made when it can be asserted over a meaningful
    stretch of later lags; otherwise the last few noisy points of the MSD curve
    would be read as a plateau that is not there.
    """
    min_tail = max(CONFINEMENT_MIN_SUSTAIN,
                   int(math.ceil(CONFINEMENT_MIN_SUSTAIN_FRACTION * max_lag)))
    for L in range(1, max_lag + 1):
        tail = msd[L + 1: max_lag + 1]
        tail = tail[np.isfinite(tail)]
        if tail.size < min_tail:
            return None
        if not np.isfinite(msd[L]):
            continue
        if np.all(tail <= msd[L] * (1.0 + CONFINEMENT_RISE_TOL)):
            return L
    return None


def measure_timescale(mf: MethodFile, z: np.ndarray, stats: dict, rep: Report) -> MSDResult:
    if stats["median_span"] < 2:
        raise DerivationError(f"{mf.name}: tracks are too short to compute an MSD.")
    probe = int(min(max(stats["max_span"] - 1, 1), 200))
    msd, pairs = pooled_msd(mf, z, probe)

    if pairs[1] == 0:
        raise DerivationError(f"{mf.name}: no lag-1 displacement pairs; MSD is undefined.")

    span_limit = int(math.floor(stats["median_span"] / 2.0))
    max_usable = 0
    for lag in range(1, probe + 1):
        if lag > span_limit:
            break
        if pairs[lag] < MSD_MIN_PAIR_FRACTION * pairs[1]:
            break
        if not np.isfinite(msd[lag]):
            break
        max_usable = lag
    if max_usable < MSD_MIN_FIT_LAGS:
        raise DerivationError(
            f"{mf.name}: only {max_usable} usable MSD lags "
            f"(need >= {MSD_MIN_FIT_LAGS}). Tracks are too short or too sparse."
        )

    rep.line(f"  MSD probed to lag {probe}; usable lag range 1..{max_usable}")
    rep.line(f"    (a lag is usable while it keeps >= {MSD_MIN_PAIR_FRACTION:.0%} of the "
             f"lag-1 pair count [{pairs[1]}] and stays within half the median track "
             f"span [{span_limit}])")

    # Every candidate fit range, fitted once. Two independent criteria then bound it.
    fits: dict[int, tuple[float, float, float, float]] = {}
    for L in range(MSD_MIN_FIT_LAGS, max_usable + 1):
        fit = fit_anomalous(np.arange(1, L + 1, dtype=float), msd[1:L + 1])
        if fit is None:
            break
        fits[L] = fit

    # Criterion 1 -- model adequacy: extend while the model stays a good description.
    l_resid = None
    for L in sorted(fits):
        if fits[L][3] > MSD_FIT_REL_RESID_TOL:
            break
        l_resid = L

    # Criterion 2 -- sigma identifiability. sigma is a SHORT-LAG property: it is the
    # zero-lag intercept, and only the first few lags carry information about it. A
    # flexible power law fitted over the whole curve absorbs the short-lag structure
    # into its exponent and leaves the intercept unidentifiable -- it slides towards
    # zero and then goes negative. Tracking the whole curve is not the objective;
    # resolving the noise floor is.
    #
    # The cap is therefore the end of the PLATEAU over which the fitted sigma is
    # stable: starting from the shortest admissible range, the run is extended while
    # the relative spread of sigma across it stays within SIGMA_STABILITY_TOL. No lag
    # count is hardcoded; the plateau is wherever the data puts it.
    sigmas = sigma_by_range(fits)
    plateau, l_stab = stable_plateau(fits, sigmas)

    if l_stab is None:
        raise DerivationError(
            f"{mf.name}: the fitted sigma has no stable plateau. Starting from lag "
            f"{MSD_MIN_FIT_LAGS}, no run of at least {SIGMA_STABILITY_MIN_RUN} consecutive fit "
            f"ranges holds sigma to within {SIGMA_STABILITY_TOL:.0%} "
            f"(longest stable run found: "
            f"{len(plateau)} range(s)"
            + (f", over fit ranges 1..{plateau[0]} through 1..{plateau[-1]}" if plateau else "")
            + "), "
            f"so there is no range over which the noise floor is identifiable. No fit range is "
            f"chosen and no window is derived. The tool does NOT fall back to the largest "
            f"positive-intercept range, nor to any other rule."
        )

    best = None
    if l_resid is not None:
        L = min(l_resid, l_stab)
        if L in fits:
            a_hat, g_hat, alpha, rel = fits[L]
            best = (L, a_hat, g_hat, alpha, rel)
    if best is None:
        raise DerivationError(
            f"{mf.name}: MSD(tau) = 2*sigma^2 + Gamma*tau^alpha could not be fitted over the "
            f"initial {MSD_MIN_FIT_LAGS} lags within the {MSD_FIT_REL_RESID_TOL:.0%} "
            f"relative-residual tolerance, or the best alpha fell on a search bound "
            f"[{ALPHA_SEARCH_MIN:g}, {ALPHA_SEARCH_MAX:g}] and is therefore an artifact of the "
            f"bound rather than a result. No localisation noise, transport coefficient or "
            f"exponent can be extracted; refusing to guess. The discarded linear model is NOT "
            f"substituted."
        )
    fit_lags, intercept, gamma, alpha, rel = best

    rep.line(f"  Model               : MSD(tau) = 2*sigma^2 + Gamma * tau^alpha "
             f"(anomalous diffusion; alpha is fitted, not assumed)")
    rep.line(f"  Fit range chosen    : lags 1..{fit_lags}   (rel residual {rel:.4f})")
    rep.line(f"    Two criteria bound the range; the smaller wins.")
    rep.line(f"    1. Model adequacy: extend while the RMS fit residual stays within "
             f"{MSD_FIT_REL_RESID_TOL:.0%} of the mean MSD")
    rep.line(f"       over the range. That allows lags 1..{l_resid}.")
    rep.line(f"    2. sigma identifiability: sigma is the ZERO-LAG intercept, so only short "
             f"lags carry information")
    rep.line(f"       about it. Fitted over a long range, a flexible power law absorbs the "
             f"short-lag structure into")
    rep.line(f"       its exponent and the intercept slides to zero and then negative. The cap "
             f"is the end of the")
    rep.line(f"       plateau over which the fitted sigma is stable to within "
             f"{SIGMA_STABILITY_TOL:.0%} across at least")
    rep.line(f"       {SIGMA_STABILITY_MIN_RUN} consecutive ranges. That allows lags "
             f"1..{l_stab}. No lag count is hardcoded.")
    plateau_str = ", ".join(f"L={x}:{sigmas[x]:.3f}" for x in plateau)
    rep.line(f"       plateau: {plateau_str}")
    rep.line(f"    Why stability rather than intercept positivity: positivity would take the "
             f"LAST range before the")
    rep.line(f"    intercept goes negative, by which point it is already collapsing, and the "
             f"sigma it returns is far")
    rep.line(f"    below the independent model-free estimate. The stability cap was chosen "
             f"because it produces")
    rep.line(f"    AGREEMENT with the model-free covariance estimator, and that agreement "
             f"between two estimators")
    rep.line(f"    sharing no assumptions is the justification for the rule. Compare the two "
             f"sigma values below.")
    rep.line(f"    alpha was searched on a dense grid over [{ALPHA_SEARCH_MIN:g}, "
             f"{ALPHA_SEARCH_MAX:g}] step {ALPHA_SEARCH_STEP:g}; at each alpha the model is "
             f"linear in 2*sigma^2 and Gamma, so those are exact least squares.")

    if intercept > 0:
        sigma = math.sqrt(intercept / 2.0)
        resolvable = True
    else:
        sigma = 0.0
        resolvable = False

    # The same fit on the UNCLEANED MSD, so the report can show how much of alpha is
    # an artifact of the Stage 2 pass rather than a property of the motion.
    # The raw fit gets its OWN stability plateau. Forcing it over the cleaned data's
    # fit range would fit it where it is not conditioned -- reintroducing exactly the
    # over-extended-range misspecification the stability cap exists to remove. If the
    # raw MSD has no plateau of its own, the comparison is reported as unavailable
    # with the reason, not manufactured.
    alpha_raw: Optional[float] = None
    alpha_raw_range: Optional[int] = None
    alpha_raw_reason: Optional[str] = None
    msd_raw, pairs_raw = pooled_msd(mf, mf.z, max_usable)
    if pairs_raw[1] <= 0:
        alpha_raw_reason = "the uncleaned MSD has no lag-1 pairs"
    else:
        raw_fits: dict[int, tuple[float, float, float, float]] = {}
        for L in range(MSD_MIN_FIT_LAGS, max_usable + 1):
            if not np.all(np.isfinite(msd_raw[1:L + 1])):
                break
            rf = fit_anomalous(np.arange(1, L + 1, dtype=float), msd_raw[1:L + 1])
            if rf is None:
                break
            raw_fits[L] = rf
        if not raw_fits:
            alpha_raw_reason = ("the anomalous model does not converge on the uncleaned MSD "
                                "at any fit range")
        else:
            raw_plateau, raw_cap = stable_plateau(raw_fits, sigma_by_range(raw_fits))
            if raw_cap is None:
                alpha_raw_reason = (
                    f"the uncleaned MSD has no stable sigma plateau of its own (longest run "
                    f"{len(raw_plateau)} range(s), needs {SIGMA_STABILITY_MIN_RUN}), so there "
                    f"is no range over which a raw alpha would be conditioned"
                )
            else:
                alpha_raw = raw_fits[raw_cap][2]
                alpha_raw_range = raw_cap

    conf = find_confinement_lag(msd, max_usable)

    return MSDResult(
        lags=np.arange(0, max_usable + 1),
        msd=msd,
        pairs=pairs,
        max_usable_lag=max_usable,
        fit_lags=fit_lags,
        intercept=intercept,
        gamma=gamma,
        alpha=alpha,
        rel_residual=rel,
        sigma=sigma,
        sigma_resolvable=resolvable,
        alpha_no_rejection=alpha_raw,
        alpha_no_rejection_range=alpha_raw_range,
        alpha_no_rejection_reason=alpha_raw_reason,
        confinement_lag=conf,
    )


def derive_windows(mf: MethodFile, msd_res: MSDResult, stats: dict,
                   noise_margin: float, rep: Report) -> Derived:
    notes: list[str] = []
    gamma = msd_res.gamma
    alpha = msd_res.alpha
    if gamma <= 0:
        raise DerivationError(
            f"{mf.name}: the fitted transport coefficient Gamma is {gamma:.6g} (not "
            f"positive). There is no measurable motion scale, so neither the smoothing "
            f"window nor the Hampel window can be derived. Refusing to guess."
        )
    sigma = msd_res.sigma
    # The single-frame motion scale implied by the FITTED model: the motion term at
    # tau = 1 is Gamma * 1^alpha = Gamma, so the displacement scale is sqrt(Gamma).
    single_frame_motion = math.sqrt(gamma)

    # 3d -- smoothing window.
    # Requirement: sigma * sqrt(2) / sqrt(W) <= single_frame_motion / k
    #  =>  W >= 2 * k^2 * sigma^2 / Gamma
    w_req, w_req_uncorr = smoothing_window_requirement(msd_res.intercept, gamma,
                                                       noise_margin, alpha)
    w_smooth = next_odd_at_least(w_req)
    cap = None
    if msd_res.confinement_lag is not None:
        cap = int(math.floor(msd_res.confinement_lag / 2.0))
        capped = prev_odd_at_most(cap)
        if capped < w_smooth:
            notes.append(
                f"smoothing window reduced from {w_smooth} to {capped} by the confinement cap "
                f"(half the confinement lag {msd_res.confinement_lag})"
            )
            w_smooth = capped

    # 3e -- Hampel window, from the same measured timescale.
    # The crossover lag tau* is where genuine motion overtakes localisation noise:
    #   Gamma * tau^alpha = 2 * sigma^2  =>  tau* = (2 sigma^2 / Gamma)^(1/alpha).
    # Points closer together than tau* are statistically indistinguishable, so they
    # form the legitimate local neighbourhood for a median/MAD. With alpha < 1 the
    # motion accumulates more slowly, so tau* is longer than the linear model implied.
    ratio = max(msd_res.intercept, 0.0) / gamma
    tau_star = ratio ** (1.0 / alpha) if ratio > 0 else 0.0
    w_hampel_raw = 2.0 * tau_star + 1.0
    w_hampel = next_odd_at_least(w_hampel_raw)
    clamped = False
    if w_hampel < MIN_HAMPEL_WINDOW:
        clamped = True
        notes.append(
            f"derived Hampel window {w_hampel} is below the {MIN_HAMPEL_WINDOW}-point minimum "
            f"needed to form a median and MAD at all; raised to {MIN_HAMPEL_WINDOW}. This is a "
            f"structural minimum, not a fallback value"
        )
        w_hampel = MIN_HAMPEL_WINDOW

    rep.line(f"  Measured quantities :")
    rep.line(f"    MSD intercept 2*sigma^2 = {msd_res.intercept:.6g}")
    if msd_res.sigma_resolvable:
        rep.line(f"    localisation noise sigma = {sigma:.6g} (Z units)")
    else:
        rep.line(f"    localisation noise sigma = UNRESOLVABLE (intercept is not positive)")
    rep.line(f"    transport coefficient Gamma = {gamma:.6g} (Z units^2 per frame^alpha)")
    rep.line(f"    anomalous exponent alpha = {alpha:.4f}  [{describe_alpha(alpha)}]")
    rep.line(f"      alpha = 1 is normal diffusion; below 1 subdiffusive; above 1 "
             f"superdiffusive or directed.")
    if msd_res.alpha_no_rejection is not None:
        rep.line(f"      alpha is measured on STAGE-2-CLEANED data and is therefore partly an "
                 f"artifact of that pass:")
        rep.line(f"      alpha with Stage 2 rejection = {alpha:.4f} (lags 1..{msd_res.fit_lags}); "
                 f"without any rejection = {msd_res.alpha_no_rejection:.4f} "
                 f"(lags 1..{msd_res.alpha_no_rejection_range}).")
        rep.line(f"      Each is fitted over ITS OWN stability plateau; the ranges differ "
                 f"because the plateaus do.")
        rep.line(f"      The strict pass removes large single-frame excursions, which "
                 f"suppresses short-lag MSD and")
        rep.line(f"      changes the apparent exponent. Neither value is 'the' exponent of the "
                 f"underlying motion.")
    else:
        rep.line(f"      alpha on unrejected data is NOT AVAILABLE: "
                 f"{msd_res.alpha_no_rejection_reason}.")
        rep.line(f"      It is deliberately not forced over the cleaned data's fit range: "
                 f"fitting it where it is not")
        rep.line(f"      conditioned would reintroduce the over-extended-range misspecification "
                 f"the stability cap")
        rep.line(f"      removes. The size of the Stage 2 artifact is therefore unknown for "
                 f"this method.")
    rep.line(f"    single-frame motion scale sqrt(Gamma) = {single_frame_motion:.6g} (Z units)")
    rep.line(f"    noise/motion crossover lag tau* = (2*sigma^2/Gamma)^(1/alpha) = "
             f"{tau_star:.4f} frames")
    if msd_res.confinement_lag is None:
        rep.line(f"    confinement lag = NOT REACHED within lags 1..{msd_res.max_usable_lag}")
    else:
        rep.line(f"    confinement lag = {msd_res.confinement_lag} frames "
                 f"(no later lag up to {msd_res.max_usable_lag} exceeds MSD there by more "
                 f"than {CONFINEMENT_RISE_TOL:.0%})")
    rep.line(f"  Derived windows     :")
    rep.line(f"    smoothing window: smallest odd W with "
             f"noise(W)/motion(W) <= 1/{noise_margin:g}^2 at lag 1, where")
    rep.line(f"      noise(W) = 2*sigma^2*W^-2 and motion(W) = Gamma*W^(alpha-2), so "
             f"ratio(W) = 2*sigma^2/(Gamma*W^alpha)")
    rep.line(f"      -> W >= (2*{noise_margin:g}^2*sigma^2/Gamma)^(1/alpha) = "
             f"({w_req_uncorr:.4f})^(1/{alpha:.4f}) = {w_req:.4f}  =>  W_smooth = {w_smooth}")
    rep.line(f"      the 1/alpha correction: uncorrected requirement {w_req_uncorr:.4f} "
             f"(W = {next_odd_at_least(w_req_uncorr)}) -> corrected {w_req:.4f} "
             f"(W = {next_odd_at_least(w_req)})")
    rep.line(f"      The uncorrected form is the alpha = 1 special case. It was what this "
             f"tool used previously and")
    rep.line(f"      is systematically wrong away from alpha = 1, silently.")
    rep.line(f"    Hampel window   : smallest odd W >= 2*tau* + 1 = {w_hampel_raw:.4f}  =>  "
             f"W_hampel = {w_hampel}")
    if (np.isfinite(w_req) and np.isfinite(w_req_uncorr) and w_req > 0
            and w_req_uncorr > 0):
        corr_ratio = max(w_req / w_req_uncorr, w_req_uncorr / w_req)
        if corr_ratio > ALPHA_CORRECTION_WARN_RATIO:
            rep.warn(
                "ALPHA_DRIVES_WINDOW",
                f"{mf.name}: the 1/alpha correction changes the smoothing-window "
                f"requirement by {corr_ratio:.2f}x (uncorrected {w_req_uncorr:.4f} -> "
                f"corrected {w_req:.4f}; alpha = {alpha:.4f}, 1/alpha = "
                f"{1.0 / alpha:.4f}), above the stated {ALPHA_CORRECTION_WARN_RATIO:g}x "
                f"threshold. On this dataset alpha materially drives the window, so the "
                f"window is only as trustworthy as the fitted exponent. Check the "
                f"fit-range sensitivity table and the plateau before relying on it.",
            )

    for note in notes:
        rep.line(f"    note: {note}")

    # Whether the Hampel window spans a whole track is checked in the caller, after
    # override resolution, so that the warning describes the window actually in use
    # rather than a derived value an override may have replaced.

    return Derived(
        smoothing_window=w_smooth,
        hampel_window=w_hampel,
        smoothing_required_raw=w_req,
        smoothing_required_uncorrected=w_req_uncorr,
        crossover_lag=tau_star,
        confinement_cap=cap,
        hampel_clamped=clamped,
        notes=notes,
    )


def check_smoothing_window_usable(mf: MethodFile, stats: dict, w_smooth: int) -> None:
    """
    Refuse a smoothing window at or above the median track span.

    Such a window spans all the data a typical track has, so the moving average
    reduces every point in that track to the track mean. That is not a smoothed
    trajectory and must not be emitted as one, so this is a hard failure for the
    affected method rather than a note -- consistent with the rule that a failed
    derivation refuses rather than guesses.
    """
    median_span = stats["median_span"]
    if median_span <= 0 or w_smooth < median_span:
        return

    spans = np.array([int(mf.frame[stop - 1] - mf.frame[start] + 1)
                      for start, stop in mf.slices], dtype=float)
    lengths = np.array([stop - start for start, stop in mf.slices], dtype=float)
    collapsed = spans <= w_smooth
    n_collapsed = int(collapsed.sum())
    pts_collapsed = float(lengths[collapsed].sum())
    pts_total = float(lengths.sum())

    raise MethodFailure(
        f"{mf.name}: the derived smoothing window is {w_smooth} frames, at or above the "
        f"median track span of {median_span:.0f} frames. At this window "
        f"{n_collapsed} of {len(spans)} tracks are spanned end to end "
        f"({pts_collapsed / max(pts_total, 1):.1%} of all points), so the moving average "
        f"reduces those tracks to a single track mean. That is not a smoothed trajectory "
        f"and will not be emitted as one. No smoothed output has been written for this "
        f"method. If a window this wide is intended, re-run with an explicit "
        f"--smooth-window; the sensitivity table printed above for this method is the "
        f"evidence for choosing one. The underlying cause is visible in this method's "
        f"Stage 3 block and in any CONFINEMENT_UNBOUNDED or NOISE_DOMINATED warning "
        f"raised above."
    )


def parameter_block(rep: Report, fields: list[tuple[str, str]], warnings: list[str],
                    title: str) -> None:
    """
    A compact, fixed-width block holding every derived number for one method, so it
    can be quoted verbatim instead of re-typed. Re-typing values out of a long report
    is how a number from one method ends up attributed to another.
    """
    rep.line()
    rep.rule("=")
    rep.line(f"PARAMETER BLOCK -- {title}")
    rep.line("(quote this verbatim; do not re-type values out of the prose above)")
    rep.rule("=")
    width = max(len(k) for k, _ in fields)
    for key, val in fields:
        rep.line(f"  {key:{width}s} : {val}")
    rep.line(f"  {'warnings':{width}s} : " + (f"{len(warnings)}" if warnings else "none"))
    for w in warnings:
        code = w.split("]")[0].replace("[WARNING: ", "").strip()
        rep.line(f"  {'':{width}s}   - {code}")
    rep.rule("=")


def build_derivation_note(method_name: str, flagged: bool,
                          warnings: list[str]) -> str:
    """
    The semicolon-joined note carried in every row of a method's output CSV.

    Driven entirely by the checks that actually fired -- never by method name -- so
    on another dataset it follows whatever the data turns out to warrant. A reader
    who opens the CSV and never sees the report learns the same caveats from it.
    """
    codes: list[str] = []
    if flagged:
        codes.append("DO_NOT_USE:flagged-inconsistent")
    for w in warnings:
        if not w.startswith("[WARNING: "):
            continue
        head, _, tail = w.partition("]")
        code = head.replace("[WARNING: ", "").strip()
        if code in codes:
            continue
        if code in RUN_LEVEL_WARNING_CODES or f"{method_name}:" in tail:
            codes.append(code)
    known = {c: i for i, c in enumerate(NOTE_SEVERITY_ORDER)}
    codes.sort(key=lambda c: (known.get(c, len(known)), c))
    return ";".join(codes)


def record_method_failure(rep: Report, failures: dict[str, str], name: str,
                          code: str, text: str) -> None:
    """Report a failure that stops this method but not the run."""
    rep.line()
    rep.rule("!")
    rep.line(f"METHOD FAILED: {text}")
    rep.rule("!")
    rep.fail(code, text)
    failures[name] = text


def per_track_outlier_breakdown(mf: MethodFile, flags: np.ndarray, rep: Report) -> dict:
    """Per-track outlier rates, so one bad track can be told from a global problem."""
    rows = []
    for start, stop in mf.slices:
        finite = int(np.sum(np.isfinite(mf.z[start:stop])))
        flagged = int(np.sum(flags[start:stop]))
        if finite == 0:
            continue
        rows.append((int(mf.track_id[start]), flagged, finite, flagged / finite))
    if not rows:
        rep.line("  Per-track outlier rates: no track has any finite Z.")
        return {}

    rates = np.array([r[3] for r in rows])
    total_flagged = sum(r[1] for r in rows)
    zero = int(np.sum(rates == 0.0))
    q = np.percentile(rates, [0, 25, 50, 75, 100])
    rep.line("  Per-track outlier rate distribution:")
    rep.line(f"    tracks                 : {len(rows)}")
    rep.line(f"    tracks with 0 outliers : {zero} ({zero / len(rows):.1%})")
    rep.line(f"    rate min / q25 / median / q75 / max : "
             f"{q[0]:.2%} / {q[1]:.2%} / {q[2]:.2%} / {q[3]:.2%} / {q[4]:.2%}")

    named = sorted([r for r in rows if r[3] > PER_TRACK_OUTLIER_NAME_RATE],
                   key=lambda r: -r[3])
    rep.line(f"    tracks above the stated {PER_TRACK_OUTLIER_NAME_RATE:.0%} rate : "
             f"{len(named)}")
    if named:
        share = sum(r[1] for r in named) / max(total_flagged, 1)
        rep.line(f"    they contribute {sum(r[1] for r in named)} of {total_flagged} "
                 f"outliers ({share:.1%} of the total)")
        rep.line(f"    {'Track_ID':>10s} {'outliers':>9s} {'points':>7s} {'rate':>8s}")
        for tid, flagged, finite, rate in named:
            rep.line(f"    {tid:10d} {flagged:9d} {finite:7d} {rate:8.2%}")
        rep.line("    A high share concentrated in few tracks points at those tracks; a rate "
                 "spread evenly across tracks points at the method or the acquisition.")
    else:
        rep.line("    No individual track exceeds the stated rate; any elevated overall rate "
                 "is spread across tracks rather than concentrated in a few.")
    return {
        "n_tracks": len(rows),
        "zero": zero,
        "median_rate": float(q[2]),
        "max_rate": float(q[4]),
        "n_named": len(named),
        "named_share": (sum(r[1] for r in named) / max(total_flagged, 1)) if named else 0.0,
    }


def mean_abs_dz_per_frame(mf: MethodFile, z: np.ndarray) -> tuple[float, int]:
    """Mean |dZ| per frame over consecutive available points within each track."""
    total = 0.0
    count = 0
    for start, stop in mf.slices:
        fr = mf.frame[start:stop].astype(float)
        zz = z[start:stop]
        if zz.size < 2:
            continue
        d = np.abs(np.diff(zz)) / np.diff(fr)
        d = d[np.isfinite(d)]
        total += float(d.sum())
        count += int(d.size)
    return (total / count if count else float("nan")), count


def sensitivity_table(mf: MethodFile, z_raw: np.ndarray, z_rejected: np.ndarray,
                      stats: dict, chosen_window: int, rep: Report) -> dict:
    top = prev_odd_at_most(min(max(stats["median_track_length"] / 2.0,
                                   SENSITIVITY_MIN_MAX_WINDOW),
                               SENSITIVITY_MAX_WINDOW))
    standard = list(range(1, top + 1, 2))
    bridge: list[int] = []
    if chosen_window > top:
        # Sample across the gap so that neither the table nor the plotted line
        # spans ground that was never measured. Spacing is LOGARITHMIC: the curve
        # changes fastest at small windows, so even spacing would waste most of the
        # points on the flat tail and under-resolve the part that matters.
        for v in np.geomspace(top, chosen_window, SENSITIVITY_BRIDGE_POINTS + 2)[1:-1]:
            bridge.append(next_odd_at_least(float(v)))
    windows = sorted(set(standard + bridge + [chosen_window]))
    rep.line(f"  Sensitivity table (mean |dZ| per frame vs smoothing window; window range "
             f"1..{top} derived from half the median track length "
             f"[{stats['median_track_length']:.0f}], capped at {SENSITIVITY_MAX_WINDOW}):")
    if bridge:
        rep.line(f"    The window in use ({chosen_window}) lies beyond that range, so "
                 f"{len(sorted(set(bridge)))} intermediate windows were also sampled to cover "
                 f"the gap,")
        rep.line(f"    spaced logarithmically because the curve changes fastest at small "
                 f"windows.")
    rep.line(f"    {'window':>7s} {'no rejection':>14s} {'with rejection':>16s} "
             f"{'pairs (rej.)':>13s}")
    raw_vals, rej_vals = [], []
    for w in windows:
        s_raw = gap_aware_moving_average_all(mf, z_raw, w)
        s_rej = gap_aware_moving_average_all(mf, z_rejected, w)
        v_raw, _ = mean_abs_dz_per_frame(mf, s_raw)
        v_rej, n_rej = mean_abs_dz_per_frame(mf, s_rej)
        raw_vals.append(v_raw)
        rej_vals.append(v_rej)
        mark = "  <-- chosen" if w == chosen_window else ""
        rep.line(f"    {w:7d} {v_raw:14.6g} {v_rej:16.6g} {n_rej:13d}{mark}")
    return {"windows": windows, "no_rejection": raw_vals, "with_rejection": rej_vals,
            "chosen": chosen_window}


def gap_aware_moving_average_all(mf: MethodFile, z: np.ndarray, window: int) -> np.ndarray:
    out = np.full(z.size, np.nan)
    for start, stop in mf.slices:
        out[start:stop] = gap_aware_moving_average(
            mf.frame[start:stop], z[start:stop], window
        )
    return out


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
DERIVATION_VERSION = "zsmooth-derivation-4"
# Bump this string whenever a change alters the NUMBERS a run produces from the same
# inputs. History, so a stale output can be identified from its stamp alone:
#   -1  linear MSD model, 2*sigma^2 + D*tau
#   -2  anomalous model, 2*sigma^2 + Gamma*tau^alpha, fit range by residual only
#   -3  sigma-stability cap on the fit range
#   -4  1/alpha correction on the smoothing-window requirement


def derivation_stamp(args: argparse.Namespace) -> str:
    """
    Short hash over everything that can change the derived numbers: the derivation
    version, every declared constant, and the CLI arguments the derivation reads.

    Two runs sharing a stamp produced their numbers the same way. Two runs differing
    in it did not, and an output file carrying an old stamp is stale. Report-only
    settings (--plot, --frame-interval) are excluded so they do not perturb it.
    """
    parts = [
        DERIVATION_VERSION,
        f"zstep={args.z_step!r}", f"mad={args.mad_threshold!r}",
        f"k={args.noise_margin!r}", f"hw={args.hampel_window!r}",
        f"sw={args.smooth_window!r}",
        f"c={DEFAULT_MAD_THRESHOLD},{STAGE2_MAD_THRESHOLD},{STAGE2_WINDOW_TRACK_FRACTION},"
        f"{DEFAULT_NOISE_MARGIN_FACTOR},{ALPHA_SEARCH_MIN},{ALPHA_SEARCH_MAX},"
        f"{ALPHA_SEARCH_STEP},{ALPHA_WARN_DEVIATION},{SIGMA_STABILITY_TOL},"
        f"{SIGMA_STABILITY_MIN_RUN},{ALPHA_CORRECTION_WARN_RATIO},"
        f"{MSD_FIT_REL_RESID_TOL},{MSD_MIN_FIT_LAGS},{MSD_MIN_PAIR_FRACTION},"
        f"{CONFINEMENT_RISE_TOL},{CONFINEMENT_MIN_SUSTAIN_FRACTION},"
        f"{CONFINEMENT_MIN_SUSTAIN},{MIN_HAMPEL_WINDOW},{LATTICE_MULTIPLE_FRACTION},"
        f"{LATTICE_MIN_OCCUPANCY}",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]


def matplotlib_available() -> bool:
    try:
        import matplotlib  # noqa: F401
    except Exception:
        return False
    return True


def plot_diagnostics(mf: MethodFile, msd_res: MSDResult, sens: Optional[dict],
                     noise_margin: float, out_dir: str) -> str:
    """
    Per-method diagnostic figure: the MSD curve with its fit, and the sensitivity
    curve. Called only when --plot was given. Imports matplotlib lazily so the
    tool runs unchanged without it.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n_panels = 1 if sens is None else 2
    fig, axes = plt.subplots(1, n_panels, figsize=(6.5 * n_panels, 4.6))
    axes = [axes] if n_panels == 1 else list(axes)

    ax = axes[0]
    lags = np.arange(1, msd_res.max_usable_lag + 1)
    ax.plot(lags, msd_res.msd[1:msd_res.max_usable_lag + 1], "o", ms=3.5,
            color="0.35", label="MSD (pooled, present pairs)")
    fit_x = np.linspace(0, msd_res.max_usable_lag, 100)
    ax.plot(fit_x, msd_res.intercept + msd_res.gamma * np.power(fit_x, msd_res.alpha),
            "-", lw=1.6, color="C3",
            label=f"fit: 2*sigma^2 + Gamma*tau^alpha\nsigma={msd_res.sigma:.4g}, "
                  f"Gamma={msd_res.gamma:.4g}, alpha={msd_res.alpha:.3f}")
    ax.axvspan(1, msd_res.fit_lags, color="C0", alpha=0.12,
               label=f"fit range (lags 1..{msd_res.fit_lags})")
    ax.axhline(msd_res.intercept, ls=":", lw=1.0, color="C3")
    if msd_res.confinement_lag is not None:
        ax.axvline(msd_res.confinement_lag, ls="--", lw=1.2, color="C2",
                   label=f"confinement lag = {msd_res.confinement_lag}")
    else:
        ax.plot([], [], " ", label="confinement lag: not reached")
    ax.set_xlabel("lag tau (frames)")
    ax.set_ylabel("MSD of Z (Z units^2)")
    ax.set_title(f"{mf.name}\nMSD vs lag")
    ax.legend(fontsize=7.5, loc="upper left")
    ax.grid(alpha=0.25)

    if sens is not None:
        ax = axes[1]
        ax.plot(sens["windows"], sens["no_rejection"], "o-", ms=3.5, lw=1.3,
                label="no rejection")
        ax.plot(sens["windows"], sens["with_rejection"], "s-", ms=3.5, lw=1.3,
                label="with rejection")
        ax.axvline(sens["chosen"], ls="--", lw=1.2, color="C3",
                   label=f"window in use = {sens['chosen']}")
        ax.set_xlabel("smoothing window (frames)")
        ax.set_ylabel("mean |dZ| per frame (Z units)")
        ax.set_title(f"Sensitivity (k = {noise_margin:g})")
        ax.legend(fontsize=7.5)
        ax.grid(alpha=0.25)

    fig.tight_layout()
    path = os.path.join(out_dir, f"{os.path.splitext(mf.name)[0]}_diagnostics.png")
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="zsmooth.py",
        description="Reject transient outliers and smooth Z(t) in ZTracker_Fiji "
                    "Tool 3 (TopoJ) trajectory exports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("inputs", nargs="+", metavar="CSV",
                   help="one or more input CSVs, one per sampling method")
    p.add_argument("-o", "--out", required=True, metavar="DIR",
                   help="output directory (created if absent)")
    p.add_argument("--z-step", type=float, required=True, metavar="MICROMETRES",
                   help="Z step in micrometres. REQUIRED. Used as the Hampel MAD floor "
                        "and cross-checked against the lattice spacing found in the data.")
    p.add_argument("--lattice-reference", default=None, metavar="CSV",
                   help="which of the input files was produced by SINGLE-PIXEL sampling. "
                        "Only such a file carries the raw Z lattice, so only it can verify "
                        "--z-step. Give it exactly as it appears in the input list (or as a "
                        "bare filename). Without it the Z step is NOT verified and a warning "
                        "says so.")
    p.add_argument("--frame-interval", type=float, default=None, metavar="SECONDS",
                   help="frame interval in seconds. OPTIONAL. Used ONLY to additionally "
                        "express speeds in micrometres per second in the report; no "
                        "analysis step and no derived window depends on it.")
    p.add_argument("--mad-threshold", type=float, default=DEFAULT_MAD_THRESHOLD,
                   metavar="MAD",
                   help=f"Hampel threshold in MAD units for the Stage 4 pass "
                        f"(default {DEFAULT_MAD_THRESHOLD})")
    p.add_argument("--noise-margin", type=float, default=DEFAULT_NOISE_MARGIN_FACTOR,
                   metavar="K",
                   help=f"Stage 3d noise-margin factor k: the smoothing window is the "
                        f"smallest odd W whose residual noise contribution falls below the "
                        f"single-frame motion scale by this factor "
                        f"(default {DEFAULT_NOISE_MARGIN_FACTOR:g})")
    p.add_argument("--plot", action="store_true",
                   help="write a per-method diagnostic PNG (MSD curve with the fit and fit "
                        "range marked, plus the sensitivity curve). Requires matplotlib, "
                        "which is otherwise not needed.")
    p.add_argument("--hampel-window", type=int, default=None, metavar="FRAMES",
                   help="override the derived Stage 4 Hampel window (odd, >= 3). Both the "
                        "derived value and this override are recorded in the report.")
    p.add_argument("--smooth-window", type=int, default=None, metavar="FRAMES",
                   help="override the derived smoothing window (odd, >= 1). Both the derived "
                        "value and this override are recorded in the report.")
    return p


def validate_args(args: argparse.Namespace) -> None:
    if args.z_step <= 0:
        raise FatalDataError(f"--z-step must be positive; got {args.z_step}")
    if args.mad_threshold <= 0:
        raise FatalDataError(f"--mad-threshold must be positive; got {args.mad_threshold}")
    if args.frame_interval is not None and args.frame_interval <= 0:
        raise FatalDataError(f"--frame-interval must be positive; got {args.frame_interval}")
    if args.noise_margin <= 0:
        raise FatalDataError(f"--noise-margin must be positive; got {args.noise_margin}")
    # Every per-file key -- the output CSV name, the report sections, the stats,
    # results and failures dicts -- is derived from the input basename. Two inputs
    # sharing one would overwrite each other's output and collide in the report,
    # and the run would exit 0 as though nothing were wrong.
    seen: dict[str, list[str]] = {}
    for path in args.inputs:
        seen.setdefault(os.path.basename(path), []).append(path)
    collisions = {base: paths for base, paths in seen.items() if len(paths) > 1}
    if collisions:
        detail = []
        for base, paths in collisions.items():
            detail.append(f"  '{base}' is shared by {len(paths)} inputs:")
            detail.extend(f"    {os.path.abspath(p)}" for p in paths)
        raise FatalDataError(
            "input files share a basename:\n" + "\n".join(detail) + "\n"
            "  Every per-file output is named from the basename, so these would "
            "overwrite each other's\n"
            "  _smoothed.csv and collide in the report. Rename or copy them to distinct "
            "filenames first."
        )

    args.lattice_reference_index = None
    if args.lattice_reference is not None:
        ref = args.lattice_reference
        exact = [p for p in args.inputs
                 if os.path.abspath(p) == os.path.abspath(ref)]
        if len(exact) == 1:
            args.lattice_reference_index = args.inputs.index(exact[0])
        else:
            wanted = os.path.basename(ref)
            candidates = [p for p in args.inputs if os.path.basename(p) == wanted]
            if not candidates:
                raise FatalDataError(
                    f"--lattice-reference '{ref}' is not one of the input files. It must "
                    f"name a file that was also passed as an input. Inputs are: "
                    + ", ".join(os.path.basename(p) for p in args.inputs)
                )
            if len(candidates) > 1:
                listed = "\n".join(f"    {os.path.abspath(p)}" for p in candidates)
                raise FatalDataError(
                    f"--lattice-reference '{ref}' is ambiguous: {len(candidates)} input "
                    f"files share the basename '{wanted}':\n{listed}\n"
                    f"  Refusing to pick one -- naming the wrong file would verify --z-step "
                    f"against the wrong lattice. Give the full path of the single-pixel file."
                )
            args.lattice_reference_index = args.inputs.index(candidates[0])
    if args.plot and not matplotlib_available():
        raise FatalDataError(
            "--plot requires matplotlib, which is not installed. Install it with "
            "'pip install matplotlib' (see requirements.txt), or re-run without --plot; "
            "every other output is unaffected."
        )
    for name, val, minimum in (("--hampel-window", args.hampel_window, MIN_HAMPEL_WINDOW),
                               ("--smooth-window", args.smooth_window, 1)):
        if val is None:
            continue
        if val < minimum or val % 2 == 0:
            raise FatalDataError(
                f"{name} must be an odd integer >= {minimum}; got {val}"
            )


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    rep = Report()

    try:
        validate_args(args)
        os.makedirs(args.out, exist_ok=True)

        stamp = derivation_stamp(args)
        rep.line("ZTracker Tool 3 (TopoJ) Z-trajectory outlier rejection and smoothing")
        rep.line("zsmooth.py parameters report")
        rep.rule("=")
        rep.line(f"DERIVATION STAMP : {stamp}   ({DERIVATION_VERSION})")
        rep.line("  A short hash over the derivation version, every declared constant, and the")
        rep.line("  CLI arguments the derivation reads. Two runs sharing this stamp produced "
                 "their numbers")
        rep.line("  the same way; an output carrying a different stamp came from a different "
                 "derivation and")
        rep.line("  should not be compared with this one. It appears in every parameter block "
                 "below.")
        rep.rule("=")
        rep.line("All analysis is performed in FRAME units. Z units are whatever the input "
                 "files carry (micrometres, per the export specification).")
        rep.line()
        rep.line("Command line:")
        rep.line("  " + " ".join([os.path.basename(sys.argv[0] or "zsmooth.py")] +
                                 (argv if argv is not None else sys.argv[1:])))
        rep.line()
        rep.line("Inputs:")
        for path in args.inputs:
            rep.line(f"  {os.path.abspath(path)}")
        rep.line(f"Output directory: {os.path.abspath(args.out)}")
        rep.line()
        rep.line("User-supplied parameters:")
        rep.line(f"  --z-step         = {args.z_step:.6g} micrometres")
        rep.line(f"  --lattice-reference = "
                 + (args.lattice_reference if args.lattice_reference
                    else "not supplied (Z step NOT verified)"))
        rep.line(f"  --frame-interval = "
                 + (f"{args.frame_interval:.6g} s (report-only)"
                    if args.frame_interval is not None
                    else "not supplied (speeds reported per frame)"))
        rep.line(f"  --mad-threshold  = {args.mad_threshold:g} MAD")
        if args.noise_margin == DEFAULT_NOISE_MARGIN_FACTOR:
            rep.line(f"  --noise-margin   = {args.noise_margin:g} "
                     f"(default {DEFAULT_NOISE_MARGIN_FACTOR:g}, not overridden)")
        else:
            rep.line(f"  --noise-margin   = {args.noise_margin:g} "
                     f"(OVERRIDES the default {DEFAULT_NOISE_MARGIN_FACTOR:g})")
        rep.line(f"  --plot           = "
                 + ("on" if args.plot else "off"))
        rep.line(f"  --hampel-window  = "
                 + (str(args.hampel_window) if args.hampel_window else "derived from data"))
        rep.line(f"  --smooth-window  = "
                 + (str(args.smooth_window) if args.smooth_window else "derived from data"))
        rep.line()
        rep.line("Declared constants (all of them scale-free ratios or tolerances):")
        rep.line(f"  Stage 2 Hampel threshold                     = {STAGE2_MAD_THRESHOLD:g} MAD")
        rep.line(f"  Stage 2 window / median track length         = {STAGE2_WINDOW_TRACK_FRACTION:g}")
        rep.line(f"  Stage 3d noise-margin factor k (in use)      = {args.noise_margin:g} "
                 f"(default {DEFAULT_NOISE_MARGIN_FACTOR:g})")
        rep.line(f"  --z-step equality rel. tolerance             = {Z_STEP_EQUALITY_RTOL:g}")
        rep.line(f"  --z-step submultiple rel. tolerance (info)   = {Z_STEP_MULTIPLE_RTOL:g}")
        rep.line(f"  Sensitivity bridge points beyond the range   = "
                 f"{SENSITIVITY_BRIDGE_POINTS} (log-spaced)")
        rep.line(f"  Per-track outlier naming rate                = "
                 f"{PER_TRACK_OUTLIER_NAME_RATE:g}")
        rep.line(f"  MSD fit relative-residual tolerance          = {MSD_FIT_REL_RESID_TOL:g}")
        rep.line(f"  MSD minimum lag pair fraction                = {MSD_MIN_PAIR_FRACTION:g}")
        rep.line(f"  Confinement 'ceases to rise' tolerance       = {CONFINEMENT_RISE_TOL:g}")
        rep.line(f"  Confinement min sustained tail / lag range   = "
                 f"{CONFINEMENT_MIN_SUSTAIN_FRACTION:g} (never fewer than "
                 f"{CONFINEMENT_MIN_SUSTAIN} lags)")
        rep.line(f"  Outlier-rate warning threshold               = {OUTLIER_RATE_WARN_FRACTION:g}")
        rep.line(f"  sigma/Z-range warning threshold              = {SIGMA_RANGE_WARN_FRACTION:g}")
        rep.line(f"  Minimum tracks for a stable MSD fit          = {MIN_TRACKS_FOR_MSD}")
        rep.line(f"  Minimum pairs at the top fit lag             = {MIN_PAIRS_AT_MAX_FIT_LAG}")

        # ------------------------------------------------------------------
        rep.section("STAGE 1 -- DIAGNOSE")
        methods = [load_method(p) for p in args.inputs]
        stage1_consistency(methods, rep)
        detected_spacing, zstep_status = stage1_zstep(
            methods, args.z_step, args.lattice_reference_index, args.lattice_reference, rep)
        inconsistent = stage1_cross_method(methods, args.z_step,
                                           args.mad_threshold, rep)

        rep.sub("1d. Per-file description")
        stats: dict[str, dict] = {}
        for mf in methods:
            rep.line(f"{mf.name}")
            stats[mf.name] = stage1_describe(mf, rep)
            rep.line()
            if stats[mf.name]["n_nan"] > 0:
                rep.warn(
                    "NAN_Z_PRESENT",
                    f"{mf.name}: {stats[mf.name]['n_nan']} of "
                    f"{stats[mf.name]['n_rows']} rows have blank or non-numeric Z. "
                    f"Those rows are carried through with Z_smoothed = NaN and are "
                    f"excluded from every statistic.",
                )
            if stats[mf.name]["n_tracks"] < MIN_TRACKS_FOR_MSD:
                rep.warn(
                    "TOO_FEW_TRACKS",
                    f"{mf.name}: {stats[mf.name]['n_tracks']} tracks is fewer than the "
                    f"{MIN_TRACKS_FOR_MSD} needed for a stable MSD fit. The derived "
                    f"windows below rest on weak statistics.",
                )

        # ------------------------------------------------------------------
        results = {}
        failures: dict[str, str] = {}
        for mf in methods:
            st = stats[mf.name]
            rep.section(f"{mf.name}")
            warn_mark = len(rep.warnings)
            g_det = detected_spacing.get(mf.name)
            blk: list[tuple[str, str]] = [
                ("derivation stamp", f"{stamp}  ({DERIVATION_VERSION})"),
                ("input", os.path.abspath(mf.path)),
                ("rows / tracks / NaN Z", f"{st['n_rows']} / {st['n_tracks']} / {st['n_nan']}"),
                ("Z range (span)", f"{st['z_range']:.6g}"),
                ("median track length / span", f"{st['median_track_length']:.0f} / "
                                               f"{st['median_span']:.0f} frames"),
                ("--z-step supplied", f"{args.z_step:.6g}"),
                ("detected lattice spacing", "none (continuous)" if g_det is None
                                             else f"{g_det:.6g}"),
                ("z-step verification", zstep_status),
            ]

            # -------------------------- Stage 2 --------------------------
            rep.sub("Stage 2 -- strict provisional pass (output NOT used as the result)")
            w2 = next_odd_at_least(STAGE2_WINDOW_TRACK_FRACTION * st["median_track_length"])
            if w2 < MIN_HAMPEL_WINDOW:
                rep.line(f"  derived Stage 2 window {w2} raised to the {MIN_HAMPEL_WINDOW}-point "
                         f"structural minimum")
                w2 = MIN_HAMPEL_WINDOW
            rep.line(f"  window    : {w2} frames "
                     f"(= {STAGE2_WINDOW_TRACK_FRACTION:g} x measured median track length "
                     f"{st['median_track_length']:.0f}, rounded up to odd)")
            rep.line(f"  threshold : {STAGE2_MAD_THRESHOLD:g} MAD")
            rep.line(f"  MAD floor : {args.z_step:.6g} (the supplied --z-step)")
            flags2 = run_hampel(mf, mf.z, w2, STAGE2_MAD_THRESHOLD, args.z_step)
            z_stage2 = mf.z.copy()
            z_stage2[flags2] = np.nan
            n2 = int(flags2.sum())
            rep.line(f"  provisionally removed: {n2} of {st['n_rows']} points "
                     f"({100.0 * n2 / max(st['n_rows'], 1):.3f}%)")
            rep.line("  Purpose: keep gross outliers out of the Stage 3 fit. This output is "
                     "discarded afterwards.")
            blk += [
                ("Stage 2 window / threshold", f"{w2} frames / {STAGE2_MAD_THRESHOLD:g} MAD "
                                               f"/ floor {args.z_step:.6g}"),
                ("Stage 2 removed", f"{n2} ({n2 / max(st['n_rows'], 1):.3%}) -- provisional"),
            ]

            covsig = covariance_sigma(mf, z_stage2)
            rep.line()
            rep.line("  Model-free localisation noise (cross-check, NOT used in any "
                     "derivation):")
            rep.line("    For independent localisation noise, two successive displacements "
                     "share an endpoint, so")
            rep.line("    Cov(delta_i, delta_i+1) = -sigma^2. This assumes no MSD model, no "
                     "power law and no fit range,")
            rep.line("    and it is computed before the fit so it survives a fit that fails.")
            rep.line(f"    successive-displacement pairs (frames f, f+1, f+2 all present) = "
                     f"{covsig['n']}")
            rep.line(f"    Cov(delta_i, delta_i+1) = {covsig['cov']:.4f}")
            if covsig["sigma"] is None:
                rep.line("    sigma_cov = UNRESOLVABLE (the covariance is not negative, which "
                         "is inconsistent with")
                rep.line("      independent localisation noise on top of uncorrelated motion)")
            else:
                rep.line(f"    sigma_cov = sqrt(-Cov) = {covsig['sigma']:.4f} (Z units)")
            blk += [
                ("sigma (covariance)", f"{covsig['sigma']:.6g}" if covsig["sigma"] is not None
                                       else "UNRESOLVABLE (covariance not negative)"),
                ("Cov / n pairs", f"{covsig['cov']:.4f} / {covsig['n']}"),
            ]

            # -------------------------- Stage 3 --------------------------
            rep.sub("Stage 3 -- measure the motion timescale")
            try:
                msd_res = measure_timescale(mf, z_stage2, st, rep)
            except DerivationError as exc:
                record_method_failure(rep, failures, mf.name, "DERIVATION_FAILED", str(exc))
                rep.line("  No plot can be produced: the MSD could not be characterised.")
                blk += [("STATUS", "FAILED -- DERIVATION_FAILED (MSD not characterised)"),
                        ("failure", str(exc))]
                parameter_block(rep, blk, rep.warnings[warn_mark:],
                                f"{mf.name}  [FAILED]")
                continue

            rep.line("  MSD(tau) (Z units^2), pooled across tracks, present-pairs only:")
            rep.line(f"    {'lag':>5s} {'MSD':>14s} {'pairs':>9s}")
            for lag in range(1, msd_res.max_usable_lag + 1):
                mark = "  (in fit)" if lag <= msd_res.fit_lags else ""
                rep.line(f"    {lag:5d} {msd_res.msd[lag]:14.6g} "
                         f"{int(msd_res.pairs[lag]):9d}{mark}")

            if covsig["sigma"] is not None and msd_res.msd[1] > 0:
                share = 2.0 * covsig["sigma"] ** 2 / msd_res.msd[1]
                covsig["share"] = share
                rep.line()
                rep.line(f"  Noise share of MSD(1): 2*sigma_cov^2 / MSD(1) = "
                         f"2*{covsig['sigma'] ** 2:.4f} / {msd_res.msd[1]:.4f} = {share:.2%}")
                rep.line(f"    That percentage is the quantitative justification for smoothing "
                         f"at all: it is how much of")
                rep.line(f"    the frame-to-frame variation is measurement rather than "
                         f"movement.")
                rep.line(f"    Read the two terms differently. MSD(1) is a mean of SQUARES and "
                         f"is highly sensitive to the")
                rep.line(f"    Stage 2 settings -- on this data it moves by over 100% between "
                         f"reasonable Stage 2 choices,")
                rep.line(f"    because a handful of retained outliers dominate a mean of "
                         f"squares. sigma_cov over the same")
                rep.line(f"    range of settings moves by a few percent. The covariance "
                         f"estimator is comparatively robust;")
                rep.line(f"    the share, inheriting MSD(1)'s denominator, is not. Trust "
                         f"sigma_cov more than the percentage.")

            if msd_res.pairs[msd_res.fit_lags] < MIN_PAIRS_AT_MAX_FIT_LAG:
                rep.warn(
                    "TOO_FEW_PAIRS_FOR_MSD",
                    f"{mf.name}: only {int(msd_res.pairs[msd_res.fit_lags])} displacement "
                    f"pairs at the top fit lag {msd_res.fit_lags} (minimum "
                    f"{MIN_PAIRS_AT_MAX_FIT_LAG}). The MSD fit, and every window derived "
                    f"from it, rests on weak statistics.",
                )

            try:
                derived = derive_windows(mf, msd_res, st, args.noise_margin, rep)
                boot = bootstrap_alpha(mf, z_stage2, msd_res.fit_lags, args.noise_margin)
                rep.line()
                rep.line("  UNCERTAINTY ON alpha, AND ON THE WINDOW IT IMPLIES:")
                if not boot:
                    rep.line("    Not estimable (too few tracks, or too few replicates "
                             "converged). The window below is")
                    rep.line("    a point estimate with no interval around it.")
                else:
                    lo_p, hi_p = ALPHA_CI_PERCENTILES
                    rep.line(f"    Method: bootstrap over TRACKS, {boot['n']} of "
                             f"{ALPHA_BOOTSTRAP_REPLICATES} replicates converged, "
                             f"{hi_p - lo_p:.0f}% percentile interval, seed "
                             f"{ALPHA_BOOTSTRAP_SEED}.")
                    rep.line(f"    Tracks are the independent units: the MSD is pooled across "
                             f"them, while within a track the")
                    rep.line(f"    lags are strongly correlated, which rules out a "
                             f"residual-based interval and makes a profile")
                    rep.line(f"    likelihood need a noise model this correlation makes "
                             f"intractable. The bootstrap needs none.")
                    rep.line(f"    The fit range is HELD FIXED at 1..{msd_res.fit_lags}, so "
                             f"this interval is conditional on that")
                    rep.line(f"    range; the dependence on where the fit stops is the "
                             f"fit-range table's job, not this one.")
                    rep.line(f"    alpha      = {msd_res.alpha:.4f}  "
                             f"[{boot['alpha_lo']:.4f}, {boot['alpha_hi']:.4f}]")
                    rep.line(f"    W_smooth   = {derived.smoothing_window}  "
                             f"[{boot['window_lo']}, {boot['window_hi']}]   "
                             f"(requirement {derived.smoothing_required_raw:.4f} "
                             f"[{boot['w_lo']:.4f}, {boot['w_hi']:.4f}])")
                    if boot["n_unresolvable"]:
                        rep.line(f"    {boot['n_unresolvable']} of {boot['n']} replicates gave "
                                 f"a non-positive intercept, i.e. no resolvable noise floor.")
                    ra = ((boot['alpha_hi'] - boot['alpha_lo']) / msd_res.alpha
                          if msd_res.alpha > 0 else float('nan'))
                    rw = ((boot['w_hi'] - boot['w_lo']) / derived.smoothing_required_raw
                          if derived.smoothing_required_raw > 0 else float('nan'))
                    base = derived.smoothing_required_uncorrected
                    if base > 1:
                        w_a_lo = base ** (1.0 / boot['alpha_hi'])
                        w_a_hi = base ** (1.0 / boot['alpha_lo'])
                        ra_only = (w_a_hi - w_a_lo) / derived.smoothing_required_raw
                    else:
                        ra_only = float('nan')
                    rep.line(f"    relative interval width: alpha {ra:.3f}, window {rw:.3f} "
                             f"(window is {rw / ra:.2f}x alpha's)")
                    if np.isfinite(ra_only) and ra_only <= 100:
                        rep.line(f"    of which the 1/alpha exponent alone contributes "
                                 f"{ra_only:.3f}, an amplification of {ra_only / ra:.2f}x on")
                        rep.line(f"    alpha's own width; the remainder is sigma and Gamma "
                                 f"varying too.")
                    else:
                        rep.line(f"    The 1/alpha exponent alone cannot be quoted here: the "
                                 f"alpha interval reaches "
                                 f"{boot['alpha_lo']:.4f}, where 1/alpha diverges and the")
                        rep.line(f"    implied window runs away without bound. That divergence "
                                 f"is itself the finding -- an alpha")
                        rep.line(f"    this poorly determined cannot support an exponent.")
                    if boot["window_lo"] != boot["window_hi"]:
                        rep.warn(
                            "WINDOW_NOT_DETERMINED",
                            f"{mf.name}: the smoothing window is not determined to a single "
                            f"value by this data. The {hi_p - lo_p:.0f}% bootstrap interval on "
                            f"alpha ({boot['alpha_lo']:.4f}, {boot['alpha_hi']:.4f}) maps to "
                            f"windows {boot['window_lo']}..{boot['window_hi']}, spanning more "
                            f"than one odd window. The point estimate "
                            f"{derived.smoothing_window} is reported and used, but it is more "
                            f"precise than the data warrants; anything downstream that is "
                            f"sensitive at that level should be checked across the interval.",
                        )

                altw = alternative_window(covsig["sigma"], msd_res.msd[1],
                                          args.noise_margin, msd_res.alpha)
                tx = measure_transfer_exponents(mf, msd_res.alpha)
                rep.line()
                rep.line("  ALTERNATIVE WINDOW (report only -- NOT used, nothing below depends "
                         "on it):")
                rep.line("    Transfer functions of the gap-aware moving average at lag 1, "
                         "MEASURED ON THIS RUN by")
                rep.line(f"    laying synthetic series over this method's own frames and gaps "
                         f"(seed {TRANSFER_PROBE_SEED},")
                rep.line(f"    windows {list(TRANSFER_PROBE_WINDOWS)}):")
                if tx:
                    rep.line(f"      noise  ~ W^{tx['noise_exp']:+.3f}   "
                             f"(structurally expected {tx['noise_exp_expected']:+.2f})")
                    rep.line(f"      motion ~ W^{tx['motion_exp']:+.3f}   "
                             f"(structurally expected alpha-2 = "
                             f"{tx['motion_exp_expected']:+.2f}; fBm at Hurst "
                             f"{tx['hurst']:.3f})")
                else:
                    rep.line("      not measurable on this method's track structure; the "
                             "structural expectations are")
                    rep.line("      noise ~ W^-2 and motion ~ W^(alpha-2), used below "
                             "unverified for this run.")
                rep.line("    The noise does NOT divide by W. Successive windows overlap in "
                         "W-1 of their W points, so")
                rep.line("    their difference is (1/W)*(eps[t+1+h] - eps[t-h]) and its "
                         "variance falls as 1/W^2. The")
                rep.line("    motion falls as W^(alpha-2): the same difference spans W frames "
                         "of displacement, which")
                rep.line("    accumulate as W^alpha.")
                rep.line("    Hence ratio = 2*sigma^2 / (Gamma * W^alpha), and requiring "
                         "ratio <= f gives")
                rep.line("      W >= (2*sigma^2 / (f*Gamma))^(1/alpha).")
                rep.line("    The exponent 1/alpha is not optional. It vanishes at alpha = 1 "
                         "and dominates away from it;")
                rep.line("    the formula currently IN USE omits it and is correct only at "
                         "alpha = 1.")
                if altw is None:
                    rep.line("    Not computable: sigma_cov is unresolvable.")
                elif altw["window"] is None:
                    rep.line(f"    Not computable: MSD(1) - 2*sigma_cov^2 = "
                             f"{altw['gamma_meas']:.4f} is not positive, so there is no "
                             f"measured motion component at lag 1.")
                else:
                    rep.line(f"    sigma_cov = {covsig['sigma']:.4f}; noise 2*sigma_cov^2 = "
                             f"{altw['noise']:.4f}; MSD(1) = {msd_res.msd[1]:.4f}")
                    rep.line(f"    measured motion Gamma_meas = MSD(1) - 2*sigma_cov^2 = "
                             f"{altw['gamma_meas']:.4f}")
                    rep.line(f"    f = 1/k^2 = {altw['f']:.4f};  2*sigma^2/(f*Gamma) = "
                             f"{altw['base']:.4f}")
                    rep.line(f"    raised to 1/alpha = {1.0 / msd_res.alpha:.4f}  ->  W >= "
                             f"{altw['w_req']:.4f}  =>  W_alt = {altw['window']}")
                    rep.line(f"    (without the 1/alpha correction it would be "
                             f"{next_odd_at_least(altw['w_req_uncorrected'])}; the current rule "
                             f"in use gives {derived.smoothing_window})")
                rep.line("    This does NOT remove a free parameter. f is exactly 1/k^2 and "
                         "plays the identical role;")
                rep.line("    the rule is renamed, not made parameter-free. What it does "
                         "change is WHERE the inputs")
                rep.line("    come from: sigma and Gamma are both measured here, so the window "
                         "stops depending on the")
                rep.line("    MSD model and the fit range. That is a robustness gain, not a "
                         "reduction in free choices.")
            except DerivationError as exc:
                record_method_failure(rep, failures, mf.name, "DERIVATION_FAILED", str(exc))
                if args.plot:
                    png = plot_diagnostics(mf, msd_res, None, args.noise_margin, args.out)
                    rep.line(f"  Wrote {png} (MSD panel only; no window was derived, so there "
                             f"is no sensitivity curve)")
                blk += [("STATUS", "FAILED -- DERIVATION_FAILED (no window derivable)"),
                        ("failure", str(exc))]
                parameter_block(rep, blk, rep.warnings[warn_mark:],
                                f"{mf.name}  [FAILED]")
                continue

            blk += [
                ("MSD model", "2*sigma^2 + Gamma*tau^alpha"),
                ("MSD usable lags", f"1..{msd_res.max_usable_lag}"),
                ("MSD fit range", f"1..{msd_res.fit_lags}  (rel residual "
                                  f"{msd_res.rel_residual:.4f})"),
                ("MSD(1)", f"{msd_res.msd[1]:.6g}"),
                ("2*sigma^2 (intercept)", f"{msd_res.intercept:.6g}"),
                ("sigma (fitted)", f"{msd_res.sigma:.6g}" if msd_res.sigma_resolvable
                                   else "UNRESOLVABLE (intercept not positive)"),
                ("noise share of MSD(1)", f"{covsig['share']:.2%}" if covsig.get("share")
                                          is not None else "n/a"),
                ("Gamma", f"{msd_res.gamma:.6g}"),
                ("alpha (Stage-2 cleaned)", f"{msd_res.alpha:.4f}  "
                                            f"[{describe_alpha(msd_res.alpha)}]"
                 + (f"  95% CI [{boot['alpha_lo']:.4f}, {boot['alpha_hi']:.4f}]"
                    if boot else "  (CI not estimable)")),
                ("alpha (no rejection)",
                 f"{msd_res.alpha_no_rejection:.4f} (own plateau, lags "
                 f"1..{msd_res.alpha_no_rejection_range})"
                 if msd_res.alpha_no_rejection is not None
                 else f"NOT AVAILABLE -- {msd_res.alpha_no_rejection_reason}"),
                ("sqrt(Gamma) motion scale", f"{math.sqrt(msd_res.gamma):.6g}"
                                             if msd_res.gamma > 0 else "n/a"),
                ("confinement lag", "NOT REACHED" if msd_res.confinement_lag is None
                                    else f"{msd_res.confinement_lag} frames"),
            ]

            rep.line()
            fitrange = fit_range_sensitivity(msd_res.msd, msd_res.max_usable_lag,
                                             msd_res.fit_lags, args.noise_margin, rep)

            if abs(msd_res.alpha - 1.0) > ALPHA_WARN_DEVIATION:
                rep.warn(
                    "ANOMALOUS_DIFFUSION",
                    f"{mf.name}: the fitted anomalous exponent is alpha = {msd_res.alpha:.4f}, "
                    f"which departs from 1 by more than the stated {ALPHA_WARN_DEVIATION:g}. "
                    f"The motion is {describe_alpha(msd_res.alpha).lower()}, so a linear "
                    f"MSD model would have been misspecified here: it would have absorbed the "
                    f"curvature into the intercept and the slope, making the localisation "
                    f"noise and the motion scale both depend on where the fit range stopped. "
                    f"The fitted model is used instead. See the fit-range sensitivity table "
                    f"for what that changes.",
                )

            if covsig["sigma"] is not None and msd_res.sigma_resolvable:
                hi = max(covsig["sigma"], msd_res.sigma)
                lo = min(covsig["sigma"], msd_res.sigma)
                if lo <= 0 or hi / lo > SIGMA_ESTIMATOR_DISAGREE_RATIO:
                    rep.warn(
                        "SIGMA_ESTIMATORS_DISAGREE",
                        f"{mf.name}: the two localisation-noise estimates differ by more than "
                        f"the stated factor of {SIGMA_ESTIMATOR_DISAGREE_RATIO:g}. Fitted "
                        f"sigma = {msd_res.sigma:.4f} (from the MSD intercept, dependent on "
                        f"the model and the fit range); covariance sigma = "
                        f"{covsig['sigma']:.4f} (model-free, from successive-displacement "
                        f"covariance). Ratio {hi / lo:.2f}. They measure the same quantity, so "
                        f"a gap this large means at least one of them is not measuring what it "
                        f"claims. The FITTED value is what the windows are derived from.",
                    )
            elif covsig["sigma"] is not None and not msd_res.sigma_resolvable:
                rep.warn(
                    "SIGMA_ESTIMATORS_DISAGREE",
                    f"{mf.name}: the fitted sigma is UNRESOLVABLE (the MSD intercept is "
                    f"{msd_res.intercept:.4g}, not positive), but the model-free covariance "
                    f"estimator resolves sigma = {covsig['sigma']:.4f}, accounting for "
                    f"{covsig.get('share', float('nan')):.1%} of MSD(1). The model says there "
                    f"is no noise floor to measure; a model-free estimator on the same data "
                    f"says there is. The window derivation uses the FITTED value and therefore "
                    f"asks for no smoothing. Treat that as a statement about the fit, not "
                    f"about the data.",
                )

            if not msd_res.sigma_resolvable:
                rep.warn(
                    "SIGMA_UNRESOLVABLE",
                    f"{mf.name}: the fitted MSD intercept is {msd_res.intercept:.6g}, which is "
                    f"not positive, so the localisation noise sigma cannot be resolved from "
                    f"this data. sigma is reported as 0 and the smoothing-window derivation "
                    f"consequently asks for no smoothing. No value has been substituted.",
                )
            if msd_res.confinement_lag is None:
                rep.warn(
                    "CONFINEMENT_UNBOUNDED",
                    f"{mf.name}: MSD(tau) does not flatten within lags 1.."
                    f"{msd_res.max_usable_lag}. The confinement timescale is unbounded by "
                    f"this data, so NO upper cap on the smoothing window can be derived. "
                    f"The smoothing window below is set by the noise criterion alone.",
                )
            if msd_res.sigma_resolvable and np.isfinite(st["z_range"]) and st["z_range"] > 0:
                frac = msd_res.sigma / st["z_range"]
                if frac > SIGMA_RANGE_WARN_FRACTION:
                    rep.warn(
                        "NOISE_DOMINATED",
                        f"{mf.name}: localisation noise sigma = {msd_res.sigma:.6g} is "
                        f"{frac:.1%} of the total observed Z range "
                        f"({st['z_range']:.6g}), above the "
                        f"{SIGMA_RANGE_WARN_FRACTION:.0%} threshold. This data is "
                        f"noise-dominated; smoothed values should be treated with caution.",
                    )

            # ------------------- window selection --------------------
            w_hampel = derived.hampel_window
            w_smooth = derived.smoothing_window
            rep.line()
            if args.hampel_window is not None:
                rep.line(f"  Hampel window OVERRIDDEN: derived {derived.hampel_window} -> "
                         f"user-supplied {args.hampel_window}")
                w_hampel = args.hampel_window
            if args.smooth_window is not None:
                rep.line(f"  Smoothing window OVERRIDDEN: derived {derived.smoothing_window} -> "
                         f"user-supplied {args.smooth_window}")
                w_smooth = args.smooth_window

            # Describes the window actually in use, so an override that avoids the
            # problem is not warned about and an override that creates one is.
            median_span = st["median_span"]
            if median_span > 0 and w_hampel >= median_span:
                rep.warn(
                    "HAMPEL_WINDOW_SPANS_TRACK",
                    f"{mf.name}: the Hampel window IN USE ({w_hampel} frames"
                    + (f", user-supplied; derived was {derived.hampel_window}"
                       if args.hampel_window is not None else ", derived")
                    + f") is at or above the median track span ({median_span:.0f} frames). "
                    f"Over a typical track the window covers all available data, so the "
                    f"median and MAD become whole-track statistics and the filter loses its "
                    f"local character: it now rejects points that differ from the track as a "
                    f"whole rather than from their neighbourhood. Unlike the smoothing-window "
                    f"case this is a degradation rather than a collapse to a constant, so "
                    f"processing continues. No value has been substituted. Set "
                    f"--hampel-window below {median_span:.0f} if a local window is wanted.",
                )
            elif (median_span > 0 and args.hampel_window is not None
                    and derived.hampel_window >= median_span):
                rep.line(f"  NOTE: the DERIVED Hampel window ({derived.hampel_window} frames) "
                         f"was at or above the median track span ({median_span:.0f} frames) "
                         f"and would have raised HAMPEL_WINDOW_SPANS_TRACK; the override "
                         f"({w_hampel}) is local and no warning applies.")

            # A derived smoothing window at or above the median track span collapses
            # typical tracks to their mean. That is a hard failure for this method, not
            # a note. An explicit --smooth-window is the user saying they intend it, so
            # it bypasses the check. The check itself is applied further below, after the
            # sensitivity table has been printed: that table is the evidence the user
            # needs in order to choose an override, and the design requires it to appear
            # for every method regardless of the outcome.
            degenerate: Optional[MethodFailure] = None
            try:
                check_smoothing_window_usable(
                    mf, st, w_smooth if args.smooth_window is None
                    else derived.smoothing_window
                )
            except MethodFailure as exc:
                degenerate = exc
            if degenerate is not None and args.smooth_window is not None:
                rep.line(f"  NOTE: the DERIVED smoothing window "
                         f"({derived.smoothing_window} frames) was at or above the median "
                         f"track span ({st['median_span']:.0f} frames) and would have been "
                         f"refused; the explicit --smooth-window {args.smooth_window} "
                         f"overrides that refusal.")
                degenerate = None

            plural = lambda w: "frame" if w == 1 else "frames"
            rep.line(f"  IN USE: Hampel window = {w_hampel} {plural(w_hampel)}, "
                     f"smoothing window = {w_smooth} {plural(w_smooth)}")
            if mf.name in inconsistent:
                rep.line()
                rep.rule("*")
                rep.line(f"  DO NOT USE THESE WINDOWS. {mf.name} was flagged in Stage 1c as "
                         f"disagreeing with the")
                rep.line(f"  consensus of the other methods. The windows above are derived from "
                         f"its sigma, Gamma and")
                rep.line(f"  alpha, so they inherit that inconsistency: they describe whatever "
                         f"this method measured,")
                rep.line(f"  which the other methods contradict. The numbers are reported in "
                         f"full and the derivation is")
                rep.line(f"  unchanged -- they are simply not a sound basis for smoothing "
                         f"parameters. Resolve the")
                rep.line(f"  disagreement first, or take windows from a method that is "
                         f"consistent with the consensus.")
                rep.line(f"  ")
                rep.line(f"  AND THE EXPONENT AMPLIFIES IT. This method's alpha is "
                         f"{msd_res.alpha:.4f}, so the window requirement")
                rep.line(f"  is raised to 1/alpha = {1.0 / msd_res.alpha:.4f}. An exponent that "
                         f"is itself a product of the")
                rep.line(f"  sampling problem is being used as a POWER, so any error in it is "
                         f"amplified, not merely")
                rep.line(f"  carried through: the uncorrected requirement "
                         f"{derived.smoothing_required_uncorrected:.4f} becomes "
                         f"{derived.smoothing_required_raw:.4f}.")
                rep.line(f"  Note this alpha is NOT an over-extended-fit artifact -- it sits on "
                         f"a proper stability")
                rep.line(f"  plateau with sigma stable across it. It is genuinely anomalous for "
                         f"THIS method while every")
                rep.line(f"  consensus-consistent method is near 1, which is itself further "
                         f"evidence of the sampling")
                rep.line(f"  problem rather than a reason to trust the number. This is the "
                         f"least trustworthy window in")
                rep.line(f"  the report.")
                rep.rule("*")
            if w_smooth == 1:
                rep.line("  A smoothing window of 1 means the derivation asks for NO smoothing: "
                         "the measured noise is already below the single-frame motion scale by "
                         "more than the required factor. Z_smoothed then equals Z with rejected "
                         "points removed.")

            if args.smooth_window is None:
                rep.line()
                rep.line("  HOW THIS SMOOTHING WINDOW WAS SET -- read before using it.")
                rep.line("  It is NOT a measured quantity. It depends on THREE arbitrary "
                         "choices:")
                _e = 2.0 / msd_res.alpha
                rep.line(f"    1. k, the noise margin (--noise-margin, in use "
                         f"{args.noise_margin:g}). The window scales as k^(2/alpha) = "
                         f"k^{_e:.3f}:")
                rep.line(f"       at k = {args.noise_margin / 2:g} it would be about "
                         f"{next_odd_at_least(derived.smoothing_required_raw * 0.5 ** _e)}, at "
                         f"k = {args.noise_margin * 2:g} about "
                         f"{next_odd_at_least(derived.smoothing_required_raw * 2.0 ** _e)}, "
                         f"against {w_smooth} here.")
                rep.line(f"       (k^2 exactly only at alpha = 1.) k can therefore be moved to "
                         f"reach almost any window,")
                rep.line(f"       and any downstream speed.")
                rep.line(f"    2. The MSD fit range. See the fit-range sensitivity table above: "
                         f"the window varies by")
                rep.line(f"       "
                         + (f"{fitrange['anomalous_ratio']:.2f}x across fit ranges under the "
                            f"model in use."
                            if fitrange["anomalous_ratio"] else
                            "an amount that could not be computed here."))
                rep.line(f"    3. The Stage 2 cleaning parameters (window {w2}, "
                         f"{STAGE2_MAD_THRESHOLD:g} MAD). sigma, Gamma and alpha are all")
                rep.line(f"       measured on Stage-2-cleaned data"
                         + (f"; alpha alone moves {msd_res.alpha:.4f} -> "
                            f"{msd_res.alpha_no_rejection:.4f} without rejection."
                            if msd_res.alpha_no_rejection is not None else "."))
                if msd_res.confinement_lag is None:
                    rep.line(f"    MSD(tau) never flattened, so no confinement timescale exists "
                             f"in this data and no upper")
                    rep.line(f"    cap could be derived. Nothing measured bounds the window from "
                             f"above at all.")
                else:
                    rep.line(f"    A confinement lag of {msd_res.confinement_lag} frames does cap "
                             f"the window from above; that cap")
                    rep.line(f"    is measured, the rest is not.")
                rep.line(f"    The sensitivity table below is the evidence for judging whether "
                         f"the window in use is")
                rep.line(f"    right. None of the three choices is self-justifying.")

            # -------------------------- Stage 4 --------------------------
            rep.sub("Stage 4 -- reject and smooth")
            flags4 = run_hampel(mf, mf.z, w_hampel, args.mad_threshold, args.z_step)
            n4 = int(flags4.sum())
            n_finite = int(np.sum(np.isfinite(mf.z)))
            rate = n4 / max(n_finite, 1)
            rep.line(f"  Hampel: window {w_hampel} frames, threshold {args.mad_threshold:g} MAD, "
                     f"MAD floor {args.z_step:.6g}")
            rep.line(f"  outliers flagged: {n4} of {n_finite} finite points ({rate:.3%})")
            rep.line("  Flagged points are set to NaN and REMOVED. They are not interpolated, "
                     "forward-filled or imputed.")
            if rate > OUTLIER_RATE_WARN_FRACTION:
                rep.warn(
                    "HIGH_OUTLIER_RATE",
                    f"{mf.name}: {rate:.2%} of points were rejected, above the stated "
                    f"{OUTLIER_RATE_WARN_FRACTION:.0%} threshold. At this rate the rejection is "
                    f"a symptom of a data-quality problem, not a filtering step; investigate "
                    f"the acquisition or the sampling method rather than raising the threshold.",
                )

            rep.line()
            ptrack = per_track_outlier_breakdown(mf, flags4, rep)

            z_rejected = mf.z.copy()
            z_rejected[flags4] = np.nan

            rep.line()
            sens = sensitivity_table(mf, mf.z, z_rejected, st, w_smooth, rep)
            rep.line("  (This table is printed regardless of which window was chosen; it is the "
                     "evidence for the choice. 'no rejection' smooths the raw Z; "
                     "'with rejection' smooths after Stage 4a removal.)")

            if degenerate is not None:
                record_method_failure(rep, failures, mf.name,
                                      "SMOOTHING_WINDOW_DEGENERATE", str(degenerate))
                if args.plot:
                    png = plot_diagnostics(mf, msd_res, sens, args.noise_margin, args.out)
                    rep.line(f"  Wrote {png}")
                blk += [("STATUS", "FAILED -- SMOOTHING_WINDOW_DEGENERATE"),
                        ("failure", str(degenerate))]
                parameter_block(rep, blk, rep.warnings[warn_mark:],
                                f"{mf.name}  [FAILED]")
                continue

            z_smoothed = gap_aware_moving_average_all(mf, z_rejected, w_smooth)

            rep.line()
            v_raw, n_raw_pairs = mean_abs_dz_per_frame(mf, mf.z)
            v_fin, n_fin_pairs = mean_abs_dz_per_frame(mf, z_smoothed)
            label_raw = "raw Z"
            label_fin = f"rejected + smoothed (W={w_smooth})"
            rep.line("  Speed proxy (mean |dZ| between consecutive available points, "
                     "normalised per frame):")
            rep.line(f"    {label_raw:32s} : {v_raw:.6g} per frame "
                     f"({n_raw_pairs} intervals)")
            rep.line(f"    {label_fin:32s} : {v_fin:.6g} per frame "
                     f"({n_fin_pairs} intervals)")
            if args.frame_interval is not None:
                rep.line(f"    {label_raw:32s} : "
                         f"{v_raw / args.frame_interval:.6g} per second "
                         f"(--frame-interval {args.frame_interval:g} s, report only)")
                rep.line(f"    {label_fin:32s} : "
                         f"{v_fin / args.frame_interval:.6g} per second")

            # -------------------------- output ---------------------------
            n_defined = int(np.sum(np.isfinite(z_smoothed)))
            out_df = mf.raw_text.copy()
            z_raw_text = mf.raw_text["Z"].to_numpy()
            smoothed_orig = z_smoothed[mf.inverse]
            flags_orig = flags4[mf.inverse]
            out_df["Z_raw"] = z_raw_text
            out_df["Z_smoothed"] = ["" if not np.isfinite(v) else f"{v:.6f}"
                                    for v in smoothed_orig]
            out_df["outlier_flag"] = flags_orig
            # Provenance, carried in the file itself so a reader who never opens the
            # report can still tell which derivation produced it and whether the
            # method it came from was flagged as unusable.
            out_df["run_stamp"] = stamp
            note = build_derivation_note(mf.name, mf.name in inconsistent, rep.warnings)
            out_df["derivation_note"] = note
            stem = os.path.splitext(mf.name)[0]
            out_path = os.path.join(args.out, f"{stem}_smoothed.csv")
            out_df.to_csv(out_path, index=False)
            rep.line()
            rep.line(f"  Wrote {out_path}")
            rep.line(f"    columns: {', '.join(out_df.columns)}")
            rep.line(f"    run_stamp = {stamp} on every row")
            rep.line(f"    derivation_note = "
                     + (f"'{note}'" if note else "empty (no check fired for this method)")
                     + " on every row")
            rep.line(f"    Z_smoothed defined at {n_defined} of {st['n_rows']} rows "
                     f"({100.0 * n_defined / max(st['n_rows'], 1):.2f}%); "
                     f"undefined where Z was blank or the point was rejected.")
            rep.line("    The original Track_ID, Frame, X, Y and Z columns are reproduced "
                     "verbatim from the input text; nothing was overwritten.")

            if args.plot:
                png = plot_diagnostics(mf, msd_res, sens, args.noise_margin, args.out)
                rep.line(f"  Wrote {png}")

            blk += [
                ("crossover lag tau*", f"{derived.crossover_lag:.4f} frames"),
                ("k (--noise-margin)", f"{args.noise_margin:g}"),
                ("W_smooth requirement", f"{derived.smoothing_required_raw:.4f} "
                                         f"(corrected, before odd-rounding)"),
                ("W_smooth req uncorrected",
                 f"{derived.smoothing_required_uncorrected:.4f} "
                 f"(alpha=1 special case; W would be "
                 f"{next_odd_at_least(derived.smoothing_required_uncorrected)})"),
                ("W_alt (model-free, unused)",
                 f"{altw['window']} (w_req {altw['w_req']:.4f}, f=1/k^2={altw['f']:.4f})"
                 if altw and altw["window"] else "not computable"),
                ("W_smooth 95% CI", f"[{boot['window_lo']}, {boot['window_hi']}] "
                                    f"(requirement [{boot['w_lo']:.4f}, {boot['w_hi']:.4f}])"
                 if boot else "not estimable"),
                ("W_smooth derived / in use", f"{derived.smoothing_window} / {w_smooth}"
                    + ("  (OVERRIDDEN)" if args.smooth_window is not None else "")),
                ("W_hampel derived / in use", f"{derived.hampel_window} / {w_hampel}"
                    + ("  (OVERRIDDEN)" if args.hampel_window is not None else "")),
                ("fit-range spread (live, in cap)",
                 (f"lin {fitrange['linear_ratio']:.2f}x" if fitrange['linear_ratio'] else "n/a")
                 + " / "
                 + (f"anom {fitrange['anomalous_ratio']:.2f}x" if fitrange['anomalous_ratio']
                    else "n/a")),
                ("fit-range spread (no cap)",
                 (f"lin {fitrange['linear_ratio_uncapped']:.2f}x"
                  if fitrange['linear_ratio_uncapped'] else "n/a")
                 + " / "
                 + (f"anom {fitrange['anomalous_ratio_uncapped']:.2f}x"
                    if fitrange['anomalous_ratio_uncapped'] else "n/a")
                 + "  -- counterfactual, removed by the cap"),
                ("outliers", f"{n4} of {n_finite} ({rate:.3%})"),
                ("per-track outlier rate",
                 f"median {ptrack.get('median_rate', float('nan')):.2%}, "
                 f"max {ptrack.get('max_rate', float('nan')):.2%}, "
                 f"{ptrack.get('zero', 0)} clean tracks, "
                 f"{ptrack.get('n_named', 0)} above "
                 f"{PER_TRACK_OUTLIER_NAME_RATE:.0%} "
                 f"({ptrack.get('named_share', 0.0):.1%} of outliers)"),
                ("Z_smoothed defined", f"{n_defined} of {st['n_rows']} "
                                       f"({n_defined / max(st['n_rows'], 1):.2%})"),
                ("speed raw / smoothed", f"{v_raw:.6g} / {v_fin:.6g} per frame"
                    + (f"  ({v_raw / args.frame_interval:.6g} / "
                       f"{v_fin / args.frame_interval:.6g} per second)"
                       if args.frame_interval is not None else "")),
                ("STATUS", "OK -- WINDOWS NOT SOUND: method flagged as inconsistent "
                           "with the consensus of the others (Stage 1c); do not use them"
                           if mf.name in inconsistent else "OK"),
                ("output", os.path.abspath(out_path)),
            ]
            parameter_block(rep, blk, rep.warnings[warn_mark:], mf.name)

            results[mf.name] = dict(
                stage2_window=w2, stage2_removed=n2,
                derived_hampel=derived.hampel_window, derived_smooth=derived.smoothing_window,
                used_hampel=w_hampel, used_smooth=w_smooth,
                outliers=n4, outlier_rate=rate, sigma=msd_res.sigma,
                gamma=msd_res.gamma, alpha=msd_res.alpha,
                sigma_cov=covsig['sigma'],
                w_req=derived.smoothing_required_raw,
                w_alt=(altw['window'] if altw else None),
                w_alt_req=(altw['w_req'] if altw else None),
                out_path=out_path,
            )

        # ------------------------------------------------------------------
        rep.section("SUMMARY")
        rep.line("  Gamma is deliberately absent: its units are Z^2 per frame^alpha, so with "
                 "a different alpha")
        rep.line("  per method the column would not be comparable across rows. It is in each "
                 "method's parameter block.")
        rep.line(f"  {'method':32s} {'sigma_fit':>10s} {'sigma_cov':>10s} {'alpha':>7s} "
                 f"{'W_hampel':>9s} {'W_smooth':>9s} {'outliers':>9s} {'rate':>8s}")
        for name, r in results.items():
            h = str(r["used_hampel"]) + ("*" if r["used_hampel"] != r["derived_hampel"] else "")
            s = str(r["used_smooth"]) + ("*" if r["used_smooth"] != r["derived_smooth"] else "")
            scov = f"{r['sigma_cov']:.4g}" if r['sigma_cov'] is not None else "n/a"
            rep.line(f"  {name[:32]:32s} {r['sigma']:10.4g} {scov:>10s} "
                     f"{r['alpha']:7.4f} {h:>9s} {s:>9s} {r['outliers']:9d} "
                     f"{r['outlier_rate']:8.2%}")
        for name in failures:
            rep.line(f"  {name[:32]:32s} {'FAILED -- no smoothed output written':>60s}")
        rep.line("  (* = user override; the derived value is recorded in that method's section)")

        rep.section("CROSS-METHOD AGREEMENT")
        eligible = [(n, r) for n, r in results.items() if n not in inconsistent]
        excluded = [(n, "flagged as inconsistent with the consensus (Stage 1c)")
                    for n in results if n in inconsistent]
        excluded += [(n, "derivation failed; no parameters to compare") for n in failures]
        rep.line("Derived parameters compared across the methods that are NOT flagged by the "
                 "consensus check.")
        rep.line("")
        rep.line("Why this matters: these methods sample the same tracks at the same frames "
                 "through different")
        rep.line("geometry, so their noise and motion estimates are arrived at independently. "
                 "Independent")
        rep.line("methods converging on the same derived parameters is the strongest available "
                 "evidence that")
        rep.line("those parameters reflect the DATA rather than the derivation rules -- a rule "
                 "artifact would")
        rep.line("have no reason to land in the same place from different inputs. Divergence "
                 "is the opposite:")
        rep.line("it means at least one number is being set by the procedure rather than by "
                 "what was measured.")
        rep.line("")
        rep.line("Flagged methods are excluded. Including a method already known to disagree "
                 "with the others")
        rep.line("would corrupt the comparison: its divergence is expected and would drown the "
                 "signal.")
        rep.line("")
        if len(eligible) < 2:
            rep.line(f"  Only {len(eligible)} eligible method(s); no cross-method comparison "
                     f"is possible.")
        else:
            rep.line(f"  {'method':32s} {'sigma_fit':>10s} {'sigma_cov':>10s} {'alpha':>7s} "
                     f"{'W_hampel':>9s} {'W_smooth':>9s} {'(w_req)':>9s} {'W_alt':>6s}")
            for name, r in eligible:
                rep.line(f"  {name[:32]:32s} {r['sigma']:10.4g} "
                         + (f"{r['sigma_cov']:10.4g}" if r['sigma_cov'] is not None
                            else f"{'n/a':>10s}")
                         + f" {r['alpha']:7.4f} {r['derived_hampel']:9d} "
                           f"{r['derived_smooth']:9d} {r['w_req']:9.4f} "
                         + (f"{r['w_alt']:6d}" if r['w_alt'] else f"{'n/a':>6s}"))
            rep.line("  (derived values, before any override. w_req is the continuous "
                     "requirement before")
            rep.line("   odd-rounding: two methods can display the same W_smooth while their "
                     "requirements differ")
            rep.line("   by 25% or more, so read agreement from w_req, not from the rounded "
                     "integer. W_alt is the")
            rep.line("   model-free alternative window, reported but not used.)")
            rep.line("")

            def spread_of(vals):
                vals = [v for v in vals if v is not None and v > 0]
                return (max(vals) / min(vals)) if len(vals) >= 2 else None

            s_fit = spread_of([r['sigma'] for _, r in eligible])
            s_cov = spread_of([r['sigma_cov'] for _, r in eligible])
            w_sm = [r['derived_smooth'] for _, r in eligible]
            w_ha = [r['derived_hampel'] for _, r in eligible]
            rep.line(f"  sigma_fit spread (max/min) : "
                     + (f"{s_fit:.3f}x" if s_fit else "not computable"))
            rep.line(f"  sigma_cov spread (max/min) : "
                     + (f"{s_cov:.3f}x" if s_cov else "not computable"))
            rep.line(f"  W_smooth across methods    : {min(w_sm)}..{max(w_sm)}"
                     + ("  (identical)" if min(w_sm) == max(w_sm) else ""))
            rep.line(f"  W_hampel across methods    : {min(w_ha)}..{max(w_ha)}"
                     + ("  (identical)" if min(w_ha) == max(w_ha) else ""))
            w_rq = [r['w_req'] for _, r in eligible if r['w_req'] > 0]
            if len(w_rq) >= 2:
                rep.line(f"  w_req spread (max/min)     : {max(w_rq) / min(w_rq):.4f}x  "
                         f"<- the real window agreement, free of rounding")
            rep.line("")
            rep.line("  READ THE W_smooth COLUMN WITH CARE. It is very nearly k-INVARIANT "
                     "and is therefore")
            rep.line("  NOT good evidence that the window is well determined. The requirement "
                     "is")
            rep.line("  W >= (2*k^2*sigma^2/Gamma)^(1/alpha), so k enters each method as "
                     "k^(2/alpha). When every method")
            rep.line("  has the same alpha this cancels EXACTLY out of any ratio between "
                     "them; when they differ it")
            rep.line("  cancels only approximately, leaving a weak residual dependence "
                     "through the spread in alpha.")
            rep.line("  Before the 1/alpha correction the cancellation was exact and the "
                     "spread was identical at every")
            rep.line("  k to four decimals. It is still far too weak to treat agreement here "
                     "as evidence about k.")
            rep.line("  Agreement here is strong evidence about sigma and alpha, which are "
                     "measured independently by")
            rep.line("  each method. It is structurally void as evidence about the smoothing "
                     "window, because no")
            rep.line("  value of k could make these methods disagree. The absolute window "
                     "still scales as k^2 and")
            rep.line("  k is still chosen by hand -- see 'HOW THIS SMOOTHING WINDOW WAS SET' "
                     "in each method's")
            rep.line("  section. Do not read cross-method agreement as showing that k does "
                     "not matter.")
        if excluded:
            rep.line("")
            rep.line("  Excluded from this comparison:")
            for name, why in excluded:
                rep.line(f"    {name[:40]:40s} {why}")

        rep.section("ALL WARNINGS RAISED")
        if rep.warnings:
            for w in rep.warnings:
                rep.line("  " + w)
        else:
            rep.line("  none")

        rep.section("METHOD FAILURES")
        if rep.failures:
            for f in rep.failures:
                rep.line("  " + f)
            rep.line()
            rep.line(f"  {len(failures)} of {len(methods)} methods produced no smoothed output. "
                     f"The remaining {len(results)} processed normally.")
        else:
            rep.line("  none")

        report_path = os.path.join(args.out, "zsmooth_parameters_report.txt")
        rep.write(report_path)
        print(f"\nParameters report written to {report_path}")
        return 3 if failures else 0

    except (FatalDataError, DerivationError) as exc:
        rep.line()
        rep.line("ERROR: " + str(exc))
        rep.line("Stopping. No output has been written for the remaining files.")
        try:
            if getattr(args, "out", None):
                os.makedirs(args.out, exist_ok=True)
                rep.write(os.path.join(args.out, "zsmooth_parameters_report.txt"))
        except Exception:
            pass
        print("\n" + "ERROR: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
