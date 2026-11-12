-- 002: 按波长排除杂散光污染波段；旧研究该列为 NULL/空列表，结果与导出保持兼容。
ALTER TABLE unmix_runs ADD COLUMN band_exclusions JSON NULL AFTER seed;
