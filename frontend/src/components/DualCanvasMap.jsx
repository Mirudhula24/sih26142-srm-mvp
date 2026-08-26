import { useCallback, useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
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

const AOI_SRC = 'aoi';
const EMPTY_FC = { type: 'FeatureCollection', features: [] };

const rectangle = (a, b) => ({
  type: 'Polygon',
  coordinates: [[
    [a.lng, a.lat], [b.lng, a.lat], [b.lng, b.lat], [a.lng, b.lat], [a.lng, a.lat],
  ]],
});

/**
 * Two MapLibre instances under a curtain slider.
 *
 * MapLibre is pinned to v3.6 LTS: v4 changed the internal WebGL camera matrices and
 * loses context when Deck.gl shares the canvas. See docs/TECH_CLASHES.md (Clash 4).
 */
export default function DualCanvasMap({ inputLayer, outputLayer, drawMode, onAoiDrawn }) {
  const leftRef = useRef(null);
  const rightRef = useRef(null);
  const leftMap = useRef(null);
  const rightMap = useRef(null);
  const syncing = useRef(false);
  const drawModeRef = useRef(drawMode);
  const onAoiDrawnRef = useRef(onAoiDrawn);
  const drawStart = useRef(null);

  const [draggingSlider, setDraggingSlider] = useState(false);
  const { cameraRequest, setCamera, aoi, sliderPosition, setSliderPosition } = useSrmStore();

  // Handlers are registered once against the map instances, so they read the current
  // values through refs rather than re-binding on every render.
  useEffect(() => { drawModeRef.current = drawMode; }, [drawMode]);
  useEffect(() => { onAoiDrawnRef.current = onAoiDrawn; }, [onAoiDrawn]);

  const eachMap = useCallback((fn) => {
    [leftMap.current, rightMap.current].forEach((m) => m && fn(m));
  }, []);

  useEffect(() => {
    const opts = {
      style: BASEMAP,
      center: [77.108, 28.709],
      zoom: 12,
      attributionControl: false,
    };
    leftMap.current = new maplibregl.Map({ container: leftRef.current, ...opts });
    rightMap.current = new maplibregl.Map({ container: rightRef.current, ...opts });

    // Bidirectional camera lock. The `syncing` guard breaks the feedback loop that
    // would otherwise make both maps fight each other and drop the frame rate.
    const link = (from, to) => () => {
      if (syncing.current) return;
      syncing.current = true;
      to.jumpTo({
        center: from.getCenter(),
        zoom: from.getZoom(),
        bearing: from.getBearing(),
        pitch: from.getPitch(),
      });
      syncing.current = false;
    };
    const onLeft = link(leftMap.current, rightMap.current);
    const onRight = link(rightMap.current, leftMap.current);
    leftMap.current.on('move', onLeft);
    rightMap.current.on('move', onRight);

    leftMap.current.on('moveend', () => {
      const m = leftMap.current;
      const c = m.getCenter();
      setCamera({ center: [c.lng, c.lat], zoom: m.getZoom(), bearing: m.getBearing(), pitch: m.getPitch() });
    });

    [leftMap.current, rightMap.current].forEach((map) => {
      map.on('load', () => {
        map.addSource(AOI_SRC, { type: 'geojson', data: EMPTY_FC });
        map.addLayer({
          id: `${AOI_SRC}-fill`,
          type: 'fill',
          source: AOI_SRC,
          paint: { 'fill-color': '#38bdf8', 'fill-opacity': 0.12 },
        });
        map.addLayer({
          id: `${AOI_SRC}-line`,
          type: 'line',
          source: AOI_SRC,
          paint: { 'line-color': '#0ea5e9', 'line-width': 2 },
        });
      });
      attachDrawHandlers(map, drawModeRef, drawStart, onAoiDrawnRef);
    });

    return () => {
      leftMap.current?.remove();
      rightMap.current?.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Move the maps when something outside them asks for a new camera -- picking a cached
  // region, for instance. Driven by an explicit request rather than by the stored camera,
  // which the maps themselves write on every pan and would echo straight back.
  useEffect(() => {
    if (!cameraRequest) return;
    eachMap((m) => m.jumpTo({
      center: cameraRequest.center,
      zoom: cameraRequest.zoom ?? m.getZoom(),
      bearing: cameraRequest.bearing ?? 0,
      pitch: cameraRequest.pitch ?? 0,
    }));
  }, [cameraRequest, eachMap]);

  // Reflect the committed AOI on both canvases.
  useEffect(() => {
    const data = aoi ? { type: 'Feature', geometry: aoi, properties: {} } : EMPTY_FC;
    eachMap((m) => {
      const apply = () => m.getSource(AOI_SRC)?.setData(data);
      m.isStyleLoaded() ? apply() : m.once('idle', apply);
    });
  }, [aoi, eachMap]);

  // Panning is disabled while drawing so a drag defines a box instead of moving the map.
  useEffect(() => {
    eachMap((m) => (drawMode ? m.dragPan.disable() : m.dragPan.enable()));
    eachMap((m) => m.getCanvas().style.setProperty('cursor', drawMode ? 'crosshair' : ''));
  }, [drawMode, eachMap]);

  useEffect(() => { applyRaster(leftMap.current, 'input-raster', inputLayer); }, [inputLayer]);
  useEffect(() => { applyRaster(rightMap.current, 'srm-raster', outputLayer); }, [outputLayer]);

  // The curtain only tracks the pointer once the handle itself is grabbed. Listening on
  // the whole container made every map pan drag the slider too.
  useEffect(() => {
    if (!draggingSlider) return;
    const move = (e) => {
      const rect = leftRef.current.parentElement.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width;
      setSliderPosition(Math.min(0.98, Math.max(0.02, x)));
    };
    const up = () => setDraggingSlider(false);
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    return () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
  }, [draggingSlider, setSliderPosition]);

  return (
    <div className="relative h-full w-full overflow-hidden bg-slate-900">
      <div ref={leftRef} className="absolute inset-0" />
      <div
        ref={rightRef}
        className="absolute inset-0"
        style={{ clipPath: `inset(0 0 0 ${sliderPosition * 100}%)` }}
      />

      <div
        className="absolute top-0 bottom-0 z-10 w-1 bg-white shadow-lg"
        style={{ left: `${sliderPosition * 100}%` }}
      >
        <button
          type="button"
          aria-label="Drag to compare input and output"
          onPointerDown={() => setDraggingSlider(true)}
          className="absolute top-1/2 -ml-4 h-8 w-8 -translate-y-1/2 cursor-ew-resize rounded-full border-2 border-slate-300 bg-white"
        />
      </div>

      {drawMode && (
        <span className="absolute left-1/2 top-3 z-10 -translate-x-1/2 rounded bg-sky-600 px-3 py-1 text-xs font-medium text-white">
          Drag on the map to set the area of interest
        </span>
      )}

      <span className="absolute bottom-3 left-3 z-10 rounded bg-black/60 px-2 py-1 text-xs text-white">
        Sentinel-2 · 10 m input
      </span>
      <span className="absolute bottom-3 right-3 z-10 rounded bg-black/60 px-2 py-1 text-xs text-white">
        SRM · 2.5 m thematic map
      </span>
    </div>
  );
}

/** Drag-to-draw a bounding box, drawn natively rather than via mapbox-gl-draw. */
function attachDrawHandlers(map, drawModeRef, drawStart, onAoiDrawnRef) {
  map.on('mousedown', (e) => {
    if (!drawModeRef.current) return;
    e.preventDefault();
    drawStart.current = e.lngLat;
  });

  map.on('mousemove', (e) => {
    if (!drawModeRef.current || !drawStart.current) return;
    map.getSource(AOI_SRC)?.setData({
      type: 'Feature',
      geometry: rectangle(drawStart.current, e.lngLat),
      properties: {},
    });
  });

  map.on('mouseup', (e) => {
    if (!drawModeRef.current || !drawStart.current) return;
    const start = drawStart.current;
    drawStart.current = null;
    // Ignore a stray click: a box needs actual extent to be a valid AOI.
    if (Math.abs(e.lngLat.lng - start.lng) < 1e-4 || Math.abs(e.lngLat.lat - start.lat) < 1e-4) {
      return;
    }
    onAoiDrawnRef.current?.(rectangle(start, e.lngLat));
  });
}

/**
 * Add imagery to a canvas.
 *
 * Two shapes are accepted. A tile template is used when TiTiler is serving the COG.
 * A `{url, coordinates}` pair becomes a MapLibre `image` source pinned to its four
 * corners — that is how sync mode renders results with no tile server running.
 */
function applyRaster(map, id, layer) {
  if (!map || !layer) return;
  const add = () => {
    if (map.getLayer(id)) map.removeLayer(id);
    if (map.getSource(id)) map.removeSource(id);

    if (typeof layer === 'string') {
      map.addSource(id, { type: 'raster', tiles: [layer], tileSize: 256 });
    } else if (layer.url && layer.coordinates) {
      map.addSource(id, { type: 'image', url: layer.url, coordinates: layer.coordinates });
    } else {
      return;
    }
    // Keep the AOI outline above any imagery added later.
    map.addLayer(
      { id, type: 'raster', source: id, paint: { 'raster-fade-duration': 0 } },
      map.getLayer(`${AOI_SRC}-fill`) ? `${AOI_SRC}-fill` : undefined,
    );
  };
  map.isStyleLoaded() ? add() : map.once('idle', add);
}
