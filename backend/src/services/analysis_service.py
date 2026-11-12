import numpy as np
from .unmix_algorithm import matrix_diagnostics
from .noise_algorithm import conditional_refits
from .band_selection import resolve_band_mask
from ..utils.fingerprint import fingerprint

ALGORITHM_VERSION = "simplex-nullspace-kkt-gaussian-v3"


def analyze_unmix(snapshot, noise_sigma=.005, repeats=80, seed=2026, band_exclusions=None):
    library = snapshot['library']; members = sorted(snapshot['endmembers'], key=lambda e: e['code']); samples = sorted(snapshot['samples'], key=lambda s: s['code'])
    if not 1 <= len(samples) <= 6 or len(samples)*repeats > 480: raise ValueError("选择1–6个样本，样本数×重复数不得超过480")
    if len({s['code'] for s in samples}) != len(samples): raise ValueError("混合样本编号重复")
    if type(seed) is not int or not 0 <= seed <= 2147483647: raise ValueError("根种子须为0–2147483647整数")
    wavelengths = np.asarray(library['wavelengths'], dtype=float)
    # 排除规则在此再次解析：worker 只信任冻结在运行行上的规则，不信任外部记忆。
    retained_idx, excluded_idx, exclusions = resolve_band_mask(library['wavelengths'], band_exclusions)
    retained_waves = [float(w) for w in wavelengths[retained_idx]]
    A_full = np.array([e['spectrum'] for e in members], dtype=float).T
    if wavelengths.ndim != 1 or not np.isfinite(wavelengths).all() or np.any(np.diff(wavelengths) <= 0): raise ValueError("波长须有限且严格递增")
    if len(wavelengths) != A_full.shape[0]: raise ValueError("波长与端元波段数不匹配")
    # 配比、KKT、可辨识性与条件重拟合全部只在保留波段上求解。
    A = A_full[retained_idx, :]
    _, diagnostics = matrix_diagnostics(A)
    if not diagnostics['supported']: raise ValueError(diagnostics['reason'])
    streams = np.random.SeedSequence(seed).spawn(len(samples)); results = []
    for sample, child in zip(samples, streams):
        observed_full = np.asarray(sample['observed'], dtype=float)
        if observed_full.shape != (A_full.shape[0],): raise ValueError(f"样本{sample['code']}观测波段数与光谱库不匹配")
        y = observed_full[retained_idx]
        refits = conditional_refits(A, y, noise_sigma, repeats, child)
        point = refits['point_fit']
        weights = np.asarray(point['weights'])
        # 全谱重建：用同一套保留波段配比回乘完整端元矩阵，被排除波段不参与拟合但仍展示。
        reconstructed_full = (A_full @ weights).tolist()
        residual_full = (observed_full - A_full @ weights).tolist()
        reason_by_index = {index: item['reason'] for index, item in zip(excluded_idx, exclusions)}
        band_status = [
            {"wavelength": float(wavelengths[i]), "retained": i not in reason_by_index,
             "exclusion_reason": reason_by_index.get(i, "")}
            for i in range(len(wavelengths))
        ]
        results.append({"sample_id": sample['id'], "code": sample['code'], "name": sample['name'],
                        "observed": sample['observed'], "spawn_key": list(child.spawn_key),
                        "high_residual": point['rmse'] > max(3*noise_sigma, 1e-8),
                        "retained_band_count": len(retained_idx),
                        "reconstructed_full": reconstructed_full, "residual_full": residual_full,
                        "band_status": band_status, **refits})
    canonical = {"library": library, "endmembers": members, "samples": samples,
                 "band_exclusions": exclusions, "retained_wavelengths": retained_waves}
    fingerprint_payload = {"method": ALGORITHM_VERSION, "snapshot": canonical,
                           "noise_sigma": noise_sigma, "repeats": repeats, "seed": seed}
    return {"algorithm_version": ALGORITHM_VERSION, "library": library, "endmembers": members, "samples": results,
            "diagnostics": diagnostics, "full_spectrum_diagnostics": matrix_diagnostics(A_full)[1],
            "noise_sigma": noise_sigma, "repeats": repeats, "seed": seed,
            "band_exclusions": exclusions, "retained_wavelengths": retained_waves,
            "total_band_count": len(wavelengths), "retained_band_count": len(retained_idx), "excluded_band_count": len(excluded_idx),
            "input_snapshot": canonical, "input_hash": fingerprint(fingerprint_payload),
            "assumptions": "固定校准端元的线性混合；权重非负且和为1。噪声在各保留波段独立同方差Gaussian，sigma由用户给定；被排除的杂散光污染波段不参与配比、重拟合与残差判定，仅展示全谱重建。高残差只提示失配，不是噪声或成分真实性检验。",
            "quantile_note": "分位范围是条件扰动情景，不是配比真值的覆盖保证。", "feasibility_tolerance": 1e-10, "condition_limit": 1e6}
