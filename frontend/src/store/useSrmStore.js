import { create } from 'zustand';

/**
 * Single source of truth for both map canvases. Keeping the camera here (rather than
 * letting each MapLibre instance own it) is what keeps the split view locked together.
 */
export const useSrmStore = create((set) => ({
  camera: { center: [77.108, 28.709], zoom: 12, bearing: 0, pitch: 0 },
  // Written by the maps on every pan. Reading this to *move* them would echo back.
  setCamera: (camera) => set({ camera }),

  // A one-shot instruction to move the maps, from outside the maps. The nonce makes two
  // consecutive requests for the same place distinct, so the effect fires both times.
  cameraRequest: null,
  requestCamera: (c) => set({ cameraRequest: { ...c, nonce: Date.now() } }),

  sliderPosition: 0.5,
  setSliderPosition: (sliderPosition) => set({ sliderPosition }),

  aoi: null,
  setAoi: (aoi) => set({ aoi }),

  granule: null,
  setGranule: (granule) => set({ granule }),

  job: null,
  setJob: (job) => set({ job }),

  status: 'idle', // idle | fetching | processing | ready | error
  setStatus: (status) => set({ status }),

  offlineMode: false,
  toggleOffline: () => set((s) => ({ offlineMode: !s.offlineMode })),

  settings: { scaleFactor: 4, applyMrf: true, maxCloudCover: 10 },
  setSettings: (patch) => set((s) => ({ settings: { ...s.settings, ...patch } })),
}));
