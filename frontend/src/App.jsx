import { useState } from 'react';
import AnalyticsDrawer from './components/AnalyticsDrawer.jsx';
import ControlPanel from './components/ControlPanel.jsx';
import DualCanvasMap from './components/DualCanvasMap.jsx';
import { fetchGranule, pollJob, startSRM } from './lib/api.js';
import { TITILER_BASE } from './lib/constants.js';
import { useSrmStore } from './store/useSrmStore.js';

export default function App() {
  const { aoi, setAoi, granule, setGranule, job, setJob, status, setStatus, settings, setCamera } =
    useSrmStore();
  const [error, setError] = useState(null);
  const [outputTileUrl, setOutputTileUrl] = useState(null);

  const handleRegionSelect = (region) => {
    setCamera({ center: region.center, zoom: region.zoom, bearing: 0, pitch: 0 });
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
        scale_factor: settings.scaleFactor,
        apply_mrf_smoothing: settings.applyMrf,
      });
      const finished = await pollJob(queued.job_id);
      if (finished.status === 'FAILED') throw new Error('Inference failed.');

      setJob(finished);
      setOutputTileUrl(
        finished.tile_url_template ??
          `${TITILER_BASE}/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=/data/cogs/${finished.job_id}.tif`,
      );
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
        />
        <main className="min-w-0 flex-1">
          <DualCanvasMap inputTileUrl={granule?.preview_url} outputTileUrl={outputTileUrl} />
        </main>
        <AnalyticsDrawer job={job} />
      </div>
    </div>
  );
}
