"""Ambient-noise signal processing: H/V spectral ratio (Nakamura), PSD and spectral features.

Pure numpy/scipy so it can be unit-tested without network access.
SESAME (2004) criteria are implemented in a simplified but faithful form.
"""

from __future__ import annotations

import numpy as np
from scipy import signal, stats


def konno_ohmachi_weights(freqs: np.ndarray, centers: np.ndarray, b: float = 40) -> np.ndarray:
    """Konno-Ohmachi smoothing weights, shape (len(centers), len(freqs)), rows sum to 1."""
    with np.errstate(divide="ignore", invalid="ignore"):
        x = b * np.log10(freqs[None, :] / centers[:, None])
        w = (np.sin(x) / x) ** 4
    w[~np.isfinite(w)] = 0
    w[np.isclose(freqs[None, :], centers[:, None])] = 1.0
    w[:, freqs <= 0] = 0
    s = w.sum(axis=1, keepdims=True)
    return np.divide(w, s, out=np.zeros_like(w), where=s > 0)


def _windows(x: np.ndarray, n: int) -> np.ndarray:
    k = len(x) // n
    return x[: k * n].reshape(k, n)


def sesame_thresholds(f0: float) -> tuple[float, float]:
    """(epsilon(f0) as a fraction-free frequency threshold, theta(f0) amplitude-factor
    threshold)."""
    for lim, eps, theta in (
        (0.2, 0.25, 3.0),
        (0.5, 0.20, 2.5),
        (1.0, 0.15, 2.0),
        (2.0, 0.10, 1.78),
    ):
        if f0 < lim:
            return eps * f0, theta
    return 0.05 * f0, 1.58


def hv_ratio(
    z,
    n,
    e,
    fs: float,
    win_s: float = 60,
    fmin: float = 0.2,
    fmax: float = 20,
    b: float = 40,
    n_freq: int = 100,
    reject_factor: float = 2.0,
) -> dict:
    """Compute the H/V curve and its peak from three components of ambient noise."""
    m = min(len(z), len(n), len(e))
    z, n, e = (np.asarray(a[:m], dtype=float) for a in (z, n, e))
    nwin = int(win_s * fs)
    W = [signal.detrend(_windows(a, nwin), axis=1) for a in (z, n, e)]
    if W[0].shape[0] == 0:
        return {"n_windows_valid": 0}
    # reject windows with transients (RMS far above the median in any component)
    rms = np.stack([np.sqrt((w**2).mean(axis=1)) for w in W])
    med = np.median(rms, axis=1, keepdims=True)
    ok = (rms <= reject_factor * med).all(axis=0)
    if ok.sum() < 3:
        ok = np.ones_like(ok)
    W = [w[ok] for w in W]
    taper = signal.windows.tukey(nwin, 0.1)
    freqs = np.fft.rfftfreq(nwin, 1 / fs)
    centers = np.logspace(np.log10(fmin), np.log10(min(fmax, fs / 2.5)), n_freq)
    K = konno_ohmachi_weights(freqs, centers, b)
    spec = [np.abs(np.fft.rfft(w * taper, axis=1)) @ K.T for w in W]  # (nw, n_freq)
    H = np.sqrt((spec[1] ** 2 + spec[2] ** 2) / 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        hv = H / spec[0]
    hv = np.where(np.isfinite(hv) & (hv > 0), hv, np.nan)
    logc = np.nanmean(np.log(hv), axis=0)
    curve = np.exp(logc)
    sigA = np.exp(np.nanstd(np.log(hv), axis=0))  # multiplicative std factor
    i0 = int(np.nanargmax(curve))
    f0, a0 = float(centers[i0]), float(curve[i0])
    peaks_w = centers[np.nanargmax(hv, axis=1)]
    f0_std = float(np.std(peaks_w))
    nw = hv.shape[0]

    # second peak: highest local maximum at least a factor 1.5 away from f0 and with A > 2
    lm = signal.argrelmax(curve)[0]
    cand = [i for i in lm if (centers[i] > 1.5 * f0 or centers[i] < f0 / 1.5) and curve[i] > 2]
    f2 = float(centers[max(cand, key=lambda i: curve[i])]) if cand else np.nan

    # SESAME reliability (3 criteria)
    band = (centers > 0.5 * f0) & (centers < 2 * f0)
    lim = 2.0 if f0 > 0.5 else 3.0
    reliable = bool(f0 > 10 / win_s and win_s * nw * f0 > 200 and np.all(sigA[band] < lim))
    # SESAME clear peak (6 criteria, need >= 5)
    eps, theta = sesame_thresholds(f0)
    c1 = np.any(curve[(centers >= f0 / 4) & (centers <= f0)] < a0 / 2)
    c2 = np.any(curve[(centers >= f0) & (centers <= 4 * f0)] < a0 / 2)
    c3 = a0 > 2
    fp_hi = centers[np.nanargmax(curve * sigA)]
    fp_lo = centers[np.nanargmax(curve / sigA)]
    c4 = abs(fp_hi - f0) <= 0.05 * f0 and abs(fp_lo - f0) <= 0.05 * f0
    c5 = f0_std < eps
    c6 = sigA[i0] < theta
    clear = int(c1) + int(c2) + int(c3) + int(c4) + int(c5) + int(c6) >= 5
    return {
        "hv_f0_hz": f0,
        "hv_a0": a0,
        "hv_f0_std": f0_std,
        "hv_second_peak_hz": f2,
        "hv_sesame_reliable": reliable,
        "hv_sesame_clear_peak": bool(clear),
        "hv_curve": curve.astype(float).tolist(),
        "hv_freqs": centers.tolist(),
        "n_windows_valid": int(nw),
    }


def psd_db(x: np.ndarray, fs: float, seg_s: float = 60) -> tuple[np.ndarray, np.ndarray]:
    """Welch PSD in dB (rel. unit²/Hz)."""
    f, p = signal.welch(signal.detrend(np.asarray(x, float)), fs=fs, nperseg=int(seg_s * fs))
    with np.errstate(divide="ignore"):
        return f, 10 * np.log10(p)


def band_median(f, p_db, lo, hi):
    m = (f >= lo) & (f < hi)
    return float(np.median(p_db[m])) if m.any() else np.nan


def spectral_features(x: np.ndarray, fs: float, vel_units: bool = True) -> dict:
    """Spectral and statistical features of the vertical component."""
    f, pdb = psd_db(x, fs)
    p = 10 ** (pdb / 10)
    m = f > 0
    tot = p[m].sum()
    cen = float((f[m] * p[m]).sum() / tot) if tot > 0 else np.nan
    bw = float(np.sqrt(((f[m] - cen) ** 2 * p[m]).sum() / tot)) if tot > 0 else np.nan
    cum = np.cumsum(p[m]) / tot if tot > 0 else np.zeros(m.sum())
    roll = float(f[m][np.searchsorted(cum, 0.85)]) if tot > 0 else np.nan
    out = {
        "dominant_freq_hz": float(f[m][np.argmax(p[m])]),
        "spectral_centroid_hz": cen,
        "spectral_bandwidth_hz": bw,
        "spectral_rolloff_hz": roll,
        "rms_velocity": float(np.sqrt(np.mean(np.asarray(x, float) ** 2)))
        if vel_units
        else np.nan,
        "kurtosis": float(stats.kurtosis(x)),
    }
    if vel_units:  # PSD bands only make sense in physical units
        # convert velocity PSD to acceleration PSD: + 20 log10(2 pi f)
        with np.errstate(divide="ignore"):
            pacc = pdb + 20 * np.log10(2 * np.pi * np.where(f > 0, f, np.nan))
        out.update(
            {
                "psd_p50_db_0_1_1hz": band_median(f, pacc, 0.1, 1),
                "psd_p50_db_1_10hz": band_median(f, pacc, 1, 10),
                "psd_p50_db_10_30hz": band_median(f, pacc, 10, 30),
                "_f": f,
                "_pacc": pacc,
            }
        )
    return out


def psd_vs_nlnm(f, pacc_db, lo=1.0, hi=10.0) -> float:
    """Median excess (dB) of acceleration PSD over Peterson's New Low Noise Model in a band."""
    try:
        from obspy.signal.spectral_estimation import get_nlnm
    except ImportError:
        return np.nan
    per, nl = get_nlnm()
    fq = 1 / per[::-1]
    nlf = np.interp(f, fq, nl[::-1])
    m = (f >= lo) & (f < hi) & np.isfinite(pacc_db)
    return float(np.median(pacc_db[m] - nlf[m])) if m.any() else np.nan


def count_transients(x: np.ndarray, fs: float, sta=1.0, lta=30.0, on=3.5) -> int:
    from obspy.signal.trigger import classic_sta_lta, trigger_onset

    cft = classic_sta_lta(np.asarray(x, float), int(sta * fs), int(lta * fs))
    return len(trigger_onset(cft, on, 1.5))


def classify_noise(psd_1_10, psd_10_30, day_night) -> str:
    """Rule-based dominant source (placeholder for the learned classifier)."""
    if any(v is None or not np.isfinite(v) for v in (psd_1_10, psd_10_30)):
        return "desconocida"
    if np.isfinite(day_night) and day_night > 2 and psd_1_10 > -140:
        return "trafico_actividad_humana"
    if psd_10_30 > psd_1_10 + 5:
        return "industria_fuente_cercana"
    return "natural"
