import { API_BASE } from './constants.js';

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export const fetchGranule = (body) =>
  request('/api/v1/imagery/fetch', { method: 'POST', body: JSON.stringify(body) });

export const startSRM = (body) =>
  request('/api/v1/srm/process', { method: 'POST', body: JSON.stringify(body) });

export const getJob = (jobId) => request(`/api/v1/jobs/${jobId}`);

export const exportUrls = (jobId) => ({
  geotiff: `${API_BASE}/api/v1/jobs/${jobId}/export.tif`,
  geojson: `${API_BASE}/api/v1/jobs/${jobId}/export.geojson`,
  csv: `${API_BASE}/api/v1/jobs/${jobId}/report.csv`,
});

/** Poll until the job leaves PENDING/RUNNING. */
export async function pollJob(jobId, { intervalMs = 1000, timeoutMs = 120000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const job = await getJob(jobId);
    if (job.status === 'COMPLETED' || job.status === 'FAILED') return job;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error('Timed out waiting for the SRM job.');
}
