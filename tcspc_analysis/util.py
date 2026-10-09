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

    The width is measured above the baseline, and the two half-height
    crossings are interpolated between the bins on either side (counting whole
    bins read 4 to 20 % wide for an IRF of 30 to 60 ps at 4 ps per bin). A
    trace without a peak above its baseline gives 0. The peak position is the
    left edge of the highest bin, as before.

    The baseline is the median of the bins that hold the background: those
    between the first and the last bin with counts (a record is longer than
    the sync period, and its empty part would make any median 0) that lie
    more than three widths away from the peak. The width is therefore taken
    twice - first above the median of that whole stretch, to know where the
    peak is, then above the baseline. A peak with no such bins beside it has
    no background to subtract: its baseline is 0.
    """
    trace = np.asarray(trace, float)
    pk = int(np.argmax(trace))
    filled = np.nonzero(trace)[0]
    if not filled.size:
        return pk * res_ps, 0.0
    first, last = int(filled[0]), int(filled[-1])
    rough = _width_above(trace, pk, float(np.median(trace[first:last + 1])))
    if rough <= 0:
        return pk * res_ps, 0.0
    where = np.arange(first, last + 1)
    away = where[np.abs(where - pk) > 3.0 * rough]
    base = float(np.median(trace[away])) if away.size else 0.0
    return pk * res_ps, float(_width_above(trace, pk, base) * res_ps)


def _width_above(trace, pk, base):
    """Full width at half maximum of the peak at bin ``pk`` above ``base``,
    in bins (0 when the peak is not above it)."""
    if not trace[pk] > base:
        return 0.0
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
    return float(right - left)


def short_name(path, limit=24):
    """File name of ``path``, cut to ``limit`` characters for a status label."""
    name = os.path.basename(path)
    return name if len(name) <= limit else name[:limit - 3] + "..."
