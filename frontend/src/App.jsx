import { useState } from 'react';
import AnalyticsDrawer from './components/AnalyticsDrawer.jsx';
import ControlPanel from './components/ControlPanel.jsx';
import DualCanvasMap from './components/DualCanvasMap.jsx';
import { fetchGranule, pollJob, startSRM } from './lib/api.js';
import { API_BASE } from './lib/constants.js';
import { useSrmStore } from './store/useSrmStore.js';

export default function App() {
  const { aoi, setAoi, granule, setGranule, job, setJob, status, setStatus, settings, requestCamera } =
    useSrmStore();
  const [error, setError] = useState(null);
  const [layers, setLayers] = useState({ input: null, output: null });
  const [drawMode, setDrawMode] = useState(false);

  const handleRegionSelect = (region) => {
    requestCamera({ center: region.center, zoom: region.zoom });
    const [lon, lat] = region.center;
    const d = 0.03;
    setAoi({
      type: 'Polygon',
      coordinates: [[
        [lon - d, lat - d], [lon + d, lat - d],
        [lon + d, lat + d], [lon - d, lat + d],
        [lon - d, lat - d],
      ]],
    });
  };

  const handleAoiDrawn = (polygon) => {
    setAoi(polygon);
    setDrawMode(false);
    setError(null);
  };

  const handleUploadGeoJSON = async (file) => {
    try {
      const parsed = JSON.parse(await file.text());
      setAoi(parsed.type === 'FeatureCollection' ? parsed.features[0].geometry : parsed);
    } catch {
      setError('Could not parse that GeoJSON file.');
    }
  };

  const handleRun = async () => {
    if (!aoi) {
      setError('Select an area of interest first.');
      return;
    }
    setError(null);
    try {
      setStatus('fetching');
      const scene = await fetchGranule({
        aoi_geojson: aoi,
        max_cloud_cover: settings.maxCloudCover,
        date_range: { start: '2026-01-01', end: '2026-03-01' },
      });
      setGranule(scene);

      setStatus('processing');
      const queued = await startSRM({
        granule_id: scene.granule_id,
        aoi_geojson: aoi,
        max_cloud_cover: settings.maxCloudCover,
        scale_factor: settings.scaleFactor,
        apply_mrf_smoothing: settings.applyMrf,
      });
      const finished = queued.status === 'COMPLETED' ? queued : await pollJob(queued.job_id);
      if (finished.status === 'FAILED') {
        throw new Error(finished.error || 'Inference failed.');
      }

      setJob(finished);
      // Sync mode returns corner-pinned PNGs; the distributed stack returns a TiTiler
      // tile template. Prefer whichever the API actually supplied.
      if (finished.bounds && finished.output_preview_url) {
        setLayers({
          input: { url: API_BASE + finished.input_preview_url, coordinates: finished.bounds },
          output: { url: API_BASE + finished.output_preview_url, coordinates: finished.bounds },
        });
      } else if (finished.tile_url_template) {
        setLayers({ input: null, output: finished.tile_url_template });
      }
      setStatus('ready');
    } catch (e) {
      setError(e.message);
      setStatus('error');
    }
  };

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-4 border-b border-slate-200 bg-slate-900 px-4 py-3 text-white">
        <h1 className="text-sm font-semibold">SIH26142 — GeoSRM Engine</h1>
        <span className="text-xs text-slate-300">
          {granule ? `${granule.granule_id} · ${granule.cloud_cover}% cloud` : 'No granule loaded'}
        </span>
        {job?.method && (
          <span
            className={`rounded px-2 py-1 text-xs ${
              job.method === 'learned' ? 'bg-indigo-700' : 'bg-slate-600'
            }`}
            title={
              job.method === 'classical'
                ? 'Constrained least-squares unmixing plus pixel swapping — no trained weights involved'
                : 'Deep spectral unmixing with the Swin allocation head'
            }
          >
            {job.method === 'classical' ? 'classical SRM' : 'deep SRM'}
          </span>
        )}
        {job?.data_source && (
          <span
            className={`rounded px-2 py-1 text-xs ${
              job.data_source === 'stac' ? 'bg-emerald-700' : 'bg-amber-700'
            }`}
            title={
              job.data_source === 'stac'
                ? 'Imagery fetched live from the Sentinel-2 STAC catalogue'
                : 'Imagery served from the local offline cache, not a fresh acquisition'
            }
          >
            {job.data_source === 'stac' ? 'live STAC' : 'cached imagery'}
          </span>
        )}
        <span className="ml-auto rounded bg-slate-700 px-2 py-1 text-xs capitalize">{status}</span>
      </header>

      {error && (
        <div className="bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>
      )}

      <div className="flex min-h-0 flex-1">
        <ControlPanel
          onRun={handleRun}
          onRegionSelect={handleRegionSelect}
          onUploadGeoJSON={handleUploadGeoJSON}
          drawMode={drawMode}
          onToggleDraw={() => setDrawMode((d) => !d)}
        />
        <main className="min-w-0 flex-1">
          <DualCanvasMap
            inputLayer={layers.input}
            outputLayer={layers.output}
            drawMode={drawMode}
            onAoiDrawn={handleAoiDrawn}
          />
        </main>
        <AnalyticsDrawer job={job} />
      </div>
    </div>
  );
}
