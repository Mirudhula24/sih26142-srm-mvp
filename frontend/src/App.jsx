import { useEffect, useRef, useState } from 'react';
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
import { fetchGranule, getJob, inspectSubpixel, pollJob, startSRM } from './lib/api.js';
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
    setSettings,
    toggleControl,
    toggleAnalytics,
  } = useSrmStore();

  const [error, setError] = useState(null);
  const [outputTileUrl, setOutputTileUrl] = useState(null);
  const [inspection, setInspection] = useState(null);
  const permalinkRestored = useRef(false);

  // Restore permalink state once on mount: #region=delhi_ncr&scale=4&job=job_srm_...
  useEffect(() => {
    if (permalinkRestored.current) return;
    permalinkRestored.current = true;
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ''));
    const regionKey = params.get('region');
    if (regionKey) {
      const region = CACHED_REGIONS.find((r) => r.key === regionKey);
      if (region) handleRegionSelect(region);
    }
    const scale = Number(params.get('scale'));
    if (scale === 4 || scale === 8) setSettings({ scaleFactor: scale });
    const jobId = params.get('job');
    if (jobId) {
      getJob(jobId)
        .then((resumed) => {
          if (resumed?.status === 'COMPLETED') {
            setJob(resumed);
            setOutputTileUrl(
              resumed.tile_url_template ??
                `${TITILER_BASE}/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=/data/cogs/${resumed.job_id}.tif`,
            );
            setStatus('ready');
          }
        })
        .catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Publish the permalink whenever the shareable subset changes.
  useEffect(() => {
    const params = new URLSearchParams();
    if (selectedRegionKey) params.set('region', selectedRegionKey);
    if (settings.scaleFactor) params.set('scale', String(settings.scaleFactor));
    if (job?.job_id) params.set('job', job.job_id);
    const hash = params.toString();
    const target = hash ? `#${hash}` : '';
    if (target !== window.location.hash) {
      window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}${target}`);
    }
  }, [selectedRegionKey, settings.scaleFactor, job?.job_id]);
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
    <div className="flex h-full flex-col bg-[#f4efe8] text-slate-900 antialiased font-sans select-none overflow-hidden">
      {/* Top Navigation Header */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-5 z-30">
        {/* Left Logo */}
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-100 text-slate-800 border border-slate-300">
            <Brain size={20} />
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-tight text-slate-900 flex items-center gap-2">
              GeoSRM Engine
            </h1>
            <p className="text-[10px] text-slate-400 font-medium">Sub-Pixel Land Mapping</p>
          </div>
        </div>

        {/* Center Project Selector & Location Badge */}
        <div className="hidden md:flex items-center gap-4">
          <div className="relative flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-1.5 text-xs text-slate-800">
            <span className="font-semibold text-slate-400">Project:</span>
            <select
              value={selectedRegion.key}
              onChange={(e) => {
                const reg = CACHED_REGIONS.find((r) => r.key === e.target.value);
                if (reg) handleRegionSelect(reg);
              }}
              className="bg-transparent font-bold text-slate-900 outline-none cursor-pointer"
            >
              {CACHED_REGIONS.map((r) => (
                <option key={r.key} value={r.key} className="bg-white text-slate-900">
                  {r.label.split('—')[0].trim()}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <MapPin size={14} className="text-rose-600" />
            <span>{selectedRegion.label.split('—')[0].trim()}, India</span>
          </div>

          <div className="flex items-center gap-1.5 rounded-full bg-emerald-100 border border-emerald-200 px-3 py-1 text-xs font-bold text-emerald-700">
            <span>AOI: 42.6 km²</span>
          </div>
        </div>

        {/* Right Model Status & User Controls */}
        <div className="flex items-center gap-3">
          <div className={`hidden lg:flex items-center gap-2 rounded-xl border px-3.5 py-1.5 text-xs font-semibold ${usingBaseline || usingWorldCover ? 'border-amber-300 bg-amber-50 text-amber-700' : 'border-emerald-300 bg-emerald-50 text-emerald-700'}`}>
            <span className={`h-2 w-2 rounded-full ${usingBaseline || usingWorldCover ? 'bg-amber-400' : 'bg-emerald-400'}`} />
            <span>{usingWorldCover ? 'ESA WorldCover reference (2021)' : usingBaseline ? 'Spectral baseline — checkpoint required' : `Model: GeoSRM v1.0 ${status === 'ready' ? 'Ready' : status}`}</span>
          </div>

          {job && (
            <a
              href={job.cog_output_url ?? '#'}
              download
              className="flex items-center gap-2 rounded-full border border-slate-300 bg-white px-3.5 py-1.5 text-xs font-semibold text-slate-800 hover:bg-slate-100 transition-colors cursor-pointer"
            >
              <Upload size={14} /> Export
            </a>
          )}

          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white">
            LK
          </div>

          {/* Quick Mobile Drawer Toggles */}
          <div className="flex items-center gap-1 sm:hidden">
            <button
              onClick={toggleControl}
              type="button"
              className="p-1.5 rounded-lg border border-slate-200 bg-slate-100 text-slate-700 hover:text-slate-900"
              title="Toggle Controls"
            >
              <SlidersHorizontal size={16} />
            </button>
            <button
              onClick={toggleAnalytics}
              type="button"
              className="p-1.5 rounded-lg border border-slate-200 bg-slate-100 text-slate-700 hover:text-slate-900"
              title="Toggle Analytics"
            >
              <BarChart3 size={16} />
            </button>
          </div>
        </div>
      </header>

      {/* Floating Error Banner */}
      {error && (
        <div className="absolute top-16 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-2xl border border-rose-300 bg-rose-100 px-4 py-2.5 text-xs text-rose-700">
          <AlertCircle size={16} className="text-rose-600 shrink-0" />
          <span className="font-medium max-w-lg truncate">{error}</span>
          <button
            type="button"
            onClick={() => setError(null)}
            className="ml-2 rounded-full p-1 hover:bg-rose-200/60 text-rose-700 hover:text-slate-900 transition-colors cursor-pointer"
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

        <main className="relative min-w-0 flex-1 bg-[#f4efe8]">
          <DualCanvasMap inputTileUrl={granule?.preview_url} outputTileUrl={outputTileUrl} onInspect={handleInspect} inspection={inspection} />
          <ProcessingStepper regionName={selectedRegion.label.split('—')[0].trim()} />
        </main>

        <AnalyticsDrawer job={job} />
      </div>
    </div>
  );
}
