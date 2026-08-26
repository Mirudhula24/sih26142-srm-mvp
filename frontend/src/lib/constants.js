export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
export const TITILER_BASE = import.meta.env.VITE_TITILER_BASE_URL ?? 'http://localhost:8001';

// Palette must stay in sync with backend/services/exporter.py CLASS_COLORS.
export const LAND_COVER_CLASSES = [
  { id: 0, key: 'built_up',   label: 'Urban',      color: '#3b82f6' },
  { id: 1, key: 'water',      label: 'Water',      color: '#06b6d4' },
  { id: 2, key: 'vegetation', label: 'Vegetation', color: '#10b981' },
  { id: 3, key: 'cropland',   label: 'Cropland',   color: '#84cc16' },
  { id: 4, key: 'bare_soil',  label: 'Barren',     color: '#f59e0b' },
];

export const CACHED_REGIONS = [
  { key: 'delhi_ncr',      label: 'Delhi NCR — urban', center: [77.10, 28.70], zoom: 12, bbox: [76.84, 28.40, 77.35, 28.88] },
  { key: 'kerala_coastal', label: 'Kerala — coastal',  center: [76.05, 10.15], zoom: 12, bbox: [75.75, 9.90, 76.40, 10.45] },
  { key: 'rajasthan_arid', label: 'Rajasthan — arid',  center: [73.05, 26.30], zoom: 12, bbox: [72.80, 26.10, 73.40, 26.60] },
];

// True XYZ mosaic (not a STAC preview PNG). Using a preview image as tiles is what
// produced the repeating diagonal stripe on the left canvas.
export const SENTINEL2_XYZ =
  'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg';
