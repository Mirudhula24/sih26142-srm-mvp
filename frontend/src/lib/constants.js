export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
export const TITILER_BASE = import.meta.env.VITE_TITILER_BASE_URL ?? 'http://localhost:8001';

// Palette must stay in sync with backend/services/exporter.py CLASS_COLORS.
export const LAND_COVER_CLASSES = [
  { id: 0, key: 'built_up',   label: 'Built-up',   color: '#d6604d' },
  { id: 1, key: 'water',      label: 'Water',      color: '#2166ac' },
  { id: 2, key: 'vegetation', label: 'Vegetation', color: '#1b7837' },
  { id: 3, key: 'cropland',   label: 'Cropland',   color: '#a6db6c' },
  { id: 4, key: 'bare_soil',  label: 'Bare soil',  color: '#bfa57a' },
];

export const CACHED_REGIONS = [
  { key: 'delhi_ncr',      label: 'Delhi NCR — urban',    center: [77.10, 28.70], zoom: 12 },
  { key: 'kerala_coastal', label: 'Kerala — coastal',     center: [76.05, 10.15], zoom: 12 },
  { key: 'rajasthan_arid', label: 'Rajasthan — arid',     center: [73.05, 26.30], zoom: 12 },
];
