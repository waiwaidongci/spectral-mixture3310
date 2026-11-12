"""按波长排除杂散光污染波段的统一解析与校验。

配置页给出的排除规则在入队（run_service 预检）与 worker 计算（analysis_service）
两处使用，同一处解析保证规则冻结前后一致。排除项归一化为按波长排序的
{wavelength, reason} 字典列表，便于写入快照与指纹。
"""
import numpy as np

WAVELENGTH_TOL = 1e-9
MIN_RETAINED_BANDS = 2


def normalize_exclusions(band_exclusions):
    items = []
    for item in band_exclusions or []:
        if isinstance(item, dict):
            wavelength, reason = item["wavelength"], item["reason"]
        else:
            wavelength, reason = item.wavelength, item.reason
        try:
            wavelength = float(wavelength)
        except (TypeError, ValueError):
            raise ValueError("排除波长必须为数字")
        if not np.isfinite(wavelength):
            raise ValueError("排除波长必须为有限数字")
        reason = str(reason).strip()
        if not reason:
            raise ValueError("每个排除波段必须填写杂散光污染原因")
        items.append({"wavelength": wavelength, "reason": reason})
    items.sort(key=lambda x: x["wavelength"])
    return items


def resolve_band_mask(wavelengths, band_exclusions):
    """返回 (保留波段下标, 排除波段下标, 归一化排除规则)。"""
    waves = np.asarray(wavelengths, dtype=float)
    if waves.ndim != 1 or not np.isfinite(waves).all() or np.any(np.diff(waves) <= 0):
        raise ValueError("波长须有限且严格递增")
    exclusions = normalize_exclusions(band_exclusions)
    selected = [item["wavelength"] for item in exclusions]
    if len(set(selected)) != len(selected):
        raise ValueError("排除波长不可重复，请合并同一波段的污染原因")
    grid = waves.tolist()
    excluded_idx = []
    for wavelength in selected:
        matches = [i for i, grid_wave in enumerate(grid) if abs(grid_wave - wavelength) <= WAVELENGTH_TOL]
        if not matches:
            raise ValueError(f"排除波长 {wavelength:g}nm 不在光谱库波长网格中")
        excluded_idx.append(matches[0])
    excluded_set = set(excluded_idx)
    retained = [i for i in range(len(grid)) if i not in excluded_set]
    if len(retained) < MIN_RETAINED_BANDS:
        raise ValueError(f"至少保留{MIN_RETAINED_BANDS}个未污染波段才能解混，请减少排除波段")
    return retained, sorted(excluded_set), exclusions
