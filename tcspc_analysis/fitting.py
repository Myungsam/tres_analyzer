"""Kinetics and global-analysis fit kernels."""
import numpy as np


# ==========================================================================
# 2d. Kinetics + Global-analysis kernels (ported from TA_Analyzer_rev5/ta_core)
# ==========================================================================
# These are the numerical heart of the two analysis windows: an IRF-convolved
# multi-exponential model, a single-trace fit (Kinetics) and a VARPRO global
# fit over the whole map (Global analysis).  They are lifted almost verbatim
# from ta_core.py but made self-contained - scipy is imported lazily so the
# viewer still starts (and the FLIM tab still runs) on a machine without it;
# the TensorFlow "backend" of the original global fit is dropped for plain
# NumPy.  Time is in ps here, matching TRESModel.times.
_erfc = _erfcx = _minimize = _least_squares = None


def _ensure_scipy():
    """Load scipy on first use; raise a friendly error if it is missing."""
    global _erfc, _erfcx, _minimize, _least_squares
    if _erfc is None:
        try:
            from scipy.special import erfc, erfcx
            from scipy.optimize import minimize, least_squares
        except ImportError as exc:      # pragma: no cover - depends on env
            raise FitInputError(
                "The Kinetics and Global-analysis tools need SciPy.\n"
                "Install it with:  pip install scipy") from exc
        _minimize, _least_squares = minimize, least_squares
        _erfcx = erfcx
        _erfc = erfc        # the guard above: set last, when the others are there


def exp_irf_conv(t, tau, t0, fwhm):
    """Exponential decay convolved with a Gaussian IRF (given as FWHM).

    Evaluated piecewise to dodge overflow: the asymptotic form far past t0,
    the full erfcx formula near t0, ~0 far before it. tau = +inf gives the
    step response, used for the constant (tau = infinity) offset term.
    """
    _ensure_scipy()                         # erfc / erfcx come from here
    sigma = fwhm / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    t_arr = np.asarray(t, float).ravel()
    dt = t_arr - t0
    c = np.zeros_like(dt)

    if np.isinf(tau):
        with np.errstate(invalid="ignore"):
            c = 0.5 * _erfc(-dt / (sigma * np.sqrt(2.0)))
        c[~np.isfinite(c)] = 0.0
        return c

    thresh = 5.0 * sigma + sigma ** 2 / tau
    near = np.abs(dt) <= thresh
    far_pos = dt > thresh

    if np.any(far_pos):
        dtf = dt[far_pos]
        c[far_pos] = np.exp(sigma ** 2 / (2.0 * tau ** 2) - dtf / tau)

    if np.any(near):
        dtn = dt[near]
        B = (sigma / tau - dtn / sigma) / np.sqrt(2.0)
        with np.errstate(invalid="ignore", over="ignore"):
            c[near] = 0.5 * np.exp(-dtn ** 2 / (2.0 * sigma ** 2)) * _erfcx(B)

    c[~np.isfinite(c)] = 0.0
    return c


def stretched_irf_conv(t, tau, beta, t0, fwhm, mode="numerical"):
    """Stretched exp exp(-((t-t0)/tau)^beta), optional Gaussian-IRF convolution.

    mode='skip' ignores the IRF (caller masks data within ~3 sigma of t0);
    mode='numerical' convolves on a fine uniform grid.
    """
    t = np.asarray(t, float).ravel()
    dt = t - t0
    out = np.zeros_like(dt)
    if (not np.isfinite(tau)) or tau <= 0 or \
       (not np.isfinite(beta)) or beta <= 0:
        return out

    def bare(x):
        with np.errstate(invalid="ignore"):
            xx = np.maximum(x, 0.0)
            return np.exp(-(xx / tau) ** beta) * (x >= 0).astype(float)

    mode = mode.lower()
    if mode == "skip":
        out = bare(dt)
    elif mode == "numerical":
        sigma = fwhm / (2.0 * np.sqrt(2.0 * np.log(2.0)))
        if not np.isfinite(sigma) or sigma <= 0:
            return bare(dt)
        step = min(0.2 * sigma, 0.05 * tau)
        if not np.isfinite(step) or step <= 0:
            step = 0.01
        t_lo = float(t.min()) - 5.0 * sigma
        t_hi = float(t.max()) + 5.0 * sigma
        n_grid = int(np.ceil((t_hi - t_lo) / step)) + 1
        if n_grid > 200_000:
            step = (t_hi - t_lo) / 200_000.0
            n_grid = 200_001
        t_grid = t_lo + np.arange(n_grid) * step
        f_grid = bare(t_grid - t0)
        n_k = int(np.ceil(5.0 * sigma / step))
        kx = np.arange(-n_k, n_k + 1) * step
        irf = np.exp(-kx ** 2 / (2.0 * sigma ** 2))
        irf /= irf.sum()
        c_grid = np.convolve(f_grid, irf, mode="same")
        out = np.interp(t, t_grid, c_grid, left=0.0, right=0.0)
    else:
        raise ValueError(f"stretched_irf_conv: unknown mode {mode!r}")

    out[~np.isfinite(out)] = 0.0
    return out


def _basis(t, tau, beta, stretch_on, t0, fwhm, has_inf, irf_mode, conv):
    """The model's columns, (N_t x k): one per component - a stretched one
    through stretched_irf_conv(), a plain exponential through ``conv`` - and,
    with ``has_inf``, the tau = inf offset last. ``conv(column, t, tau, t0,
    fwhm)`` is exp_irf_conv() behind a memo (_column_memo) inside a fit.
    Both kernels and build_ga_basis() build their model here."""
    n = len(tau)
    C = np.zeros((t.size, n + (1 if has_inf else 0)))
    for j in range(n):
        if stretch_on[j]:
            C[:, j] = stretched_irf_conv(t, tau[j], beta[j], t0, fwhm, irf_mode)
        else:
            C[:, j] = conv(j, t, tau[j], t0, fwhm)
    if has_inf:
        C[:, -1] = conv("inf", t, np.inf, t0, fwhm)
    return C


def build_ga_basis(t, tau_vec, t0, fwhm, has_inf):
    """(N_t x k) basis of IRF-convolved plain exponentials."""
    tau_vec = np.asarray(tau_vec, float).ravel()
    return _basis(np.asarray(t, float).ravel(), tau_vec, np.ones(tau_vec.size),
                  np.zeros(tau_vec.size, bool), t0, fwhm, has_inf, "",
                  lambda column, *args: exp_irf_conv(*args))


def _column_memo():
    """exp_irf_conv() that remembers, per model column, the curve of its last
    arguments. Inside a fit most columns keep theirs from one evaluation to
    the next - a fixed lifetime, the offset - as long as the IRF is fixed
    too; the same arguments give the same curve, so nothing changes but the
    work."""
    last = {}

    def conv(column, t, tau, t0, fwhm):
        key = (float(tau), float(t0), float(fwhm))
        hit = last.get(column)
        if hit is None or hit[0] != key:
            hit = last[column] = (key, exp_irf_conv(t, tau, t0, fwhm))
        return hit[1]

    return conv


# What both kernels hand to Nelder-Mead besides fatol (which follows the data).
NM_OPTIONS = {"xatol": 1e-8, "maxiter": 5000, "maxfev": 20000, "disp": False}


def _nm_fatol(data):
    """Nelder-Mead's stop tolerance on the loss, for a fit of ``data``.

    The loss is a sum of squared residuals, so its size follows the data: about
    1e-6 for absorbance changes, 1e8 and more for photon counts. A fixed 1e-10
    is then far below the rounding noise of the loss itself; the simplex could
    only stop when all its corners happened to give the very same number, and
    otherwise ran on to maxiter with nothing left to gain (seconds per fit,
    and which of the two happened changed with the numpy / scipy build).
    A 1e-12th of the data's own sum of squares is still well beyond the
    precision of any fitted parameter, and never tighter than the old 1e-10
    for small-valued data. Only finite values count, as in the loss.
    """
    data = np.asarray(data, float)
    data = data[np.isfinite(data)]
    return max(1e-10, 1e-12 * float(np.sum(np.square(data))))


def _amp_limit(D, masked):
    """The largest amplitude the global fit takes for a spectrum. Beyond it
    two components are cancelling each other.

    Counted in units of the data - a million times its largest value - so the
    same sample measured ten times longer ends in the same place. (Up to 1.5
    it was 1e10 counts, or 1e8 for a map with masked cells, whatever the
    counts: 1e10 is 5e6 x the largest value of one of the sample files, and
    its default Nelder-Mead fit ended exactly there.) ``masked`` says which of
    the two old limits applied; both are this one now.
    """
    finite = np.isfinite(D)
    return 1e6 * (float(np.max(np.abs(D[finite]))) if finite.any() else 1.0)


def _lsqminnorm(A, B):
    """Minimum-norm least-squares solve (numpy.linalg.lstsq wrapper)."""
    X, *_ = np.linalg.lstsq(A, B, rcond=None)
    return X


class FitInputError(ValueError):
    """The kernel refuses its input; the message is a sentence for the user."""


class FitStopped(Exception):
    """Raised inside a fit's objective when stop_check() reports a cancel."""


class GlobalAnalysisStopped(FitStopped):
    """The same, from the global fit."""


def _bin_width(t):
    t = np.asarray(t, float).ravel()
    return float(np.median(np.diff(t))) if t.size > 1 else 0.0


def _shortest_tau(fwhm, dt):
    """The shortest lifetime a fit may end on, in ps: a tenth of the time bin
    of the fitted data (``dt``).

    A component much shorter than the IRF has the IRF's own shape - scattered
    excitation light is one - and only its amplitude x lifetime is determined.
    The limit lets a fit hold such a component without the lifetime running
    off to 1e-10 ps and the amplitude to 1e15. (Up to 1.5 the global fit
    stopped at FWHM / 9.42 instead, which such a component does not fit under:
    on the two sample files the RMS was 10 to 50 % higher for it.)
    """
    return dt / 10.0


SHORTEST_TAU_IS = "a tenth of a time bin"
SHORTEST_TAU_MEANS = ("a component with the shape of the IRF itself (scattered "
                      "light, for instance); only amplitude x τ is determined.")


def _limits(t, fwhm_init, n_tau, n_beta, t0_free, fwhm_free):
    """Limits of a fit's free parameters, in the optimiser's own variables
    (log tau ..., log beta ..., t0, log FWHM): a list of (low, high), or None
    when the starting FWHM or the time axis leaves nothing to build them from
    (the fit then ends on _refuse()).

    tau:  _shortest_tau() ... 100 x the fit range
    beta: 0.001 ... 2
    t0:   free
    FWHM: a quarter of a time bin ... the fit range
    The optimisers are held inside these, so a parameter the data pull out of
    them stops ON the limit - and _fit_warnings() says so - instead of running
    on to a lifetime of 1e-10 ps with an amplitude of 1e15.
    """
    t = np.asarray(t, float).ravel()
    span = float(t.max() - t.min()) if t.size else 0.0
    dt = _bin_width(t)
    if not (np.isfinite(fwhm_init) and fwhm_init > 0 and span > 0 and dt > 0):
        return None
    shortest = _shortest_tau(fwhm_init, dt)
    if not (0 < shortest < 100.0 * span and dt / 4.0 < span):
        return None
    out = [(float(np.log(shortest)), float(np.log(100.0 * span)))] * n_tau
    out += [(float(np.log(1e-3)), float(np.log(2.0)))] * n_beta
    if t0_free:
        out.append((None, None))
    if fwhm_free:
        out.append((float(np.log(dt / 4.0)), float(np.log(span))))
    return out


def _into(x0, limits):
    """(x0 moved onto the nearest limit where it starts outside, lows, highs)."""
    lo = np.array([-np.inf if a is None else a for a, _ in limits])
    hi = np.array([np.inf if b is None else b for _, b in limits])
    return np.clip(x0, lo, hi), lo, hi


def _need_fwhm_start(fwhm_init, fwhm_fixed):
    """A FWHM that is to be fitted needs a start the limits can be built
    from. (A fixed one of 0 is refused at the end of the fit, by _refuse();
    a free one of 0 used to be fitted with no limits at all, or stopped
    scipy with a message of its own.)"""
    if not fwhm_fixed and not (np.isfinite(fwhm_init) and fwhm_init > 0):
        raise FitInputError(
            f"The IRF FWHM must start above 0 ps (it is {fwhm_init:g}).")


def _simplex(x0, lo, hi):
    """Nelder-Mead's first simplex inside the limits: scipy's own - every
    parameter in turn raised by 5 % (by 0.00025 from zero) - except that a
    step which would leave the limits is taken the other way.

    scipy cuts a corner outside the limits back onto the limit. For a start
    ON the lower limit with a negative value - the log of a lifetime below
    1 ps, i.e. time bins under 10 ps - 5 % "up" is further down, so that
    corner landed on the start itself and the parameter never moved: the fit
    ended on the limit and said it had converged.
    """
    x0 = np.asarray(x0, float)
    sim = np.tile(x0, (x0.size + 1, 1))
    for k in range(x0.size):
        step = 0.05 * x0[k] if x0[k] != 0 else 0.00025
        if not lo[k] <= x0[k] + step <= hi[k]:
            step = -step
        if not lo[k] <= x0[k] + step <= hi[k]:      # a range narrower than the step
            far = hi[k] if hi[k] - x0[k] >= x0[k] - lo[k] else lo[k]
            step = 0.5 * (far - x0[k])
        sim[k + 1, k] = x0[k] + step
    return sim


def _refuse(t, tau, beta, stretch_on, fwhm, tau_limits):
    """Say, in words, why the model is not evaluated at these parameters.

    These are the conditions under which the objectives below hand back a
    zero model. A fit that ENDS there (it started there and could not get
    away - a fixed value, or a start too far out) used to be returned as an
    all-zero "result"; the kernels call this instead. A start outside the
    limits that the optimiser recovers from is fitted as before. tau_limits
    adds the global fit's window for a lifetime: sigma/4 ... 100 x fit range.
    """
    span = float(t.max() - t.min()) if t.size else 0.0
    if not np.isfinite(fwhm) or fwhm <= 0:
        raise FitInputError(f"The IRF FWHM must be above 0 ps (it is {fwhm:g}).")
    if fwhm > span:
        raise FitInputError(f"The IRF FWHM ({fwhm:g} ps) is wider than the fit "
                         f"range ({span:g} ps).")
    shortest = _shortest_tau(fwhm, _bin_width(t))
    for i, tv in enumerate(tau):
        if not np.isfinite(tv) or tv <= 0:
            raise FitInputError(f"τ {i + 1} must be above 0 ps (it is {tv:g}).")
        if tau_limits and tv < shortest:
            raise FitInputError(
                f"τ {i + 1} = {tv:g} ps is below the shortest lifetime the "
                f"global fit allows ({shortest:.4g} ps = {SHORTEST_TAU_IS}).")
        if tau_limits and tv > 100.0 * span:
            raise FitInputError(
                f"τ {i + 1} = {tv:g} ps is more than 100 x the fit range "
                f"({span:g} ps).")
    for i, bv in enumerate(beta):
        if (stretch_on[i] or not tau_limits) and not (np.isfinite(bv) and 0 < bv <= 2):
            raise FitInputError(f"β {i + 1} must be above 0 and at most 2 (it is {bv:g}).")
    raise FitInputError("The model could not be evaluated at these parameters "
                        "(a component has no signal in the fit range).")


def _fit_warnings(t, tau, fwhm, A, data, tau_limits, fwhm_start=None, free=None):
    """What in a result should not be read as a fitted lifetime, in words.

    Nothing is changed by this - it only looks at the numbers: a lifetime on
    one of the fit's limits (tau_limits; they were built from fwhm_start, the
    FWHM the fit began with, and hold the lifetimes marked in ``free``), below
    one time bin, or beyond the fit range, and amplitudes far above the data
    (components cancelling each other).
    """
    notes = []
    t = np.asarray(t, float).ravel()
    span = float(t.max() - t.min())
    dt = float(np.median(np.diff(t))) if t.size > 1 else 0.0
    shortest = _shortest_tau(fwhm if fwhm_start is None else fwhm_start, dt)
    tau = np.asarray(tau, float).ravel()
    free = np.ones(tau.size, bool) if free is None else np.asarray(free, bool)
    for i, tv in enumerate(tau):
        name = f"τ {i + 1} = {tv:.4g} ps"
        limited = bool(tau_limits and free[i])
        if limited and tv <= shortest * (1.0 + 1e-3):
            notes.append(f"{name} is on the lower limit of the fit ({SHORTEST_TAU_IS} "
                         f"= {shortest:.4g} ps): " + SHORTEST_TAU_MEANS)
        elif limited and tv >= 100.0 * span * (1.0 - 1e-3):
            notes.append(f"{name} is on the upper limit of the fit (100 x the "
                         f"fit range): not a fitted lifetime.")
        elif tv < dt:
            notes.append(f"{name} is shorter than one time bin ({dt:.4g} ps): "
                         f"it cannot be resolved.")
        elif tv > span:
            notes.append(f"{name} is longer than the fit range ({span:.4g} ps): "
                         f"it acts as an offset.")
    data = np.asarray(data, float)
    top = float(np.nanmax(np.abs(data))) if np.isfinite(data).any() else 0.0
    A = np.asarray(A, float)
    if top > 0 and A.size and np.isfinite(A).any() \
            and float(np.nanmax(np.abs(A))) > 1e3 * top:
        notes.append("An amplitude is more than 1000 x the largest data value: "
                     "components are cancelling each other.")
    return notes


def _skip_warning(skipping, t0_fixed, fwhm_fixed):
    """IRF mode "skip" with a free t0 / FWHM, in words (or nothing)."""
    free = [name for name, fixed in (("t₀", t0_fixed), ("FWHM", fwhm_fixed)) if not fixed]
    if not (skipping and free):
        return []
    return [f'IRF mode "skip" leaves the delays under the IRF out of the fit, so '
            f'the data hardly determine {" and ".join(free)}: fix '
            f'{"them" if len(free) > 1 else "it"}, or use another IRF mode.']


def fit_global_analysis(D, t, tau_init, t0_init, fwhm_init,
                        tau_fixed, t0_fixed, fwhm_fixed, has_inf,
                        beta_init=None, beta_fixed=None, stretch_on=None,
                        irf_mode="numerical", stop_check=None, method="trf"):
    """VARPRO global fit of D (M wavelengths x N delays) to a shared set of
    IRF-convolved (optionally stretched) exponentials.

    Non-linear params (tau, beta, t0, FWHM) are optimised (TRF or Nelder-Mead);
    the per-wavelength amplitudes A are solved by linear least-squares inside
    every objective call.  stop_check(), if given, is polled each iteration and
    raising GlobalAnalysisStopped aborts cleanly.  Returns a dict with keys
    tau, beta, stretch_on, t0, fwhm, A (M x k), fit (M x N), info.
    """
    _ensure_scipy()
    tau_init = np.asarray(tau_init, float).ravel()
    tau_fixed = np.asarray(tau_fixed, bool).ravel()
    t_arr = np.asarray(t, float).ravel()
    D = np.asarray(D, float)
    M, N = D.shape

    n_nl = len(tau_init)
    if beta_init is None:
        beta_init = np.ones(n_nl)
    if stretch_on is None:
        stretch_on = np.zeros(n_nl, dtype=bool)
    if beta_fixed is None:
        beta_fixed = np.zeros(n_nl, dtype=bool)
    beta_init = np.asarray(beta_init, float).ravel()
    stretch_on = np.asarray(stretch_on, bool).ravel()
    beta_fixed = np.asarray(beta_fixed, bool).ravel()
    if (beta_init.size != n_nl or stretch_on.size != n_nl
            or beta_fixed.size != n_nl):
        raise ValueError("beta_init / stretch_on / beta_fixed length "
                         "must match tau_init")
    any_stretched = bool(stretch_on.any())
    _need_fwhm_start(fwhm_init, fwhm_fixed)
    if n_nl == 0 and not has_inf:
        raise FitInputError("Nothing to fit: no component and no τ = ∞ offset.")

    tau_cur = tau_init.copy()
    beta_cur = beta_init.copy()
    t0_cur = float(t0_init)
    fwhm_cur = float(fwhm_init)
    idx_free_tau = np.where(~tau_fixed)[0]
    n_free_tau = len(idx_free_tau)
    idx_free_beta = np.where(stretch_on & ~beta_fixed)[0]
    n_free_beta = len(idx_free_beta)

    x0_list = []
    if n_free_tau > 0:
        x0_list.extend(np.log(tau_init[idx_free_tau]).tolist())
    if n_free_beta > 0:
        x0_list.extend(np.log(np.maximum(beta_init[idx_free_beta], 1e-3)).tolist())
    if not t0_fixed:
        x0_list.append(float(t0_init))
    if not fwhm_fixed:
        x0_list.append(float(np.log(fwhm_init)))
    x0 = np.array(x0_list, float)
    limits = _limits(t_arr, fwhm_init, n_free_tau, n_free_beta,
                     not t0_fixed, not fwhm_fixed)
    if limits is not None and x0.size:
        x0, x_lo, x_hi = _into(x0, limits)

    dt_fit = _bin_width(t_arr)
    amp_limit = _amp_limit(D, not np.all(np.isfinite(D)))
    skip_mask_active = any_stretched and irf_mode.lower() == "skip"
    # "skip" leaves the delays under the IRF out of the loss. Which ones is
    # settled here, from the starting t0 and FWHM, as fit_single_trace does:
    # taken from the current values instead, a free t0 or FWHM could lower
    # the loss by sliding the IRF over the data and discarding it.
    skip_mask = np.ones(N, dtype=bool)
    if skip_mask_active:
        skip_mask = t_arr > (float(t0_init) + 3.0 * float(fwhm_init)
                             / (2.0 * np.sqrt(2.0 * np.log(2.0))))
        need = n_nl + (1 if has_inf else 0) + 1
        if int(skip_mask.sum()) < need:
            # as fit_single_trace does. (Up to 1.5 the whole range was fitted
            # instead, rise included, with a model that has no IRF - silently.)
            raise FitInputError(
                f"Not enough data points for the fit (need >= {need}, have "
                f'{int(skip_mask.sum())} after the IRF: mode "skip" leaves out '
                f"the delays up to t₀ + 3σ).")
    n_model = [0]                   # times the model was really evaluated
    n_cells = [D.size]              # residuals in the loss of the latest call

    conv = _column_memo()

    def objective(x):
        nonlocal t0_cur, fwhm_cur       # tau_cur / beta_cur are filled in place
        if stop_check is not None and stop_check():
            raise GlobalAnalysisStopped()
        n_cells[0] = D.size
        idx = 0
        for j in range(n_free_tau):
            tau_cur[idx_free_tau[j]] = np.exp(x[idx]); idx += 1
        for j in range(n_free_beta):
            beta_cur[idx_free_beta[j]] = np.exp(x[idx]); idx += 1
        if not t0_fixed:
            t0_cur = float(x[idx]); idx += 1
        if not fwhm_fixed:
            fwhm_cur = float(np.exp(x[idx])); idx += 1

        t_span = t_arr.max() - t_arr.min()
        if (np.any(tau_cur < _shortest_tau(fwhm_cur, dt_fit)) or
                np.any(tau_cur > 100.0 * t_span) or
                fwhm_cur <= 0 or fwhm_cur > t_span or
                (any_stretched and (np.any(beta_cur[stretch_on] <= 0)
                                    or np.any(beta_cur[stretch_on] > 2)))):
            k_cols = n_nl + (1 if has_inf else 0)
            return 1e30, np.zeros((M, k_cols)), np.zeros((M, N))

        n_model[0] += 1
        # each column is recomputed only when its own arguments changed
        C = _basis(t_arr, tau_cur, beta_cur, stretch_on, t0_cur, fwhm_cur,
                   has_inf, irf_mode, conv)
        col_norms = np.sqrt(np.nansum(C ** 2, axis=0))
        if np.any(col_norms < 1e-12) or not np.all(np.isfinite(C)):
            return 1e30, np.zeros((M, C.shape[1])), np.zeros((M, N))

        col_mask = skip_mask

        k_cols = C.shape[1]
        As = np.zeros((M, k_cols))
        fit_M = np.zeros((M, N))
        if np.all(np.isfinite(D)):
            Cs = C[col_mask, :]
            Ds = D[:, col_mask]
            try:
                At = _lsqminnorm(Cs, Ds.T)         # (k x M)
            except GlobalAnalysisStopped:
                raise
            except Exception:
                return 1e30, As, fit_M
            if not np.all(np.isfinite(At)) or np.max(np.abs(At)) > amp_limit:
                return 1e30, As, fit_M
            As = At.T
            fit_M = As @ C.T
        else:
            for ii in range(M):
                row = D[ii, :]
                mm = np.isfinite(row) & col_mask
                if np.count_nonzero(mm) <= k_cols:
                    continue
                try:
                    ai = _lsqminnorm(C[mm, :], row[mm])
                except GlobalAnalysisStopped:
                    raise
                except Exception:
                    continue
                if not np.all(np.isfinite(ai)) or np.max(np.abs(ai)) > amp_limit:
                    continue
                As[ii, :] = ai
                fit_M[ii, :] = (ai.reshape(1, -1) @ C.T).ravel()

        R = D - fit_M
        if skip_mask_active:
            R = R[:, col_mask]
        mfin = np.isfinite(R)
        loss = float(np.sum(R[mfin] ** 2)) if np.any(mfin) else 1e30
        if np.any(mfin):            # masked delays and NaN cells are not in it
            n_cells[0] = int(mfin.sum())
        return loss, As, fit_M

    method_lc = str(method).lower()
    if method_lc in ("trf", "levenberg-marquardt", "lm", "least_squares"):
        method_used = "trf"
    elif method_lc in ("nm", "nelder-mead", "neldermead", "nelder_mead"):
        method_used = "nm"
    else:
        raise ValueError(f"fit_global_analysis: unknown method {method!r}")

    if x0.size == 0:
        loss, A_out, fit_out = objective(np.array([]))
        iters = 0
        n_fev = 1
        init_loss = loss
        init_cells = n_cells[0]
        verdict = (True, 0, "No free parameter: amplitudes only.")
    elif method_used == "trf":
        init_loss, _, _ = objective(x0)
        init_cells = n_cells[0]

        def _residuals(x):
            _, _, fit_M = objective(x)
            R = D - fit_M
            R = np.where(np.isfinite(R), R, 0.0)
            R[:, ~skip_mask] = 0.0
            return R.ravel()

        res = _least_squares(_residuals, x0, method="trf",
                             xtol=1e-8, ftol=1e-10, gtol=1e-8, max_nfev=5000,
                             **({} if limits is None else {"bounds": (x_lo, x_hi)}))
        loss, A_out, fit_out = objective(res.x)
        iters = int(getattr(res, "nfev", 0))
        n_fev = int(getattr(res, "nfev", 0))
        verdict = (bool(res.success), int(res.status), str(res.message))
    else:
        init_loss, _, _ = objective(x0)
        init_cells = n_cells[0]
        res = _minimize(lambda x: objective(x)[0], x0, method="Nelder-Mead",
                        bounds=limits,
                        options=dict(NM_OPTIONS, fatol=_nm_fatol(D),
                                     **({} if limits is None else
                                        {"initial_simplex": _simplex(x0, x_lo, x_hi)})))
        loss, A_out, fit_out = objective(res.x)
        iters = int(res.nit)
        n_fev = int(getattr(res, "nfev", iters))
        verdict = (bool(res.success), int(res.status), str(res.message))

    if loss >= 1e30:        # the fit ended on a point the model is not evaluated at
        _refuse(t_arr, tau_cur, beta_cur, stretch_on, fwhm_cur, True)

    # "iters" is what the exports have always quoted (TRF: its nfev, which
    # leaves out the Jacobian's evaluations; Nelder-Mead: iterations);
    # n_objective is the number of model evaluations actually made.
    info = {
        "rss": loss, "iters": iters, "nfev": n_fev, "method": method_used,
        "success": verdict[0], "status": verdict[1], "message": verdict[2],
        "n_objective": n_model[0],
        "warnings": _fit_warnings(t_arr, tau_cur, fwhm_cur, A_out, D, True,
                                  fwhm_start=float(fwhm_init), free=~tau_fixed)
        + _skip_warning(skip_mask_active, t0_fixed, fwhm_fixed),
        "rms": float(np.sqrt(loss / n_cells[0])),
        "initialLoss": init_loss,
        "initialRMS": float(np.sqrt(init_loss / init_cells)),
        "irf_mode": irf_mode if any_stretched else "closed-form",
    }
    return {
        "tau": tau_cur.copy(), "beta": beta_cur.copy(),
        "stretch_on": stretch_on.copy(), "t0": t0_cur, "fwhm": fwhm_cur,
        "A": A_out, "fit": fit_out, "info": info,
    }


def compute_eads_from_dads(DADS, tau_vec, has_inf):
    """Convert parallel DADS to sequential EADS (1 -> 2 -> ... -> N).

    Species are ordered by ascending tau. Returns (EADS, tau_sorted, Bmat).
    The sequential model needs every rate to be different: two equal
    lifetimes raise ValueError (the matrix below would divide by zero).
    """
    tau_vec = np.asarray(tau_vec, float).ravel()
    sort_idx = np.argsort(tau_vec)
    tau_sorted = tau_vec[sort_idx]
    n_decay = len(tau_sorted)
    same = np.where(np.diff(tau_sorted) <= 1e-9 * tau_sorted[1:])[0]
    if same.size:
        raise ValueError(
            "EADS need a different lifetime for every component; two of "
            f"them are τ = {tau_sorted[int(same[0])]:.6g} ps.")

    if has_inf:
        k_vec = np.concatenate([1.0 / tau_sorted, [0.0]])
        perm = np.concatenate([sort_idx, [n_decay]])
    else:
        k_vec = 1.0 / tau_sorted
        perm = sort_idx

    n = len(k_vec)
    Bmat = np.zeros((n, n))
    for ii in range(n):
        prod_k = 1.0 if ii == 0 else float(np.prod(k_vec[:ii]))
        for jj in range(ii + 1):
            denom = 1.0
            for mm in range(ii + 1):
                if mm != jj:
                    denom *= (k_vec[mm] - k_vec[jj])
            Bmat[ii, jj] = prod_k / denom

    DADS_perm = DADS[:, perm]
    try:
        EADS = np.linalg.solve(Bmat.T, DADS_perm.T).T
        if not np.all(np.isfinite(EADS)):
            raise np.linalg.LinAlgError("non-finite")
    except np.linalg.LinAlgError:
        EADS = DADS_perm @ np.linalg.pinv(Bmat)
    return EADS, tau_sorted, Bmat


def fit_single_trace(t, y, *, tau_init, tau_fixed,
                     beta_init=None, beta_fixed=None, stretch_on=None,
                     t0_init=0.0, t0_fixed=True,
                     fwhm_init=0.15, fwhm_fixed=True,
                     has_inf=False, irf_mode="skip", stop_check=None):
    """Fit one kinetic trace y(t) to a sum of (possibly stretched) exponentials
    convolved with a Gaussian IRF.  Linear amplitudes solved by VARPRO, the
    non-linear params by Nelder-Mead over a log parameterisation.  Returns a
    dict with keys tau, beta, t0, fwhm, A, fit, residual, info.
    stop_check(), if given, is polled before every evaluation of the model;
    when it returns true the fit ends with FitStopped.
    """
    _ensure_scipy()
    t = np.asarray(t, float).ravel()
    y = np.asarray(y, float).ravel()
    if t.shape != y.shape:
        raise ValueError(f"shape mismatch: t {t.shape} vs y {y.shape}")

    n_nl = int(len(tau_init))
    tau_init = np.asarray(tau_init, float).ravel()
    tau_fixed = np.asarray(tau_fixed, bool).ravel()
    if beta_init is None:
        beta_init = np.ones(n_nl)
    if beta_fixed is None:
        beta_fixed = np.zeros(n_nl, dtype=bool)
    if stretch_on is None:
        stretch_on = np.zeros(n_nl, dtype=bool)
    beta_init = np.asarray(beta_init, float).ravel()
    beta_fixed = np.asarray(beta_fixed, bool).ravel()
    stretch_on = np.asarray(stretch_on, bool).ravel()

    _need_fwhm_start(fwhm_init, fwhm_fixed)
    mask = np.isfinite(y)
    if irf_mode.lower() == "skip" and stretch_on.any():
        sig = fwhm_init / (2.0 * np.sqrt(2.0 * np.log(2.0)))
        mask = mask & (t > t0_init + 3.0 * sig)

    n_min = n_nl + (1 if has_inf else 0) + 1
    if int(mask.sum()) < n_min:
        raise FitInputError(
            f"Not enough data points for the fit "
            f"(need >= {n_min}, have {int(mask.sum())} after masking).")

    free_tau_idx = np.where(~tau_fixed)[0]
    free_beta_idx = np.where(stretch_on & ~beta_fixed)[0]

    x0 = []
    if free_tau_idx.size:
        x0.extend(np.log(np.maximum(tau_init[free_tau_idx], 1e-12)))
    if free_beta_idx.size:
        x0.extend(np.log(np.maximum(beta_init[free_beta_idx], 1e-3)))
    if not t0_fixed:
        x0.append(float(t0_init))
    if not fwhm_fixed:
        x0.append(float(np.log(max(fwhm_init, 1e-12))))
    x0 = np.asarray(x0, float)
    # the limits of the free parameters; a fixed lifetime is the user's own
    limits = _limits(t, fwhm_init, free_tau_idx.size, free_beta_idx.size,
                     not t0_fixed, not fwhm_fixed)
    if limits is not None and x0.size:
        x0, x_lo, x_hi = _into(x0, limits)

    cur = {"tau": tau_init.copy(), "beta": beta_init.copy(),
           "t0": float(t0_init), "fwhm": float(fwhm_init)}
    t_span = float(t.max() - t.min()) if t.size else 1.0
    n_cols = n_nl + (1 if has_inf else 0)
    conv = _column_memo()

    def unpack(x):
        i = 0
        if free_tau_idx.size:
            cur["tau"][free_tau_idx] = np.exp(x[i:i + free_tau_idx.size])
            i += free_tau_idx.size
        if free_beta_idx.size:
            cur["beta"][free_beta_idx] = np.exp(x[i:i + free_beta_idx.size])
            i += free_beta_idx.size
        if not t0_fixed:
            cur["t0"] = float(x[i]); i += 1
        if not fwhm_fixed:
            cur["fwhm"] = float(np.exp(x[i])); i += 1

        if (not np.all(np.isfinite(cur["tau"])) or np.any(cur["tau"] <= 0)
                or not np.all(np.isfinite(cur["beta"]))
                or np.any(cur["beta"] <= 0) or np.any(cur["beta"] > 2)
                or not np.isfinite(cur["fwhm"]) or cur["fwhm"] <= 0
                or cur["fwhm"] > t_span):
            cur["refused"] = True
            return (np.zeros(n_cols), np.zeros_like(t))
        cur["refused"] = False

        Mb = _basis(t, cur["tau"], cur["beta"], stretch_on, cur["t0"],
                    cur["fwhm"], has_inf, irf_mode, conv)

        try:
            A = _lsqminnorm(Mb[mask, :], y[mask])
        except Exception:
            A = np.zeros(n_cols)
        if not np.all(np.isfinite(A)):
            A = np.zeros(n_cols)
        return A, Mb @ A

    def loss(x):
        if stop_check is not None and stop_check():
            raise FitStopped()
        _, fv = unpack(x)
        r = (y - fv)[mask]
        L = float(np.sum(r ** 2))
        return L if np.isfinite(L) else 1e30

    if x0.size:
        res = _minimize(loss, x0, method="Nelder-Mead", bounds=limits,
                        options=dict(NM_OPTIONS, fatol=_nm_fatol(y[mask]),
                                     **({} if limits is None else
                                        {"initial_simplex": _simplex(x0, x_lo, x_hi)})))
        A_final, fit_v = unpack(res.x)
        iters = int(res.nit)
        fval = float(res.fun)
        verdict = (bool(res.success), int(res.status), str(res.message), int(res.nfev))
    else:
        A_final, fit_v = unpack(np.array([]))
        iters = 0
        fval = float(np.sum(((y - fit_v)[mask]) ** 2))
        verdict = (True, 0, "No free parameter: amplitudes only.", 1)

    if cur["refused"]:      # the fit ended on a point the model is not evaluated at
        _refuse(t, cur["tau"], cur["beta"], stretch_on, cur["fwhm"], False)

    res_v = y - fit_v
    res_v[~mask] = np.nan
    rms = float(np.sqrt(np.nanmean(res_v[mask] ** 2))) if mask.any() else 0.0
    return {
        "tau": cur["tau"].copy(), "beta": cur["beta"].copy(),
        "t0": cur["t0"], "fwhm": cur["fwhm"], "A": A_final,
        "fit": fit_v, "residual": res_v,
        "info": {"iters": iters, "fval": fval, "rms": rms,
                 "mask": mask, "irf_mode": irf_mode,
                 "success": verdict[0], "status": verdict[1],
                 "message": verdict[2], "nfev": verdict[3],
                 "warnings": _fit_warnings(t, cur["tau"], cur["fwhm"], A_final,
                                           y[mask], limits is not None,
                                           fwhm_start=float(fwhm_init),
                                           free=~tau_fixed)
                 + _skip_warning(irf_mode.lower() == "skip" and stretch_on.any(),
                                 t0_fixed, fwhm_fixed)},
    }
