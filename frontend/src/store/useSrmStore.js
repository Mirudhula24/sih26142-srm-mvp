import { create } from 'zustand';

/**
 * Single source of truth for both map canvases. Keeping the camera here (rather than
 * letting each MapLibre instance own it) is what keeps the split view locked together.
 */
export const useSrmStore = create((set) => ({
  camera: { center: [77.108, 28.709], zoom: 12, bearing: 0, pitch: 0 },
  setCamera: (camera) => set({ camera }),

  sliderPosition: 0.5,
  setSliderPosition: (sliderPosition) => set({ sliderPosition }),

  aoi: null,
  setAoi: (aoi) => set({ aoi }),

  drawMode: false,
  setDrawMode: (drawMode) => set({ drawMode }),

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

  selectedRegionKey: null,
  setSelectedRegionKey: (selectedRegionKey) => set({ selectedRegionKey }),

  controlOpen: true,
  setControlOpen: (controlOpen) => set({ controlOpen }),
  toggleControl: () => set((s) => ({ controlOpen: !s.controlOpen })),

  analyticsOpen: true,
  setAnalyticsOpen: (analyticsOpen) => set({ analyticsOpen }),
  toggleAnalytics: () => set((s) => ({ analyticsOpen: !s.analyticsOpen })),

  viewMode: 'compare', // 'compare' | 'satellite' | 'output'
  setViewMode: (viewMode) => set({ viewMode }),

  advancedOpen: false,
  setAdvancedOpen: (advancedOpen) => set({ advancedOpen }),
  toggleAdvanced: () => set((s) => ({ advancedOpen: !s.advancedOpen })),

  stepState: { step: 0, percent: 0, elapsed: 0, eta: 0 },
  setStepState: (stepState) => set((s) => ({ stepState: { ...s.stepState, ...stepState } })),
}));
