import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import { SENTINEL2_XYZ } from '../lib/constants.js';
import { useSrmStore } from '../store/useSrmStore.js';

const BASEMAP = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '© OpenStreetMap contributors',
    },
  },
  layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
};

const AOI_SOURCE = 'aoi-box';
const AOI_FILL = 'aoi-fill';
const AOI_LINE = 'aoi-line';
const DRAW_SOURCE = 'draw-box';

/**
 * Two MapLibre instances under a curtain slider.
 *
 * The maps are kept camera-locked by mirroring only USER-driven movement
 * (events that carry an originalEvent). Programmatic jumpTo calls have no
 * originalEvent, so they can't trigger a mirror-back — which removes the
 * ping-pong that used to leave the two canvases slightly misaligned.
 */
export default function DualCanvasMap({ inputTileUrl, outputTileUrl, onInspect, inspection }) {
  const leftRef = useRef(null);
  const rightRef = useRef(null);
  const leftMap = useRef(null);
  const rightMap = useRef(null);
  const sliderDragging = useRef(false);
  const inspectHandler = useRef(onInspect);

  useEffect(() => { inspectHandler.current = onInspect; }, [onInspect]);

  const camera = useSrmStore((s) => s.camera);
  const setCamera = useSrmStore((s) => s.setCamera);
  const sliderPosition = useSrmStore((s) => s.sliderPosition);
  const setSliderPosition = useSrmStore((s) => s.setSliderPosition);
  const aoi = useSrmStore((s) => s.aoi);
  const setAoi = useSrmStore((s) => s.setAoi);
  const drawMode = useSrmStore((s) => s.drawMode);
  const setDrawMode = useSrmStore((s) => s.setDrawMode);

  useEffect(() => {
    const opts = {
      style: BASEMAP,
      center: camera.center,
      zoom: camera.zoom,
      attributionControl: false,
    };
    leftMap.current = new maplibregl.Map({ container: leftRef.current, ...opts });
    rightMap.current = new maplibregl.Map({ container: rightRef.current, ...opts });

    const mirror = (from, to) => (e) => {
      if (!e.originalEvent) return;
      to.jumpTo({
        center: from.getCenter(),
        zoom: from.getZoom(),
        bearing: from.getBearing(),
        pitch: from.getPitch(),
      });
    };

    leftMap.current.on('move', mirror(leftMap.current, rightMap.current));
    rightMap.current.on('move', mirror(rightMap.current, leftMap.current));

    leftMap.current.on('moveend', () => {
      const m = leftMap.current;
      if (!m) return;
      setCamera({
        center: [m.getCenter().lng, m.getCenter().lat],
        zoom: m.getZoom(),
        bearing: m.getBearing(),
        pitch: m.getPitch(),
      });
    });

    const onLoad = (map, withSentinel) => {
      if (withSentinel) addXyzRaster(map, 's2-basemap', SENTINEL2_XYZ);
      ensureAoiLayers(map);
      map.resize();
    };
    leftMap.current.once('load', () => onLoad(leftMap.current, true));
    rightMap.current.once('load', () => {
      onLoad(rightMap.current, false);
      rightMap.current.on('click', (event) => inspectHandler.current?.({
        lon: event.lngLat.lng, lat: event.lngLat.lat,
      }));
    });

    const onResize = () => {
      leftMap.current?.resize();
      rightMap.current?.resize();
    };
    window.addEventListener('resize', onResize);
    const resizeTimer = window.setTimeout(onResize, 80);

    return () => {
      window.clearTimeout(resizeTimer);
      window.removeEventListener('resize', onResize);
      leftMap.current?.remove();
      rightMap.current?.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Cached-region clicks (and anything else that writes the store camera) must
  // actually move both MapLibre instances — they are created once and otherwise
  // ignore later Zustand updates.
  useEffect(() => {
    const left = leftMap.current;
    const right = rightMap.current;
    if (!left || !right) return;
    const next = {
      center: camera.center,
      zoom: camera.zoom,
      bearing: camera.bearing ?? 0,
      pitch: camera.pitch ?? 0,
    };
    if (camerasClose(left, next)) return;
    left.jumpTo(next);
    right.jumpTo(next);
  }, [camera]);

  useEffect(() => {
    const url = isXyzTemplate(inputTileUrl) ? inputTileUrl : null;
    applyRaster(leftMap.current, 'input-raster', url);
  }, [inputTileUrl]);

  useEffect(() => {
    applyRaster(rightMap.current, 'srm-raster', isXyzTemplate(outputTileUrl) ? outputTileUrl : null);
  }, [outputTileUrl]);

  useEffect(() => {
    paintAoi(leftMap.current, aoi);
    paintAoi(rightMap.current, aoi);
  }, [aoi]);

  useEffect(() => {
    const map = leftMap.current;
    const other = rightMap.current;
    if (!map || !drawMode) return;

    ensureAoiLayers(map);
    map.dragPan.disable();
    map.boxZoom.disable();
    other?.dragPan.disable();
    map.getCanvas().style.cursor = 'crosshair';

    let start = null;

    const onDown = (e) => {
      start = e.lngLat;
      paintDrawBox(map, boxPolygon(start, start));
    };
    const onMove = (e) => {
      if (!start) return;
      paintDrawBox(map, boxPolygon(start, e.lngLat));
    };
    const onUp = (e) => {
      if (!start) return;
      const end = eventLngLat(map, e) ?? start;
      const geom = boxPolygon(start, end);
      start = null;
      paintDrawBox(map, null);
      if (boxIsUsable(geom)) setAoi(geom);
      setDrawMode(false);
    };

    map.on('mousedown', onDown);
    map.on('mousemove', onMove);
    map.on('mouseup', onUp);
    window.addEventListener('mouseup', onUp);

    return () => {
      map.off('mousedown', onDown);
      map.off('mousemove', onMove);
      map.off('mouseup', onUp);
      window.removeEventListener('mouseup', onUp);
      paintDrawBox(map, null);
      map.dragPan.enable();
      map.boxZoom.enable();
      other?.dragPan.enable();
      map.getCanvas().style.cursor = '';
    };
  }, [drawMode, setAoi, setDrawMode]);

  const onSliderPointerDown = (e) => {
    e.preventDefault();
    e.stopPropagation();
    sliderDragging.current = true;
    e.currentTarget.setPointerCapture(e.pointerId);
    moveSlider(e);
  };
  const onSliderPointerMove = (e) => {
    if (sliderDragging.current) moveSlider(e);
  };
  const onSliderPointerUp = () => {
    sliderDragging.current = false;
  };

  const moveSlider = (e) => {
    const host = e.currentTarget.parentElement;
    if (!host) return;
    const rect = host.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    setSliderPosition(Math.min(0.98, Math.max(0.02, x)));
  };

  const viewMode = useSrmStore((s) => s.viewMode);
  const setViewMode = useSrmStore((s) => s.setViewMode);
  const settings = useSrmStore((s) => s.settings);

  const handleViewChange = (mode) => {
    setViewMode(mode);
    if (mode === 'satellite') setSliderPosition(0.99);
    else if (mode === 'output') setSliderPosition(0.01);
    else setSliderPosition(0.5);
  };

  const handleZoom = (delta) => {
    const map = leftMap.current;
    if (!map) return;
    map.zoomTo(map.getZoom() + delta);
  };

  const handleRecenter = () => {
    const map = leftMap.current;
    if (!map) return;
    map.jumpTo({ center: camera.center, zoom: camera.zoom });
  };

  return (
    <div className="relative h-full w-full overflow-hidden bg-[#070d1e] select-none">
      <div ref={leftRef} className="absolute inset-0" />
      <div
        ref={rightRef}
        className="absolute inset-0"
        style={{ clipPath: `inset(0 0 0 ${sliderPosition * 100}%)` }}
      />

      {/* Top View Switcher Segmented Control */}
      <div className="absolute top-4 left-1/2 z-20 -translate-x-1/2 flex items-center rounded-2xl border border-slate-700/60 bg-[#0b1329]/90 p-1 shadow-2xl backdrop-blur-md">
        {[
          { key: 'satellite', label: 'Satellite Input' },
          { key: 'output', label: 'SRM Output (2.5m)' },
          { key: 'compare', label: 'Compare' },
        ].map((btn) => {
          const isActive = viewMode === btn.key;
          return (
            <button
              key={btn.key}
              type="button"
              onClick={() => handleViewChange(btn.key)}
              className={`rounded-xl px-4 py-1.5 text-xs font-bold transition-all cursor-pointer ${
                isActive
                  ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              {btn.label}
            </button>
          );
        })}
      </div>

      {/* Top Left Canvas Overlay Card */}
      <div className="absolute top-4 left-4 z-10 flex flex-col gap-0.5 rounded-xl border border-slate-800/80 bg-[#0b1329]/90 px-3.5 py-2 text-xs backdrop-blur-md shadow-xl">
        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-300">
          Satellite Input
        </span>
        <span className="text-[11px] text-slate-400 font-medium">10 m Resolution</span>
      </div>

      {/* Top Right Canvas Overlay Card */}
      <div className="absolute top-4 right-16 z-10 flex flex-col gap-0.5 rounded-xl border border-blue-500/40 bg-[#0b1329]/90 px-3.5 py-2 text-xs backdrop-blur-md shadow-xl">
        <span className="text-[10px] font-bold uppercase tracking-wider text-blue-300">
          {(10 / settings.scaleFactor).toFixed(1)}m SRM Output
        </span>
        <span className="text-[11px] text-slate-400 font-medium">{settings.scaleFactor}× Enhanced</span>
      </div>

      {/* Floating Right Map Controls Stack */}
      <div className="absolute right-4 top-20 z-20 flex flex-col gap-1.5 rounded-xl border border-slate-800 bg-[#0b1329]/90 p-1 shadow-2xl backdrop-blur-md text-slate-300">
        <button
          type="button"
          onClick={() => handleZoom(1)}
          className="flex h-8 w-8 items-center justify-center rounded-lg hover:bg-blue-600 hover:text-white transition-colors cursor-pointer text-sm font-bold"
          title="Zoom In"
        >
          +
        </button>
        <button
          type="button"
          onClick={() => handleZoom(-1)}
          className="flex h-8 w-8 items-center justify-center rounded-lg hover:bg-blue-600 hover:text-white transition-colors cursor-pointer text-sm font-bold"
          title="Zoom Out"
        >
          −
        </button>
        <div className="h-px bg-slate-800 my-0.5" />
        <button
          type="button"
          onClick={handleRecenter}
          className="flex h-8 w-8 items-center justify-center rounded-lg hover:bg-blue-600 hover:text-white transition-colors cursor-pointer text-xs"
          title="Recenter Map"
        >
          🎯
        </button>
        <button
          type="button"
          onClick={() => handleViewChange(viewMode === 'compare' ? 'satellite' : 'compare')}
          className="flex h-8 w-8 items-center justify-center rounded-lg hover:bg-blue-600 hover:text-white transition-colors cursor-pointer text-xs"
          title="Toggle Compare"
        >
          ↔
        </button>
      </div>

      {/* Split-Screen Slider Handle (< >) */}
      <div
        className="absolute top-0 bottom-0 z-10 w-0.5 cursor-ew-resize bg-blue-500/80 shadow-2xl"
        style={{ left: `${sliderPosition * 100}%` }}
        onPointerDown={onSliderPointerDown}
        onPointerMove={onSliderPointerMove}
        onPointerUp={onSliderPointerUp}
        onPointerCancel={onSliderPointerUp}
      >
        <div className="absolute top-1/2 -ml-5 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border-2 border-blue-400 bg-[#0b1329] text-blue-300 shadow-2xl backdrop-blur-md transition-transform hover:scale-110 active:scale-95 font-bold text-xs">
          ‹ ›
        </div>
      </div>

      {/* Draw Mode Active Tooltip */}
      {drawMode && (
        <div className="absolute left-1/2 top-16 z-20 -translate-x-1/2 rounded-2xl border border-emerald-500/50 bg-emerald-950/90 px-4 py-2 text-xs font-semibold text-emerald-200 shadow-2xl backdrop-blur-md animate-pulse flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-emerald-400 animate-ping" />
          Click and drag on the map to draw a bounding box
        </div>
      )}

      {inspection && (
        <div className="absolute right-16 bottom-16 z-20 w-64 rounded-xl border border-cyan-500/40 bg-[#0b1329]/95 p-3 text-xs shadow-2xl backdrop-blur-md">
          <div className="mb-1 font-bold text-cyan-300">Sub-pixel Inspector</div>
          {inspection.loading ? <span className="text-slate-400">Reading output raster…</span>
            : inspection.error ? <span className="text-rose-300">{inspection.error}</span>
              : <><div className="font-semibold text-white">{inspection.class_name?.replace('_', ' ')}</div>
                <div className="mt-1 text-slate-400">Class fraction: {inspection.class_fraction_percent}%</div>
                <div className="mt-1 font-mono text-[10px] text-slate-500">{inspection.latitude?.toFixed(5)}, {inspection.longitude?.toFixed(5)}</div></>}
        </div>
      )}

      {/* Bottom Map Coordinates & Scale Bar */}
      <div className="absolute bottom-4 left-1/2 z-10 -translate-x-1/2 flex items-center gap-4 rounded-xl border border-slate-800/80 bg-[#0b1329]/90 px-4 py-1.5 text-[11px] font-mono text-slate-300 shadow-xl backdrop-blur-md">
        <span>500 m</span>
        <span className="text-slate-600">|</span>
        <span>
          Lat: {camera.center[1].toFixed(4)} Lon: {camera.center[0].toFixed(4)}
        </span>
        <span className="text-slate-600">|</span>
        <span>Zoom: {camera.zoom.toFixed(0)}</span>
        <span className="text-slate-600">|</span>
        <span className="text-blue-400 font-bold">Scale: {(10 / settings.scaleFactor).toFixed(1)} m/pixel</span>
      </div>
    </div>
  );
}

function eventLngLat(map, e) {
  if (e.lngLat) return e.lngLat;
  if (!Number.isFinite(e.clientX)) return null;
  const rect = map.getCanvas().getBoundingClientRect();
  return map.unproject([e.clientX - rect.left, e.clientY - rect.top]);
}

function camerasClose(map, next) {
  const c = map.getCenter();
  return (
    Math.abs(c.lng - next.center[0]) < 1e-7 &&
    Math.abs(c.lat - next.center[1]) < 1e-7 &&
    Math.abs(map.getZoom() - next.zoom) < 1e-4 &&
    Math.abs(map.getBearing() - next.bearing) < 1e-4 &&
    Math.abs(map.getPitch() - next.pitch) < 1e-4
  );
}

function isXyzTemplate(url) {
  return typeof url === 'string' && url.includes('{z}') && url.includes('{x}') && url.includes('{y}');
}

function addXyzRaster(map, id, url) {
  if (!map || !url) return;
  if (map.getSource(id)) return;
  map.addSource(id, { type: 'raster', tiles: [url], tileSize: 256 });
  map.addLayer({ id, type: 'raster', source: id, paint: { 'raster-opacity': 1 } });
}

function applyRaster(map, id, url) {
  if (!map) return;
  const add = () => {
    if (map.getLayer(id)) map.removeLayer(id);
    if (map.getSource(id)) map.removeSource(id);
    if (!url) return;
    map.addSource(id, { type: 'raster', tiles: [url], tileSize: 256 });
    map.addLayer({ id, type: 'raster', source: id, paint: { 'raster-opacity': 1 } });
  };
  map.isStyleLoaded() ? add() : map.once('load', add);
}

function boxPolygon(a, b) {
  const west = Math.min(a.lng, b.lng);
  const east = Math.max(a.lng, b.lng);
  const south = Math.min(a.lat, b.lat);
  const north = Math.max(a.lat, b.lat);
  return {
    type: 'Polygon',
    coordinates: [[
      [west, south], [east, south], [east, north], [west, north], [west, south],
    ]],
  };
}

function boxIsUsable(geom) {
  const ring = geom.coordinates[0];
  return Math.abs(ring[2][0] - ring[0][0]) > 1e-5 && Math.abs(ring[2][1] - ring[0][1]) > 1e-5;
}

function emptyFc() {
  return { type: 'FeatureCollection', features: [] };
}

function asFc(geom) {
  if (!geom) return emptyFc();
  return { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: geom, properties: {} }] };
}

function ensureAoiLayers(map) {
  if (!map?.isStyleLoaded()) return;
  if (!map.getSource(AOI_SOURCE)) {
    map.addSource(AOI_SOURCE, { type: 'geojson', data: emptyFc() });
    map.addLayer({
      id: AOI_FILL,
      type: 'fill',
      source: AOI_SOURCE,
      paint: { 'fill-color': '#38bdf8', 'fill-opacity': 0.12 },
    });
    map.addLayer({
      id: AOI_LINE,
      type: 'line',
      source: AOI_SOURCE,
      paint: { 'line-color': '#e2e8f0', 'line-width': 2 },
    });
  }
  if (!map.getSource(DRAW_SOURCE)) {
    map.addSource(DRAW_SOURCE, { type: 'geojson', data: emptyFc() });
    map.addLayer({
      id: 'draw-fill',
      type: 'fill',
      source: DRAW_SOURCE,
      paint: { 'fill-color': '#facc15', 'fill-opacity': 0.18 },
    });
    map.addLayer({
      id: 'draw-line',
      type: 'line',
      source: DRAW_SOURCE,
      paint: { 'line-color': '#facc15', 'line-width': 2, 'line-dasharray': [2, 1] },
    });
  }
}

function paintAoi(map, geom) {
  if (!map) return;
  const apply = () => {
    ensureAoiLayers(map);
    map.getSource(AOI_SOURCE)?.setData(asFc(geom));
  };
  map.isStyleLoaded() ? apply() : map.once('load', apply);
}

function paintDrawBox(map, geom) {
  if (!map?.getSource(DRAW_SOURCE)) return;
  map.getSource(DRAW_SOURCE).setData(asFc(geom));
}
