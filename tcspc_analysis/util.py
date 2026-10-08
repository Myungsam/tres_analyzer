"""Small helpers shared by the model and the windows."""
import os

import numpy as np


# ==========================================================================
# 2. Helpers
# ==========================================================================
def wavelength_to_rgb(wl):
    """Approximate visible-spectrum colour of a wavelength, for the axis ribbon.
    Outside 380-830 nm there is no such colour: a neutral grey."""
    if not 380 <= wl <= 830:
        return (0.55, 0.55, 0.55)
    r = g = b = 0.0
    if wl < 440:
        r, b = -(wl - 440) / 60.0, 1.0
    elif wl < 490:
        g, b = (wl - 440) / 50.0, 1.0
    elif wl < 510:
        g, b = 1.0, -(wl - 510) / 20.0
    elif wl < 580:
        r, g = (wl - 510) / 70.0, 1.0
    elif wl < 645:
        r, g = 1.0, -(wl - 645) / 65.0
    else:
        r = 1.0

    f = 1.0
    if wl < 420:
        f = 0.25 + 0.75 * (wl - 380) / 40.0
    elif wl > 700:
        f = 0.25 + 0.75 * (830 - wl) / 130.0

    gamma = 0.85
    return tuple(float(np.clip(max(c, 0.0) * f, 0, 1) ** gamma) for c in (r, g, b))


def fwhm_of(trace, res_ps):
    """Peak position (ps) and FWHM (ps) of a histogram, at native resolution.

    The width is measured above the baseline - the median of the trace: an
    IRF is short, so most of its bins hold only background - and the two
    half-height crossings are interpolated between the bins on either side
    (counting whole bins read 4 to 20 % wide for an IRF of 30 to 60 ps at
    4 ps per bin). A trace without a peak above its baseline gives 0. The
    peak position is the left edge of the highest bin, as before.
    """
    trace = np.asarray(trace, float)
    pk = int(np.argmax(trace))
    base = float(np.median(trace))
    if not trace[pk] > base:
        return pk * res_ps, 0.0
    half = base + (trace[pk] - base) / 2.0
    lo = pk
    while lo > 0 and trace[lo] > half:
        lo -= 1
    hi = pk
    while hi < len(trace) - 1 and trace[hi] > half:
        hi += 1

    def crossing(outer, inner):
        # between a bin at or below half height and its neighbour above it;
        # a walk that ran into the end of the trace stops there
        if outer == inner or trace[outer] > half:
            return float(outer)
        return outer + (inner - outer) * (half - trace[outer]) / (trace[inner] - trace[outer])

    left = crossing(lo, min(lo + 1, pk))
    right = crossing(hi, max(hi - 1, pk))
    return pk * res_ps, float((right - left) * res_ps)


def solvent_mismatch(sample, solvent):
    """Compare a solvent .phu against the sample it is to be subtracted from.

    Returns (errors, notes), two lists of messages. The subtraction is bin for
    bin, with no resampling, so any error - a different number of curves,
    wavelength list, time resolution or bin count - means the solvent has to be
    refused. A note (a different acquisition time) is only reported: the scale
    factor can make up for it.
    """
    errors, notes = [], []
    if solvent["ncurves"] != sample["ncurves"]:
        errors.append(f'number of curves: {solvent["ncurves"]} (solvent) vs '
                      f'{sample["ncurves"]} (sample)')
    # only comparable once the counts agree - allclose cannot broadcast otherwise
    elif not np.allclose(solvent["wls"], sample["wls"], rtol=0.0, atol=1e-6):
        errors.append("wavelength list differs from the sample")
    if solvent["nbins"] != sample["nbins"]:
        errors.append(f'time bins: {solvent["nbins"]:,} (solvent) vs '
                      f'{sample["nbins"]:,} (sample)')
    if not np.isclose(solvent["res_ps"], sample["res_ps"], rtol=1e-9, atol=0.0):
        errors.append(f'time resolution: {solvent["res_ps"]:g} ps (solvent) vs '
                      f'{sample["res_ps"]:g} ps (sample)')

    acq_v, acq_s = solvent.get("acq_ms"), sample.get("acq_ms")
    if acq_v and acq_s and acq_v != acq_s:
        notes.append(f"acquisition time per curve: {acq_v / 1000:g} s (solvent) vs "
                     f"{acq_s / 1000:g} s (sample)")
    return errors, notes


def short_name(path, limit=24):
    """File name of ``path``, cut to ``limit`` characters for a status label."""
    name = os.path.basename(path)
    return name if len(name) <= limit else name[:limit - 3] + "..."
