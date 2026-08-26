import { useState } from 'react';
import {
  Play,
  Upload,
  Square,
  WifiOff,
  CheckCircle2,
  Loader2,
  ChevronUp,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Pencil,
  Lock,
  BookOpen,
  Sliders,
  Check,
  Star,
  Layers,
} from 'lucide-react';
import { CACHED_REGIONS } from '../lib/constants.js';
import { useSrmStore } from '../store/useSrmStore.js';

export default function ControlPanel({ onRun, onRegionSelect, onUploadGeoJSON }) {
  const {
    settings,
    setSettings,
    status,
    offlineMode,
    toggleOffline,
    aoi,
    drawMode,
    setDrawMode,
    selectedRegionKey,
    setSelectedRegionKey,
    controlOpen,
    toggleControl,
    advancedOpen,
    toggleAdvanced,
  } = useSrmStore();

  const busy = status === 'fetching' || status === 'processing';
  const isCompleted = status === 'ready';

  const handleRegionClick = (region) => {
    setSelectedRegionKey(region.key);
    onRegionSelect(region);
  };

  if (!controlOpen) {
    return (
      <button
        type="button"
        onClick={toggleControl}
        className="absolute left-3 top-16 z-20 flex h-10 w-10 items-center justify-center rounded-xl border border-slate-700/60 bg-[#0f172a]/95 text-slate-200 shadow-xl backdrop-blur-md transition-all hover:bg-blue-600 hover:text-white cursor-pointer"
        title="Open Workflow Panel"
      >
        <ChevronRight size={20} />
      </button>
    );
  }

  return (
    <aside className="relative flex w-80 shrink-0 flex-col gap-5 overflow-y-auto border-r border-[#1e293b] bg-[#0b1329]/95 p-4 text-slate-100 backdrop-blur-lg shadow-2xl transition-all duration-300 z-20">
      {/* Workflow Header & Collapse */}
      <div className="flex items-center justify-between border-b border-[#1e293b] pb-2.5">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
          <Layers size={16} className="text-blue-400" /> Workflow
        </h2>
        <button
          type="button"
          onClick={toggleControl}
          className="flex h-6 w-6 items-center justify-center rounded-md border border-slate-700/50 bg-slate-800/60 text-slate-400 transition-all hover:bg-slate-700 hover:text-white cursor-pointer"
          title="Collapse Panel"
        >
          <ChevronUp size={16} />
        </button>
      </div>

      {/* Step 1: Define Area */}
      <section className="flex flex-col gap-2.5 rounded-xl border border-[#1e293b] bg-[#111c38]/60 p-3.5 shadow-sm">
        <div className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400 font-bold text-[11px]">
            ✓
          </span>
          <h3 className="text-xs font-bold text-white">1. Define Area</h3>
        </div>

        {/* Active AOI Card */}
        <div className="flex flex-col gap-1 rounded-lg border border-emerald-500/30 bg-emerald-950/20 p-2.5 text-xs">
          <div className="flex items-center justify-between text-emerald-400 font-semibold">
            <span>AOI Selected</span>
            <CheckCircle2 size={14} />
          </div>
          <p className="text-[11px] text-slate-300">
            {aoi ? '42.6 km² · Selected Region' : 'Delhi NCR · 42.6 km²'}
          </p>
        </div>

        {/* Region Quick Selector */}
        <div className="flex flex-col gap-1">
          <label className="text-[10px] uppercase font-bold text-slate-400">Target Region</label>
          <div className="grid grid-cols-3 gap-1">
            {CACHED_REGIONS.map((r) => {
              const isSel = selectedRegionKey === r.key || (r.key === 'delhi_ncr' && !selectedRegionKey);
              return (
                <button
                  key={r.key}
                  type="button"
                  onClick={() => handleRegionClick(r)}
                  className={`rounded-md border px-1.5 py-1 text-center text-[10px] font-semibold truncate transition-all cursor-pointer ${
                    isSel
                      ? 'border-emerald-500 bg-emerald-950/60 text-emerald-300'
                      : 'border-slate-800 bg-slate-900/60 text-slate-400 hover:text-white'
                  }`}
                >
                  {r.label.split('—')[0].trim()}
                </button>
              );
            })}
          </div>
        </div>

        {/* Action Buttons */}
        <button
          type="button"
          onClick={() => setDrawMode(!drawMode)}
          className={`flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold shadow-md transition-all cursor-pointer ${
            drawMode
              ? 'bg-emerald-600 text-white shadow-emerald-600/30 ring-2 ring-emerald-400'
              : 'bg-gradient-to-r from-emerald-600 via-teal-600 to-emerald-500 text-white hover:brightness-110'
          }`}
        >
          <Pencil size={14} />
          {drawMode ? 'Drawing... click map' : 'Edit Area on Map'}
        </button>

        <label className="flex w-full cursor-pointer items-center justify-center gap-2 rounded-lg border border-[#1e293b] bg-slate-900/70 px-3 py-1.5 text-xs font-medium text-slate-300 transition-all hover:border-slate-700 hover:text-white">
          <Upload size={14} /> Upload GeoJSON
          <input
            type="file"
            accept=".geojson,.json"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && onUploadGeoJSON(e.target.files[0])}
          />
        </label>
      </section>

      {/* Step 2: Configure Resolution */}
      <section className="flex flex-col gap-2.5 rounded-xl border border-[#1e293b] bg-[#111c38]/60 p-3.5 shadow-sm">
        <div className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-500/20 text-blue-400 font-bold text-[11px]">
            2
          </span>
          <h3 className="text-xs font-bold text-white">2. Configure Resolution</h3>
        </div>

        <p className="text-[11px] text-slate-400">Choose Output Resolution</p>

        {/* Resolution Options Grid */}
        <div className="grid grid-cols-2 gap-2">
          {/* 4x Option */}
          <button
            type="button"
            onClick={() => setSettings({ scaleFactor: 4 })}
            className={`relative flex flex-col items-center justify-center gap-1 rounded-xl border p-3 text-center transition-all cursor-pointer ${
              settings.scaleFactor === 4
                ? 'border-blue-500 bg-blue-950/50 text-white shadow-lg shadow-blue-500/20 ring-1 ring-blue-400'
                : 'border-slate-800 bg-slate-900/60 text-slate-400 hover:border-slate-700 hover:text-slate-200'
            }`}
          >
            <div className="flex items-center gap-1">
              <span className={`h-3 w-3 rounded-full border flex items-center justify-center ${
                settings.scaleFactor === 4 ? 'border-blue-400 bg-blue-500' : 'border-slate-600'
              }`}>
                {settings.scaleFactor === 4 && <span className="h-1 w-1 rounded-full bg-white" />}
              </span>
              <span className="text-base font-extrabold text-white">4×</span>
            </div>
            <span className="text-xs font-bold text-slate-200">2.5 m</span>
            <span className="rounded-full bg-blue-500/20 px-2 py-0.5 text-[9px] font-semibold text-blue-300 flex items-center gap-0.5">
              Recommended ⭐
            </span>
          </button>

          {/* 8x Option */}
          <button
            type="button"
            onClick={() => setSettings({ scaleFactor: 8 })}
            className={`relative flex flex-col items-center justify-center gap-1 rounded-xl border p-3 text-center transition-all cursor-pointer ${
              settings.scaleFactor === 8
                ? 'border-blue-500 bg-blue-950/50 text-white shadow-lg shadow-blue-500/20 ring-1 ring-blue-400'
                : 'border-slate-800 bg-slate-900/60 text-slate-400 hover:border-slate-700 hover:text-slate-200'
            }`}
          >
            <div className="flex items-center gap-1">
              <span className={`h-3 w-3 rounded-full border flex items-center justify-center ${
                settings.scaleFactor === 8 ? 'border-blue-400 bg-blue-500' : 'border-slate-600'
              }`}>
                {settings.scaleFactor === 8 && <span className="h-1 w-1 rounded-full bg-white" />}
              </span>
              <span className="text-base font-extrabold text-white">8×</span>
            </div>
            <span className="text-xs font-bold text-slate-200">1.25 m</span>
            <span className="text-[9px] text-slate-500">Maximum detail</span>
          </button>
        </div>

        {/* Collapsible Advanced Settings */}
        <button
          type="button"
          onClick={toggleAdvanced}
          className="flex items-center justify-between text-xs font-medium text-slate-400 hover:text-white pt-1 cursor-pointer"
        >
          <span>Advanced Settings</span>
          {advancedOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>

        {advancedOpen && (
          <div className="flex flex-col gap-2.5 rounded-lg bg-slate-900/80 p-2.5 text-xs text-slate-300">
            <div className="flex justify-between items-center">
              <span>Max Cloud Cover</span>
              <span className="font-bold text-blue-400">{settings.maxCloudCover}%</span>
            </div>
            <input
              type="range"
              min={0}
              max={50}
              value={settings.maxCloudCover}
              onChange={(e) => setSettings({ maxCloudCover: Number(e.target.value) })}
              className="h-1.5 w-full cursor-pointer accent-blue-500"
            />
            <label className="flex items-center justify-between cursor-pointer pt-1">
              <span>MRF Boundary Smoothing</span>
              <input
                type="checkbox"
                checked={settings.applyMrf}
                onChange={(e) => setSettings({ applyMrf: e.target.checked })}
                className="h-4 w-4 rounded accent-blue-500"
              />
            </label>
          </div>
        )}
      </section>

      {/* Step 3: Process Mapping */}
      <section className="flex flex-col gap-2.5 rounded-xl border border-[#1e293b] bg-[#111c38]/60 p-3.5 shadow-sm">
        <div className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-indigo-500/20 text-indigo-400 font-bold text-[11px]">
            3
          </span>
          <h3 className="text-xs font-bold text-white">3. Process Mapping</h3>
        </div>
        <p className="text-[11px] text-slate-400">Run GeoSRM AI Model</p>

        <button
          type="button"
          onClick={onRun}
          disabled={busy}
          className={`flex w-full items-center justify-center gap-2 rounded-xl py-3 text-xs font-bold uppercase tracking-wider text-white shadow-xl transition-all cursor-pointer ${
            busy
              ? 'bg-indigo-950 border border-indigo-800/50 text-indigo-400 cursor-not-allowed'
              : 'bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:brightness-110 active:scale-[0.98] shadow-indigo-600/30 ring-1 ring-white/20'
          }`}
        >
          {busy ? (
            <>
              <Loader2 size={16} className="animate-spin text-indigo-300" />
              <span>Running Analysis...</span>
            </>
          ) : (
            <>
              <Play size={16} className="fill-current" />
              <span>Run Analysis</span>
            </>
          )}
        </button>
      </section>

      {/* Step 4: Results & Analytics */}
      <section className="flex flex-col gap-2 rounded-xl border border-[#1e293b] bg-[#111c38]/40 p-3.5 opacity-90">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className={`flex h-5 w-5 items-center justify-center rounded-full font-bold text-[11px] ${
              isCompleted ? 'bg-emerald-500/20 text-emerald-400' : 'bg-slate-800 text-slate-500'
            }`}>
              4
            </span>
            <h3 className="text-xs font-bold text-white">4. Results & Analytics</h3>
          </div>
        </div>

        <p className="text-[11px] text-slate-400">View and Export Results</p>

        <div className="flex items-center gap-2 text-[11px] text-slate-400 pt-1">
          {isCompleted ? (
            <>
              <CheckCircle2 size={14} className="text-emerald-400" />
              <span className="text-emerald-300 font-semibold">Results ready to view</span>
            </>
          ) : (
            <>
              <Lock size={14} className="text-slate-500" />
              <span>Locked until processing</span>
            </>
          )}
        </div>
      </section>

      {/* Footer Support Link */}
      <div className="mt-auto border-t border-[#1e293b] pt-3 text-[11px] text-slate-400 flex items-center justify-between hover:text-white transition-colors cursor-pointer">
        <div className="flex items-center gap-1.5">
          <BookOpen size={14} className="text-blue-400" />
          <span>Need help? View docs</span>
        </div>
        <span>›</span>
      </div>
    </aside>
  );
}
