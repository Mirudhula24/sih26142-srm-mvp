import { useState } from 'react';
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import {
  Download,
  BarChart3,
  ChevronRight,
  ChevronLeft,
  Layers,
  Clock,
  Award,
  Maximize2,
  FileCode,
  FileSpreadsheet,
  FileText,
  Bot,
  ScanSearch,
  CalendarRange,
} from 'lucide-react';
import { LAND_COVER_CLASSES } from '../lib/constants.js';
import { askSpatialAssistant, exportUrls, getTemporalChange } from '../lib/api.js';
import { useSrmStore } from '../store/useSrmStore.js';

const fmt = (n) => new Intl.NumberFormat('en-IN', { maximumFractionDigits: 1 }).format(n);

function lookupClass(obj, cls) {
  if (obj == null) return undefined;
  if (Array.isArray(obj)) return obj[cls.id];
  return (
    obj[cls.key] ??
    obj[cls.label] ??
    obj[cls.id] ??
    obj[String(cls.id)] ??
    obj[cls.key.replace('_', '-')]
  );
}

function numeric(value, ...keys) {
  if (value == null) return 0;
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value))) {
    return Number(value);
  }
  if (typeof value === 'object') {
    for (const key of keys) {
      if (value[key] != null && Number.isFinite(Number(value[key]))) return Number(value[key]);
    }
  }
  return 0;
}

function classRows(job) {
  const dist = job.class_distribution_percent ?? {};
  const areas = job.class_area_sqm ?? {};
  const rows = LAND_COVER_CLASSES.map((c) => {
    const rawPct = lookupClass(dist, c);
    const rawArea = lookupClass(areas, c);
    const percent = numeric(rawPct, 'percent', 'value', 'pct');
    let sqm = numeric(rawArea, 'area_sqm', 'sqm');
    const hectares = numeric(rawArea, 'area_hectares', 'hectares');
    if (!sqm && hectares) sqm = hectares * 10_000;
    return { name: c.label, value: percent, color: c.color, sqm };
  });
  const pctSum = rows.reduce((s, r) => s + r.value, 0);
  if (pctSum > 0 && pctSum <= 1.01) {
    rows.forEach((r) => {
      r.value *= 100;
    });
  }
  return rows;
}

export default function AnalyticsDrawer({ job }) {
  const { analyticsOpen, toggleAnalytics, settings } = useSrmStore();
  const [layers, setLayers] = useState(() => Object.fromEntries(LAND_COVER_CLASSES.map((c) => [c.key, true])));
  const [question, setQuestion] = useState('What is the urban area?');
  const [assistantAnswer, setAssistantAnswer] = useState('');
  const [assistantBusy, setAssistantBusy] = useState(false);
  const [temporalMessage, setTemporalMessage] = useState('');

  if (!analyticsOpen) {
    return (
      <button
        type="button"
        onClick={toggleAnalytics}
        className="absolute right-3 top-16 z-20 flex h-10 w-10 items-center justify-center rounded-xl border border-slate-300 bg-white text-slate-800 transition-colors hover:bg-slate-100 hover:text-slate-900 cursor-pointer"
        title="Open Results & Analytics"
      >
        <ChevronLeft size={20} />
      </button>
    );
  }

  if (!job || job.status !== 'COMPLETED') {
    return (
      <aside className="relative flex w-80 shrink-0 flex-col gap-4 overflow-y-auto border-l border-slate-200 bg-white p-4 text-slate-400 z-20">
        <div className="flex items-center justify-between border-b border-slate-200 pb-2.5">
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
            <BarChart3 size={16} className="text-blue-600" /> Results & Analytics
          </h2>
          <button
            type="button"
            onClick={toggleAnalytics}
            className="flex h-6 w-6 items-center justify-center rounded-md border border-slate-300 bg-slate-100 text-slate-400 transition-all hover:bg-slate-200 hover:text-slate-900 cursor-pointer"
            title="Collapse Drawer"
          >
            <ChevronRight size={16} />
          </button>
        </div>
        <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center py-16">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-slate-200 bg-slate-50 text-slate-300">
            <Layers size={24} />
          </div>
          <p className="text-xs leading-relaxed text-slate-400 max-w-[200px]">
            Run a mapping analysis to populate land-cover metrics and download exports.
          </p>
        </div>
      </aside>
    );
  }

  const data = classRows(job).filter((row) => layers[LAND_COVER_CLASSES.find((c) => c.label === row.name)?.key] !== false);
  const urls = exportUrls(job.job_id);
  const scale = job.scale_factor ?? 4;
  const resM = (10 / scale).toFixed(1);
  const isReference = job.inference_mode === 'worldcover_reference';
  const accuracy = typeof job.miou_score === 'number' ? `${(job.miou_score * 100).toFixed(1)}%` : 'N/A';

  // Compute total area km2
  const totalSqm = data.reduce((s, r) => s + r.sqm, 0);
  const areaKm2 = (totalSqm / 1_000_000).toFixed(1);

  const toggleLayer = (key) => setLayers((current) => ({ ...current, [key]: !current[key] }));
  const askAssistant = async () => {
    if (!question.trim()) return;
    setAssistantBusy(true);
    try { setAssistantAnswer((await askSpatialAssistant(job.job_id, question)).answer); }
    catch (error) { setAssistantAnswer(error.message); }
    finally { setAssistantBusy(false); }
  };
  const checkTemporal = async () => {
    try { setTemporalMessage((await getTemporalChange(job.job_id)).message); }
    catch (error) { setTemporalMessage(error.message); }
  };

  return (
    <aside className="relative flex w-80 shrink-0 flex-col gap-5 overflow-y-auto border-l border-slate-200 bg-white p-4 text-slate-900 z-20">
      {/* Header & Collapse Toggle */}
      <div className="flex items-center justify-between border-b border-slate-200 pb-2.5">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
          <BarChart3 size={16} className="text-blue-600" /> Results & Analytics
        </h2>
        <button
          type="button"
          onClick={toggleAnalytics}
          className="flex h-6 w-6 items-center justify-center rounded-md border border-slate-300 bg-slate-100 text-slate-400 transition-all hover:bg-slate-200 hover:text-slate-900 cursor-pointer"
          title="Collapse Drawer"
        >
          <ChevronRight size={16} />
        </button>
      </div>

      {/* Key Metrics Grid (4 Cards) */}
      <div className="flex flex-col gap-2">
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Key Metrics</h3>
        {typeof job.confidence_mean_percent === 'number' && (
          <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-3 py-2">
            <div className="flex flex-col">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Model Confidence</span>
              <span className="text-[10px] text-slate-400">
                {typeof job.high_uncertainty_percent === 'number'
                  ? `${fmt(job.high_uncertainty_percent)}% high-uncertainty pixels`
                  : 'Per-pixel abundance entropy'}
              </span>
            </div>
            <span className={`text-lg font-extrabold ${
              job.confidence_mean_percent >= 80 ? 'text-emerald-600' :
              job.confidence_mean_percent >= 60 ? 'text-amber-600' : 'text-rose-600'}`}>
              {fmt(job.confidence_mean_percent)}%
            </span>
          </div>
        )}
        <div className="grid grid-cols-2 gap-2">
          {/* Card 1: Output Resolution */}
          <div className="flex flex-col gap-0.5 rounded-xl border border-slate-200 bg-white p-2.5">
            <span className="text-base font-extrabold text-cyan-700">{resM} m</span>
            <span className="text-[10px] text-slate-400 font-medium">Output Resolution</span>
          </div>

          {/* Card 2: Area Processed */}
          <div className="flex flex-col gap-0.5 rounded-xl border border-slate-200 bg-white p-2.5">
            <span className="text-base font-extrabold text-blue-600">{areaKm2 > 0 ? areaKm2 : '—'}{areaKm2 > 0 ? ' km²' : ''}</span>
            <span className="text-[10px] text-slate-400 font-medium">Area Processed</span>
          </div>

          {/* Card 3: Processing Time */}
          <div className="flex flex-col gap-0.5 rounded-xl border border-slate-200 bg-white p-2.5">
            <span className="text-base font-extrabold text-indigo-700">
              {job.execution_time_seconds ? `${job.execution_time_seconds.toFixed(0)}s` : '—'}
            </span>
            <span className="text-[10px] text-slate-400 font-medium">Processing Time</span>
          </div>

          {/* Card 4: Accuracy provenance */}
          <div className="flex flex-col gap-0.5 rounded-xl border border-slate-200 bg-white p-2.5">
            <div className="flex items-center gap-1">
              <span className={`text-sm font-extrabold ${isReference ? 'text-amber-600' : 'text-emerald-600'}`}>
                {isReference ? 'Reference data' : accuracy}
              </span>
            </div>
            <span className="text-[10px] text-slate-400 font-medium">
              {isReference ? 'ESA WorldCover 2021' : 'Validated mIoU'}
            </span>
          </div>
        </div>
      </div>

      {/* Land-Cover Distribution Donut Chart */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <ScanSearch size={14} className="text-cyan-600" />
          <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Layer controls</h3>
        </div>
        <p className="text-[10px] text-slate-400">Toggle classes to focus the analytics and inspector.</p>
        <div className="grid grid-cols-2 gap-1.5">
          {LAND_COVER_CLASSES.map((layer) => (
            <button key={layer.key} type="button" onClick={() => toggleLayer(layer.key)}
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1.5 text-left text-[10px] font-semibold transition-colors ${layers[layer.key] ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white text-slate-500 hover:text-slate-900'}`}>
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: layer.color }} />{layer.label}
            </button>
          ))}
        </div>
      </div>

      {/* Land-Cover Distribution Donut Chart */}
      <div className="flex flex-col gap-2">
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Land-Cover Distribution</h3>
        <div className="h-44 w-full rounded-xl border border-slate-200 bg-[#faf7f2] p-2">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                dataKey="value"
                nameKey="name"
                innerRadius={38}
                outerRadius={65}
                paddingAngle={3}
                stroke="none"
              >
                {data.map((d) => (
                  <Cell key={d.name} fill={d.color} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  backgroundColor: '#0b1329',
                  borderColor: '#1e293b',
                  borderRadius: '0.75rem',
                  fontSize: '11px',
                  color: '#f8fafc',
                }}
                formatter={(v) => [`${fmt(v)}%`, 'Coverage']}
              />
              <Legend
                verticalAlign="bottom"
                height={28}
                iconSize={8}
                wrapperStyle={{ fontSize: '10px', color: '#94a3b8' }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-3">
        <div className="flex items-center gap-2"><CalendarRange size={15} className="text-violet-600" /><h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-700">Temporal change detection</h3></div>
        <p className="text-[10px] leading-relaxed text-slate-400">Compare calibrated 2024 and 2026 outputs before reporting urban expansion or vegetation loss.</p>
        <button type="button" onClick={checkTemporal} className="rounded-lg border border-violet-300 bg-violet-50 px-2 py-1.5 text-[10px] font-semibold text-violet-700 hover:bg-violet-100">Check temporal readiness</button>
        {temporalMessage && <p className="text-[10px] leading-relaxed text-amber-700">{temporalMessage}</p>}
      </div>

      <div className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-3">
        <div className="flex items-center gap-2"><Bot size={15} className="text-cyan-600" /><h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-700">Geo-assistant</h3></div>
        <div className="flex gap-1.5"><input value={question} onChange={(e) => setQuestion(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && askAssistant()} className="min-w-0 flex-1 rounded-full border border-slate-300 bg-white px-3 py-1.5 text-[10px] text-slate-900 outline-none focus:border-slate-900" />
          <button type="button" onClick={askAssistant} disabled={assistantBusy} className="rounded-full bg-slate-900 px-3 text-[10px] font-bold text-white hover:bg-slate-800 disabled:opacity-50">Ask</button></div>
        {assistantAnswer && <p className="text-[10px] leading-relaxed text-slate-700">{assistantAnswer}</p>}
      </div>

      {/* Detailed Breakdown Table */}
      <div className="flex flex-col gap-2">
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Detailed Breakdown</h3>
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-xs">
            <thead className="border-b border-slate-200 bg-slate-50 text-slate-400 text-[10px]">
              <tr>
                <th className="px-3 py-1.5 text-left font-semibold">Class</th>
                <th className="px-3 py-1.5 text-right font-semibold">Area (km²)</th>
                <th className="px-3 py-1.5 text-right font-semibold">Percentage</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 text-[11px]">
              {data.map((d) => (
                <tr key={d.name} className="transition-colors hover:bg-slate-100">
                  <td className="flex items-center gap-2 px-3 py-1.5 font-medium text-slate-800">
                    <span className="h-2 w-2 rounded-full" style={{ background: d.color }} />
                    {d.name}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono text-slate-700">
                    {(d.sqm / 1_000_000).toFixed(2)}
                  </td>
                  <td className="px-3 py-1.5 text-right font-bold" style={{ color: d.color }}>
                    {fmt(d.value)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Export Results */}
      <div className="flex flex-col gap-2 pt-1 border-t border-slate-200">
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Export Results</h3>

        <a
          href={urls.geotiff}
          download
          className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-xs transition-all hover:border-blue-300 hover:bg-blue-50 cursor-pointer shadow-sm"
        >
          <div className="flex items-center gap-2.5">
            <Layers size={16} className="text-blue-600" />
            <div className="flex flex-col">
              <span className="font-bold text-slate-900">Download GeoTIFF</span>
              <span className="text-[10px] text-slate-400">High-resolution raster</span>
            </div>
          </div>
          <Download size={15} className="text-slate-400" />
        </a>

        <a href={urls.executiveReport} download className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-xs transition-all hover:border-cyan-300 hover:bg-cyan-50 cursor-pointer shadow-sm">
          <div className="flex items-center gap-2.5"><FileText size={16} className="text-cyan-600" /><div className="flex flex-col"><span className="font-bold text-slate-900">Executive PDF Report</span><span className="text-[10px] text-slate-400">Branded result summary</span></div></div><Download size={15} className="text-slate-400" />
        </a>

        <a
          href={urls.geojson}
          download
          className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-xs transition-all hover:border-indigo-300 hover:bg-indigo-50 cursor-pointer shadow-sm"
        >
          <div className="flex items-center gap-2.5">
            <FileCode size={16} className="text-indigo-600" />
            <div className="flex flex-col">
              <span className="font-bold text-slate-900">Export GeoJSON</span>
              <span className="text-[10px] text-slate-400">Vector land-cover data</span>
            </div>
          </div>
          <Download size={15} className="text-slate-400" />
        </a>

        <a
          href={urls.csv}
          download
          className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-xs transition-all hover:border-emerald-400 hover:bg-emerald-50 cursor-pointer shadow-sm"
        >
          <div className="flex items-center gap-2.5">
            <FileText size={16} className="text-emerald-600" />
            <div className="flex flex-col">
              <span className="font-bold text-slate-900">Download Report (CSV)</span>
              <span className="text-[10px] text-slate-400">Complete analysis report</span>
            </div>
          </div>
          <Download size={15} className="text-slate-400" />
        </a>
      </div>
    </aside>
  );
}
