import { useState } from 'react';
import {
  AlertCircle,
  X,
  Layers,
  Activity,
  Satellite,
  Brain,
  MapPin,
  ChevronDown,
  Upload,
  Download,
  User,
  SlidersHorizontal,
  BarChart3,
  CheckCircle2,
} from 'lucide-react';
import AnalyticsDrawer from './components/AnalyticsDrawer.jsx';
import ControlPanel from './components/ControlPanel.jsx';
import DualCanvasMap from './components/DualCanvasMap.jsx';
import ProcessingStepper from './components/ProcessingStepper.jsx';
import { fetchGranule, inspectSubpixel, pollJob, startSRM } from './lib/api.js';
import { TITILER_BASE, CACHED_REGIONS } from './lib/constants.js';
import { useSrmStore } from './store/useSrmStore.js';

export default function App() {
  const {
    aoi,
    setAoi,
    granule,
    setGranule,
    job,
    setJob,
    status,
    setStatus,
    settings,
    setCamera,
    setDrawMode,
    selectedRegionKey,
    setSelectedRegionKey,
    toggleControl,
    toggleAnalytics,
  } = useSrmStore();

  const [error, setError] = useState(null);
  const [outputTileUrl, setOutputTileUrl] = useState(null);
  const [inspection, setInspection] = useState(null);
  const usingBaseline = job?.inference_mode === 'spectral_baseline';
  const usingWorldCover = job?.inference_mode === 'worldcover_reference';

  const handleRegionSelect = (region) => {
    setDrawMode(false);
    setSelectedRegionKey(region.key);
    setCamera({
      center: region.center,
      zoom: region.zoom,
      bearing: 0,
      pitch: 0,
    });
    const [west, south, east, north] = region.bbox;
    const [lon, lat] = region.center;
    const padLon = Math.min(0.04, (east - west) / 4);
    const padLat = Math.min(0.04, (north - south) / 4);
    setAoi({
      type: 'Polygon',
      coordinates: [[
        [lon - padLon, lat - padLat], [lon + padLon, lat - padLat],
        [lon + padLon, lat + padLat], [lon - padLon, lat + padLat],
        [lon - padLon, lat - padLat],
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
      setError('Select or draw an area of interest first.');
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
      const finished = await pollJob(queued.job_id);
      if (finished.status === 'FAILED') throw new Error(finished.error || 'Inference failed.');

      setJob(finished);
      setInspection(null);
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

  const handleInspect = async ({ lon, lat }) => {
    if (!job?.job_id) return;
    try {
      setInspection({ longitude: lon, latitude: lat, loading: true });
      setInspection(await inspectSubpixel(job.job_id, { lon, lat }));
    } catch (e) {
      setInspection({ longitude: lon, latitude: lat, error: e.message });
    }
  };

  const selectedRegion = CACHED_REGIONS.find((r) => r.key === selectedRegionKey) || CACHED_REGIONS[0];

  return (
    <div className="flex h-full flex-col bg-[#070d1e] text-slate-100 antialiased font-sans select-none overflow-hidden">
      {/* Top Navigation Header */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-[#1e293b] bg-[#0b1329]/95 px-5 backdrop-blur-xl z-30 shadow-xl">
        {/* Left Logo */}
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-cyan-600 via-blue-600 to-indigo-600 text-white shadow-lg shadow-blue-500/25 ring-1 ring-white/20">
            <Brain size={20} />
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-tight text-white flex items-center gap-2">
              GeoSRM Engine
            </h1>
            <p className="text-[10px] text-slate-400 font-medium">Sub-Pixel Land Mapping</p>
          </div>
        </div>

        {/* Center Project Selector & Location Badge */}
        <div className="hidden md:flex items-center gap-4">
          <div className="relative flex items-center gap-2 rounded-xl border border-[#1e293b] bg-[#111c38]/60 px-3 py-1.5 text-xs text-slate-200">
            <span className="font-semibold text-slate-400">Project:</span>
            <select
              value={selectedRegion.key}
              onChange={(e) => {
                const reg = CACHED_REGIONS.find((r) => r.key === e.target.value);
                if (reg) handleRegionSelect(reg);
              }}
              className="bg-transparent font-bold text-white outline-none cursor-pointer"
            >
              {CACHED_REGIONS.map((r) => (
                <option key={r.key} value={r.key} className="bg-slate-900 text-white">
                  {r.label.split('—')[0].trim()}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <MapPin size={14} className="text-rose-400" />
            <span>{selectedRegion.label.split('—')[0].trim()}, India</span>
          </div>

          <div className="flex items-center gap-1.5 rounded-full bg-emerald-950/60 border border-emerald-800/60 px-3 py-1 text-xs font-bold text-emerald-300">
            <span>AOI: 42.6 km²</span>
          </div>
        </div>

        {/* Right Model Status & User Controls */}
        <div className="flex items-center gap-3">
          <div className={`hidden lg:flex items-center gap-2 rounded-xl border px-3.5 py-1.5 text-xs font-semibold shadow-sm ${usingBaseline || usingWorldCover ? 'border-amber-900/60 bg-amber-950/40 text-amber-300' : 'border-emerald-900/60 bg-emerald-950/40 text-emerald-300'}`}>
            <span className={`h-2 w-2 rounded-full animate-pulse ${usingBaseline || usingWorldCover ? 'bg-amber-400' : 'bg-emerald-400'}`} />
            <span>{usingWorldCover ? 'ESA WorldCover reference (2021)' : usingBaseline ? 'Spectral baseline — checkpoint required' : `Model: GeoSRM v1.0 ${status === 'ready' ? 'Ready' : status}`}</span>
          </div>

          {job && (
            <a
              href={job.cog_output_url ?? '#'}
              download
              className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-800/80 px-3.5 py-1.5 text-xs font-semibold text-white shadow-md hover:bg-slate-700 transition-all cursor-pointer"
            >
              <Upload size={14} /> Export
            </a>
          )}

          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-600 text-xs font-bold text-white shadow-md shadow-indigo-600/30 ring-2 ring-indigo-400/50">
            LK
          </div>

          {/* Quick Mobile Drawer Toggles */}
          <div className="flex items-center gap-1 sm:hidden">
            <button
              onClick={toggleControl}
              type="button"
              className="p-1.5 rounded-lg border border-slate-800 bg-slate-800/60 text-slate-300 hover:text-white"
              title="Toggle Controls"
            >
              <SlidersHorizontal size={16} />
            </button>
            <button
              onClick={toggleAnalytics}
              type="button"
              className="p-1.5 rounded-lg border border-slate-800 bg-slate-800/60 text-slate-300 hover:text-white"
              title="Toggle Analytics"
            >
              <BarChart3 size={16} />
            </button>
          </div>
        </div>
      </header>

      {/* Floating Error Banner */}
      {error && (
        <div className="absolute top-16 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-2xl border border-rose-500/40 bg-rose-950/90 px-4 py-2.5 text-xs text-rose-200 shadow-2xl backdrop-blur-md animate-in fade-in slide-in-from-top duration-200">
          <AlertCircle size={16} className="text-rose-400 shrink-0" />
          <span className="font-medium max-w-lg truncate">{error}</span>
          <button
            type="button"
            onClick={() => setError(null)}
            className="ml-2 rounded-full p-1 hover:bg-rose-900/60 text-rose-300 hover:text-white transition-colors cursor-pointer"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Main Workspace Layout */}
      <div className="relative flex min-h-0 flex-1 overflow-hidden">
        <ControlPanel
          onRun={handleRun}
          onRegionSelect={handleRegionSelect}
          onUploadGeoJSON={handleUploadGeoJSON}
        />

        <main className="relative min-w-0 flex-1 bg-[#070d1e]">
          <DualCanvasMap inputTileUrl={granule?.preview_url} outputTileUrl={outputTileUrl} onInspect={handleInspect} inspection={inspection} />
          <ProcessingStepper regionName={selectedRegion.label.split('—')[0].trim()} />
        </main>

        <AnalyticsDrawer job={job} />
      </div>
    </div>
  );
}
