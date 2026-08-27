import { useEffect, useState } from 'react';
import {
  Brain,
  CheckCircle2,
  Loader2,
  FileCheck,
  Layers,
  BarChart3,
  XCircle,
  Info,
  Clock,
} from 'lucide-react';
import { useSrmStore } from '../store/useSrmStore.js';

export default function ProcessingStepper({ regionName = 'Delhi NCR', areaKm2 = '42.6' }) {
  const { status, setStatus, settings, granule } = useSrmStore();
  const [elapsed, setElapsed] = useState(0);

  const busy = status === 'fetching' || status === 'processing';

  useEffect(() => {
    let timer;
    if (busy) {
      setElapsed(0);
      timer = setInterval(() => {
        setElapsed((prev) => prev + 1);
      }, 1000);
    }
    return () => clearInterval(timer);
  }, [busy]);

  if (!busy && status !== 'ready') return null;

  // Step state logic
  let currentStep = 0;
  let percent = 0;
  let eta = 35 - elapsed;
  if (eta < 0) eta = 0;

  if (status === 'fetching') {
    currentStep = 1;
    percent = Math.min(30, Math.round((elapsed / 8) * 30));
  } else if (status === 'processing') {
    currentStep = 2;
    percent = Math.min(95, 30 + Math.round(((elapsed - 8) / 25) * 65));
  } else if (status === 'ready') {
    currentStep = 4;
    percent = 100;
    eta = 0;
  }

  const steps = [
    { title: 'Loading Sentinel-2 Imagery', icon: Layers },
    { title: 'Validating Cloud Coverage', icon: FileCheck },
    { title: 'Running GeoSRM Inference', icon: Brain },
    { title: 'Generating Land-Cover Layers', icon: Layers },
    { title: 'Computing Spatial Analytics', icon: BarChart3 },
  ];

  const formatSec = (s) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m > 0 ? `${m}m ` : ''}${sec.toString().padStart(2, '0')}s`;
  };

  return (
    <div className="absolute bottom-4 left-1/2 z-30 w-full max-w-4xl -translate-x-1/2 rounded-2xl border border-slate-300 bg-white p-4 text-slate-900">
      {/* Top Title & Timer Bar */}
      <div className="flex items-center justify-between border-b border-slate-200 pb-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-slate-300 bg-slate-100 text-slate-700">
            <Brain size={20} />
          </div>
          <div>
            <h3 className="text-sm font-bold tracking-tight text-slate-900 flex items-center gap-2">
              Mapping {granule ? granule.granule_id.split('_')[5] ?? regionName : regionName}
            </h3>
            <p className="text-[10px] text-slate-400">
              Sentinel-2 L2A ➔ SRM 2.5m Super-Resolution Pipeline
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4 text-xs font-mono">
          <div className="flex items-center gap-1.5 text-slate-400">
            <Clock size={13} className="text-cyan-600" />
            <span>Elapsed: {formatSec(elapsed)}</span>
          </div>
          {busy && (
            <div className="flex items-center gap-1.5 text-cyan-700 font-semibold">
              <span>ETA: ~{formatSec(eta)}</span>
            </div>
          )}
        </div>
      </div>

      {/* 5-Step Progress Indicators */}
      <div className="my-4 grid grid-cols-5 gap-2 px-2">
        {steps.map((step, idx) => {
          const isDone = idx < currentStep || status === 'ready';
          const isCurrent = idx === currentStep && busy;
          const IconComp = step.icon;

          return (
            <div key={step.title} className="flex flex-col items-center gap-2 text-center">
              <div className="relative flex items-center justify-center">
                {isDone ? (
                  <div className="flex h-8 w-8 items-center justify-center rounded-full border border-emerald-400 bg-emerald-100 text-emerald-600">
                    <CheckCircle2 size={18} />
                  </div>
                ) : isCurrent ? (
                  <div className="flex h-8 w-8 items-center justify-center rounded-full border border-cyan-400 bg-cyan-100 text-cyan-700">
                    <Loader2 size={18} className="animate-spin text-cyan-600" />
                  </div>
                ) : (
                  <div className="flex h-8 w-8 items-center justify-center rounded-full border border-slate-200 bg-slate-50 text-slate-400">
                    <IconComp size={16} />
                  </div>
                )}
              </div>
              <span
                className={`text-[10px] leading-tight font-medium ${
                  isDone
                    ? 'text-emerald-700'
                    : isCurrent
                    ? 'text-cyan-700 font-bold'
                    : 'text-slate-400'
                }`}
              >
                {step.title}
              </span>
            </div>
          );
        })}
      </div>

      {/* Progress Bar & Readout */}
      <div className="flex items-center gap-3">
        <div className="relative h-2.5 min-w-0 flex-1 overflow-hidden rounded-full bg-slate-100 border border-slate-200">
          <div
            className="h-full bg-slate-300 transition-all duration-300"
            style={{ width: `${percent}%` }}
          />
        </div>
        <span className="font-mono text-xs font-bold text-cyan-700">{percent}%</span>
      </div>

      {/* Info Line & Cancel Button */}
      <div className="mt-3 flex items-center justify-between pt-2 border-t border-slate-200 text-xs">
        <div className="flex items-center gap-2 text-slate-400 text-[11px]">
          <Info size={14} className="text-cyan-600 shrink-0" />
          <span>
            Using GeoSRM v1.0 · Resolution: {(10 / settings.scaleFactor).toFixed(1)} m · Scale: {settings.scaleFactor}×
          </span>
        </div>

        {busy && (
          <button
            type="button"
            onClick={() => setStatus('idle')}
            className="flex items-center gap-1.5 rounded-lg border border-rose-300 bg-rose-50 px-3 py-1 text-xs font-semibold text-rose-700 transition-all hover:bg-rose-200 hover:text-slate-900"
          >
            <XCircle size={14} /> Cancel Job
          </button>
        )}
      </div>
    </div>
  );
}
