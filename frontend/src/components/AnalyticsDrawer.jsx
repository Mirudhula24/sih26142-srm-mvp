import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import { Download } from 'lucide-react';
import { LAND_COVER_CLASSES } from '../lib/constants.js';
import { exportUrls } from '../lib/api.js';

const fmt = (n) => new Intl.NumberFormat('en-IN', { maximumFractionDigits: 1 }).format(n);

export default function AnalyticsDrawer({ job }) {
  if (!job || job.status !== 'COMPLETED') {
    return (
      <aside className="w-60 shrink-0 border-l border-slate-200 bg-white p-4 text-sm text-slate-500 xl:w-80">
        Run a mapping job to see the land-cover breakdown.
      </aside>
    );
  }

  const dist = job.class_distribution_percent ?? {};
  const areas = job.class_area_sqm ?? {};
  const data = LAND_COVER_CLASSES.map((c) => ({
    name: c.label,
    value: dist[c.key] ?? 0,
    color: c.color,
    sqm: areas[c.key] ?? 0,
  }));
  const urls = exportUrls(job.job_id);

  return (
    <aside className="flex w-60 shrink-0 flex-col gap-4 overflow-y-auto border-l border-slate-200 bg-white p-4 xl:w-80">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        Class distribution
      </h2>

      <div className="h-52">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" innerRadius={45} outerRadius={75}>
              {data.map((d) => (
                <Cell key={d.name} fill={d.color} />
              ))}
            </Pie>
            <Tooltip formatter={(v) => `${v}%`} />
            <Legend verticalAlign="bottom" height={36} iconSize={8} />
          </PieChart>
        </ResponsiveContainer>
      </div>

      <table className="w-full text-xs">
        <thead className="text-left text-slate-500">
          <tr>
            <th className="py-1">Class</th>
            <th className="py-1 text-right">%</th>
            <th className="py-1 text-right">Hectares</th>
          </tr>
        </thead>
        <tbody>
          {data.map((d) => (
            <tr key={d.name} className="border-t border-slate-100">
              <td className="flex items-center gap-2 py-1">
                <span className="h-2 w-2 rounded-full" style={{ background: d.color }} />
                {d.name}
              </td>
              <td className="py-1 text-right">{fmt(d.value)}</td>
              <td className="py-1 text-right">{fmt(d.sqm / 10000)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <dl className="rounded bg-slate-50 p-3 text-xs text-slate-600">
        <div className="flex justify-between">
          <dt>Inference time</dt>
          <dd>{job.execution_time_seconds ?? '—'} s</dd>
        </div>
        <div className="flex justify-between">
          <dt>mIoU</dt>
          <dd>{job.miou_score?.toFixed(3) ?? '—'}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Scale factor</dt>
          <dd>4× (2.5 m)</dd>
        </div>
      </dl>

      <div className="flex flex-col gap-2">
        {[
          ['GeoTIFF (COG)', urls.geotiff],
          ['GeoJSON vectors', urls.geojson],
          ['CSV report', urls.csv],
        ].map(([label, href]) => (
          <a
            key={label}
            href={href}
            className="flex items-center gap-2 rounded border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50"
          >
            <Download size={14} /> {label}
          </a>
        ))}
      </div>
    </aside>
  );
}
