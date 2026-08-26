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
        className="absolute right-3 top-16 z-20 flex h-10 w-10 items-center justify-center rounded-xl border border-slate-700/60 bg-[#0f172a]/95 text-slate-200 shadow-xl backdrop-blur-md transition-all hover:bg-blue-600 hover:text-white cursor-pointer"
        title="Open Results & Analytics"
      >
        <ChevronLeft size={20} />
      </button>
    );
  }

  if (!job || job.status !== 'COMPLETED') {
    return (
      <aside className="relative flex w-80 shrink-0 flex-col gap-4 overflow-y-auto border-l border-[#1e293b] bg-[#0b1329]/95 p-4 text-slate-400 backdrop-blur-lg z-20">
        <div className="flex items-center justify-between border-b border-[#1e293b] pb-2.5">
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
            <BarChart3 size={16} className="text-blue-400" /> Results & Analytics
          </h2>
          <button
            type="button"
            onClick={toggleAnalytics}
            className="flex h-6 w-6 items-center justify-center rounded-md border border-slate-700/50 bg-slate-800/60 text-slate-400 transition-all hover:bg-slate-700 hover:text-white cursor-pointer"
            title="Collapse Drawer"
          >
            <ChevronRight size={16} />
          </button>
        </div>
        <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center py-16">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-slate-800 bg-slate-900/60 text-slate-600">
            <Layers size={24} className="animate-pulse" />
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
    <aside className="relative flex w-80 shrink-0 flex-col gap-5 overflow-y-auto border-l border-[#1e293b] bg-[#0b1329]/95 p-4 text-slate-100 backdrop-blur-lg shadow-2xl transition-all duration-300 z-20">
      {/* Header & Collapse Toggle */}
      <div className="flex items-center justify-between border-b border-[#1e293b] pb-2.5">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
          <BarChart3 size={16} className="text-blue-400" /> Results & Analytics
        </h2>
        <button
          type="button"
          onClick={toggleAnalytics}
          className="flex h-6 w-6 items-center justify-center rounded-md border border-slate-700/50 bg-slate-800/60 text-slate-400 transition-all hover:bg-slate-700 hover:text-white cursor-pointer"
          title="Collapse Drawer"
        >
          <ChevronRight size={16} />
        </button>
      </div>

      {/* Key Metrics Grid (4 Cards) */}
      <div className="flex flex-col gap-2">
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Key Metrics</h3>
        <div className="grid grid-cols-2 gap-2">
          {/* Card 1: Output Resolution */}
          <div className="flex flex-col gap-0.5 rounded-xl border border-[#1e293b] bg-[#111c38]/60 p-2.5">
            <span className="text-base font-extrabold text-cyan-300">{resM} m</span>
            <span className="text-[10px] text-slate-400 font-medium">Output Resolution</span>
          </div>

          {/* Card 2: Area Processed */}
          <div className="flex flex-col gap-0.5 rounded-xl border border-[#1e293b] bg-[#111c38]/60 p-2.5">
            <span className="text-base font-extrabold text-blue-400">{areaKm2 > 0 ? areaKm2 : '—'}{areaKm2 > 0 ? ' km²' : ''}</span>
            <span className="text-[10px] text-slate-400 font-medium">Area Processed</span>
          </div>

          {/* Card 3: Processing Time */}
          <div className="flex flex-col gap-0.5 rounded-xl border border-[#1e293b] bg-[#111c38]/60 p-2.5">
            <span className="text-base font-extrabold text-indigo-300">
              {job.execution_time_seconds ? `${job.execution_time_seconds.toFixed(0)}s` : '—'}
            </span>
            <span className="text-[10px] text-slate-400 font-medium">Processing Time</span>
          </div>

          {/* Card 4: Accuracy provenance */}
          <div className="flex flex-col gap-0.5 rounded-xl border border-[#1e293b] bg-[#111c38]/60 p-2.5">
            <div className="flex items-center gap-1">
              <span className={`text-sm font-extrabold ${isReference ? 'text-amber-400' : 'text-emerald-400'}`}>
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
          <ScanSearch size={14} className="text-cyan-400" />
          <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Layer controls</h3>
        </div>
        <p className="text-[10px] text-slate-500">Toggle classes to focus the analytics and inspector.</p>
        <div className="grid grid-cols-2 gap-1.5">
          {LAND_COVER_CLASSES.map((layer) => (
            <button key={layer.key} type="button" onClick={() => toggleLayer(layer.key)}
              className={`flex items-center gap-1.5 rounded-md border px-2 py-1.5 text-left text-[10px] font-semibold ${layers[layer.key] ? 'border-slate-600 bg-slate-800 text-white' : 'border-slate-800 bg-slate-950 text-slate-500'}`}>
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: layer.color }} />{layer.label}
            </button>
          ))}
        </div>
      </div>

      {/* Land-Cover Distribution Donut Chart */}
      <div className="flex flex-col gap-2">
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Land-Cover Distribution</h3>
        <div className="h-44 w-full rounded-xl border border-[#1e293b] bg-[#111c38]/40 p-2">
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

      <div className="flex flex-col gap-2 rounded-xl border border-[#1e293b] bg-[#111c38]/50 p-3">
        <div className="flex items-center gap-2"><CalendarRange size={15} className="text-violet-400" /><h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-300">Temporal change detection</h3></div>
        <p className="text-[10px] leading-relaxed text-slate-400">Compare calibrated 2024 and 2026 outputs before reporting urban expansion or vegetation loss.</p>
        <button type="button" onClick={checkTemporal} className="rounded-lg border border-violet-700/60 bg-violet-950/40 px-2 py-1.5 text-[10px] font-semibold text-violet-200 hover:bg-violet-900/60">Check temporal readiness</button>
        {temporalMessage && <p className="text-[10px] leading-relaxed text-amber-300">{temporalMessage}</p>}
      </div>

      <div className="flex flex-col gap-2 rounded-xl border border-[#1e293b] bg-[#111c38]/50 p-3">
        <div className="flex items-center gap-2"><Bot size={15} className="text-cyan-400" /><h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-300">Geo-assistant</h3></div>
        <div className="flex gap-1.5"><input value={question} onChange={(e) => setQuestion(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && askAssistant()} className="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-[10px] text-white outline-none focus:border-cyan-500" />
          <button type="button" onClick={askAssistant} disabled={assistantBusy} className="rounded-md bg-cyan-700 px-2 text-[10px] font-bold text-white disabled:opacity-50">Ask</button></div>
        {assistantAnswer && <p className="text-[10px] leading-relaxed text-slate-300">{assistantAnswer}</p>}
      </div>

      {/* Detailed Breakdown Table */}
      <div className="flex flex-col gap-2">
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Detailed Breakdown</h3>
        <div className="overflow-hidden rounded-xl border border-[#1e293b] bg-[#111c38]/60">
          <table className="w-full text-xs">
            <thead className="border-b border-[#1e293b] bg-slate-900/60 text-slate-400 text-[10px]">
              <tr>
                <th className="px-3 py-1.5 text-left font-semibold">Class</th>
                <th className="px-3 py-1.5 text-right font-semibold">Area (km²)</th>
                <th className="px-3 py-1.5 text-right font-semibold">Percentage</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1e293b]/60 text-[11px]">
              {data.map((d) => (
                <tr key={d.name} className="transition-colors hover:bg-slate-800/40">
                  <td className="flex items-center gap-2 px-3 py-1.5 font-medium text-slate-200">
                    <span className="h-2 w-2 rounded-full" style={{ background: d.color }} />
                    {d.name}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono text-slate-300">
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
      <div className="flex flex-col gap-2 pt-1 border-t border-[#1e293b]">
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Export Results</h3>

        <a
          href={urls.geotiff}
          download
          className="flex items-center justify-between rounded-xl border border-[#1e293b] bg-[#111c38]/80 px-3.5 py-2.5 text-xs transition-all hover:border-blue-500/60 hover:bg-blue-950/40 cursor-pointer shadow-sm"
        >
          <div className="flex items-center gap-2.5">
            <Layers size={16} className="text-blue-400" />
            <div className="flex flex-col">
              <span className="font-bold text-white">Download GeoTIFF</span>
              <span className="text-[10px] text-slate-400">High-resolution raster</span>
            </div>
          </div>
          <Download size={15} className="text-slate-400" />
        </a>

        <a href={urls.executiveReport} download className="flex items-center justify-between rounded-xl border border-cyan-800/70 bg-cyan-950/25 px-3.5 py-2.5 text-xs transition-all hover:bg-cyan-950/50 cursor-pointer shadow-sm">
          <div className="flex items-center gap-2.5"><FileText size={16} className="text-cyan-400" /><div className="flex flex-col"><span className="font-bold text-white">Executive PDF Report</span><span className="text-[10px] text-slate-400">Branded result summary</span></div></div><Download size={15} className="text-slate-400" />
        </a>

        <a
          href={urls.geojson}
          download
          className="flex items-center justify-between rounded-xl border border-[#1e293b] bg-[#111c38]/80 px-3.5 py-2.5 text-xs transition-all hover:border-indigo-500/60 hover:bg-indigo-950/40 cursor-pointer shadow-sm"
        >
          <div className="flex items-center gap-2.5">
            <FileCode size={16} className="text-indigo-400" />
            <div className="flex flex-col">
              <span className="font-bold text-white">Export GeoJSON</span>
              <span className="text-[10px] text-slate-400">Vector land-cover data</span>
            </div>
          </div>
          <Download size={15} className="text-slate-400" />
        </a>

        <a
          href={urls.csv}
          download
          className="flex items-center justify-between rounded-xl border border-[#1e293b] bg-[#111c38]/80 px-3.5 py-2.5 text-xs transition-all hover:border-emerald-500/60 hover:bg-emerald-950/40 cursor-pointer shadow-sm"
        >
          <div className="flex items-center gap-2.5">
            <FileText size={16} className="text-emerald-400" />
            <div className="flex flex-col">
              <span className="font-bold text-white">Download Report (CSV)</span>
              <span className="text-[10px] text-slate-400">Complete analysis report</span>
            </div>
          </div>
          <Download size={15} className="text-slate-400" />
        </a>
      </div>
    </aside>
  );
}
