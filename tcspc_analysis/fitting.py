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
        _erfc, _erfcx = erfc, erfcx
        _minimize, _least_squares = minimize, least_squares


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


def build_ga_basis(t, tau_vec, t0, fwhm, has_inf):
    """(N_t x k) basis of IRF-convolved plain exponentials."""
    tau_vec = np.asarray(tau_vec, float).ravel()
    k = len(tau_vec) + (1 if has_inf else 0)
    t_arr = np.asarray(t, float).ravel()
    C = np.zeros((len(t_arr), k))
    for j, tau in enumerate(tau_vec):
        C[:, j] = exp_irf_conv(t_arr, tau, t0, fwhm)
    if has_inf:
        C[:, -1] = exp_irf_conv(t_arr, np.inf, t0, fwhm)
    return C


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
    shortest = fwhm / (2.0 * np.sqrt(2.0 * np.log(2.0))) / 4.0
    for i, tv in enumerate(tau):
        if not np.isfinite(tv) or tv <= 0:
            raise FitInputError(f"τ {i + 1} must be above 0 ps (it is {tv:g}).")
        if tau_limits and tv < shortest:
            raise FitInputError(
                f"τ {i + 1} = {tv:g} ps is below the shortest lifetime the "
                f"global fit allows for this IRF ({shortest:.4g} ps = FWHM / 9.42).")
        if tau_limits and tv > 100.0 * span:
            raise FitInputError(
                f"τ {i + 1} = {tv:g} ps is more than 100 x the fit range "
                f"({span:g} ps).")
    for i, bv in enumerate(beta):
        if (stretch_on[i] or not tau_limits) and not (np.isfinite(bv) and 0 < bv <= 2):
            raise FitInputError(f"β {i + 1} must be above 0 and at most 2 (it is {bv:g}).")
    raise FitInputError("The model could not be evaluated at these parameters "
                        "(a component has no signal in the fit range).")


def _fit_warnings(t, tau, fwhm, A, data, tau_limits):
    """What in a result should not be read as a fitted lifetime, in words.

    Nothing is changed by this - it only looks at the numbers: a lifetime on
    one of the global fit's internal limits (tau_limits), below one time bin,
    or beyond the fit range, and amplitudes far above the data (components
    cancelling each other).
    """
    notes = []
    t = np.asarray(t, float).ravel()
    span = float(t.max() - t.min())
    dt = float(np.median(np.diff(t))) if t.size > 1 else 0.0
    shortest = fwhm / (2.0 * np.sqrt(2.0 * np.log(2.0))) / 4.0
    for i, tv in enumerate(np.asarray(tau, float).ravel()):
        name = f"τ {i + 1} = {tv:.4g} ps"
        if tau_limits and tv <= shortest * (1.0 + 1e-3):
            notes.append(f"{name} is on the lower limit of the fit (FWHM / 9.42 "
                         f"= {shortest:.4g} ps): not a fitted lifetime.")
        elif tau_limits and tv >= 100.0 * span * (1.0 - 1e-3):
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

    skip_mask_active = any_stretched and irf_mode.lower() == "skip"
    n_model = [0]                   # times the model was really evaluated
    n_cells = [D.size]              # residuals in the loss of the latest call

    conv = _column_memo()

    def build_basis_local(tau_v, beta_v, t0_v, fwhm_v):
        # the columns of build_ga_basis(), each recomputed only when its own
        # arguments changed
        n_cols = n_nl + (1 if has_inf else 0)
        C = np.zeros((N, n_cols))
        for j in range(n_nl):
            if stretch_on[j]:
                C[:, j] = stretched_irf_conv(
                    t_arr, tau_v[j], beta_v[j], t0_v, fwhm_v, irf_mode)
            else:
                C[:, j] = conv(j, t_arr, tau_v[j], t0_v, fwhm_v)
        if has_inf:
            C[:, -1] = conv("inf", t_arr, np.inf, t0_v, fwhm_v)
        return C

    def objective(x):
        nonlocal tau_cur, beta_cur, t0_cur, fwhm_cur
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

        sigma_cur = fwhm_cur / (2.0 * np.sqrt(2.0 * np.log(2.0)))
        t_span = t_arr.max() - t_arr.min()
        if (np.any(tau_cur < sigma_cur / 4.0) or
                np.any(tau_cur > 100.0 * t_span) or
                fwhm_cur <= 0 or fwhm_cur > t_span or
                (any_stretched and (np.any(beta_cur[stretch_on] <= 0)
                                    or np.any(beta_cur[stretch_on] > 2)))):
            k_cols = n_nl + (1 if has_inf else 0)
            return 1e30, np.zeros((M, k_cols)), np.zeros((M, N))

        n_model[0] += 1
        C = build_basis_local(tau_cur, beta_cur, t0_cur, fwhm_cur)
        col_norms = np.sqrt(np.nansum(C ** 2, axis=0))
        if np.any(col_norms < 1e-12) or not np.all(np.isfinite(C)):
            return 1e30, np.zeros((M, C.shape[1])), np.zeros((M, N))

        col_mask = np.ones(N, dtype=bool)
        if skip_mask_active:
            col_mask = t_arr > (t0_cur + 3.0 * sigma_cur)
            if int(col_mask.sum()) <= C.shape[1]:
                col_mask = np.ones(N, dtype=bool)

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
            if not np.all(np.isfinite(At)) or np.max(np.abs(At)) > 1e10:
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
                if not np.all(np.isfinite(ai)) or np.max(np.abs(ai)) > 1e8:
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
            if skip_mask_active:
                cm = t_arr > (t0_cur + 3.0 * fwhm_cur / (2.0
                              * np.sqrt(2.0 * np.log(2.0))))
                if cm.any() and cm.sum() < N:
                    R[:, ~cm] = 0.0
            return R.ravel()

        res = _least_squares(_residuals, x0, method="trf",
                             xtol=1e-8, ftol=1e-10, gtol=1e-8, max_nfev=5000)
        loss, A_out, fit_out = objective(res.x)
        iters = int(getattr(res, "nfev", 0))
        n_fev = int(getattr(res, "nfev", 0))
        verdict = (bool(res.success), int(res.status), str(res.message))
    else:
        init_loss, _, _ = objective(x0)
        init_cells = n_cells[0]
        res = _minimize(lambda x: objective(x)[0], x0, method="Nelder-Mead",
                        options={"xatol": 1e-8, "fatol": _nm_fatol(D),
                                 "maxiter": 5000, "maxfev": 20000,
                                 "disp": False})
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
        "warnings": _fit_warnings(t_arr, tau_cur, fwhm_cur, A_out, D, True),
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

        Mb = np.zeros((t.size, n_cols))
        for j in range(n_nl):
            if stretch_on[j]:
                Mb[:, j] = stretched_irf_conv(
                    t, cur["tau"][j], cur["beta"][j],
                    cur["t0"], cur["fwhm"], irf_mode)
            else:
                Mb[:, j] = conv(j, t, cur["tau"][j], cur["t0"], cur["fwhm"])
        if has_inf:
            Mb[:, -1] = conv("inf", t, np.inf, cur["t0"], cur["fwhm"])

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
        res = _minimize(loss, x0, method="Nelder-Mead",
                        options={"xatol": 1e-8, "fatol": _nm_fatol(y[mask]),
                                 "maxiter": 5000, "maxfev": 20000,
                                 "disp": False})
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
                                           y[mask], False)},
    }
