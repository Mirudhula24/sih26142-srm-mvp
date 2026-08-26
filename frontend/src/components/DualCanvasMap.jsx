import { useEffect, useRef } from 'react';
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

/**
 * Two MapLibre instances under a curtain slider.
 *
 * MapLibre is pinned to v3.6 LTS: v4 changed the internal WebGL camera matrices and
 * loses context when Deck.gl shares the canvas. See docs/TECH_CLASHES.md (Clash 4).
 */
export default function DualCanvasMap({ inputTileUrl, outputTileUrl }) {
  const leftRef = useRef(null);
  const rightRef = useRef(null);
  const leftMap = useRef(null);
  const rightMap = useRef(null);
  const syncing = useRef(false);

  const { camera, setCamera, sliderPosition, setSliderPosition } = useSrmStore();

  useEffect(() => {
    const opts = { style: BASEMAP, center: camera.center, zoom: camera.zoom, attributionControl: false };
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
      setCamera({
        center: [m.getCenter().lng, m.getCenter().lat],
        zoom: m.getZoom(),
        bearing: m.getBearing(),
        pitch: m.getPitch(),
      });
    });

    return () => {
      leftMap.current?.remove();
      rightMap.current?.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Swap the raster sources whenever a new job produces new tile endpoints.
  useEffect(() => {
    applyRaster(leftMap.current, 'input-raster', inputTileUrl);
  }, [inputTileUrl]);

  useEffect(() => {
    applyRaster(rightMap.current, 'srm-raster', outputTileUrl);
  }, [outputTileUrl]);

  const onDrag = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    setSliderPosition(Math.min(0.98, Math.max(0.02, x)));
  };

  return (
    <div
      className="relative h-full w-full overflow-hidden bg-slate-900"
      onPointerMove={(e) => e.buttons === 1 && onDrag(e)}
    >
      <div ref={leftRef} className="absolute inset-0" />
      <div
        ref={rightRef}
        className="absolute inset-0"
        style={{ clipPath: `inset(0 0 0 ${sliderPosition * 100}%)` }}
      />

      <div
        className="absolute top-0 bottom-0 z-10 w-1 cursor-ew-resize bg-white shadow-lg"
        style={{ left: `${sliderPosition * 100}%` }}
      >
        <div className="absolute top-1/2 -ml-4 h-8 w-8 -translate-y-1/2 rounded-full border-2 border-slate-300 bg-white" />
      </div>

      <span className="absolute bottom-3 left-3 z-10 rounded bg-black/60 px-2 py-1 text-xs text-white">
        Sentinel-2 · 10 m input
      </span>
      <span className="absolute bottom-3 right-3 z-10 rounded bg-black/60 px-2 py-1 text-xs text-white">
        SRM · 2.5 m thematic map
      </span>
    </div>
  );
}

function applyRaster(map, id, url) {
  if (!map || !url) return;
  const add = () => {
    if (map.getLayer(id)) map.removeLayer(id);
    if (map.getSource(id)) map.removeSource(id);
    map.addSource(id, { type: 'raster', tiles: [url], tileSize: 256 });
    map.addLayer({ id, type: 'raster', source: id, paint: { 'raster-opacity': 1 } });
  };
  map.isStyleLoaded() ? add() : map.once('load', add);
}
