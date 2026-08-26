import { Play, Upload, Square, WifiOff } from 'lucide-react';
import { CACHED_REGIONS } from '../lib/constants.js';
import { useSrmStore } from '../store/useSrmStore.js';

export default function ControlPanel({ onRun, onRegionSelect, onUploadGeoJSON, drawMode, onToggleDraw }) {
  const { settings, setSettings, status, offlineMode, toggleOffline, aoi } = useSrmStore();
  const busy = status === 'fetching' || status === 'processing';

  return (
    <aside className="flex w-60 shrink-0 flex-col gap-5 overflow-y-auto border-r border-slate-200 bg-white p-4 xl:w-80">
      <section>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Area of interest
        </h2>
        <button
          onClick={onToggleDraw}
          className={`mb-2 flex w-full items-center gap-2 rounded border px-3 py-2 text-sm ${
            drawMode
              ? 'border-sky-600 bg-sky-50 text-sky-700'
              : 'border-slate-300 hover:bg-slate-50'
          }`}
        >
          <Square size={16} /> {drawMode ? 'Drawing — drag on the map' : 'Draw bounding box'}
        </button>
        <label className="flex w-full cursor-pointer items-center gap-2 rounded border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50">
          <Upload size={16} /> Upload GeoJSON
          <input
            type="file"
            accept=".geojson,.json"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && onUploadGeoJSON(e.target.files[0])}
          />
        </label>
        <p className="mt-2 text-xs text-slate-500">
          {aoi ? 'AOI set.' : 'No AOI selected yet.'}
        </p>
      </section>

      <section>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Cached demo regions
        </h2>
        <div className="flex flex-col gap-1">
          {CACHED_REGIONS.map((r) => (
            <button
              key={r.key}
              onClick={() => onRegionSelect(r)}
              className="rounded px-3 py-2 text-left text-sm hover:bg-slate-100"
            >
              {r.label}
            </button>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Model configuration
        </h2>

        <label className="block text-sm text-slate-700">
          Scale factor
          <select
            value={settings.scaleFactor}
            onChange={(e) => setSettings({ scaleFactor: Number(e.target.value) })}
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
          >
            <option value={4}>4× — 2.5 m</option>
            <option value={8}>8× — 1.25 m (experimental)</option>
          </select>
        </label>

        <label className="mt-3 block text-sm text-slate-700">
          Max cloud cover: {settings.maxCloudCover}%
          <input
            type="range"
            min={0}
            max={50}
            value={settings.maxCloudCover}
            onChange={(e) => setSettings({ maxCloudCover: Number(e.target.value) })}
            className="mt-1 w-full"
          />
        </label>

        <label className="mt-3 flex items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={settings.applyMrf}
            onChange={(e) => setSettings({ applyMrf: e.target.checked })}
          />
          MRF boundary smoothing
        </label>

        <label className="mt-3 flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={offlineMode} onChange={toggleOffline} />
          <WifiOff size={14} /> Offline demo mode
        </label>
      </section>

      <button
        onClick={onRun}
        disabled={busy}
        className="mt-auto flex items-center justify-center gap-2 rounded bg-slate-900 px-4 py-3 text-sm font-semibold text-white disabled:opacity-50"
      >
        <Play size={16} />
        {busy ? 'Processing…' : 'Execute super-resolution mapping'}
      </button>
    </aside>
  );
}
