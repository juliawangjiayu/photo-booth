import { useEffect, useRef, useState } from 'react';
import maplibregl, { type GeoJSONSource, type Map as MapType, type Marker } from 'maplibre-gl';
import { Check, Crosshair, MapPin, X } from 'lucide-react';
import {answerCirclePolygon} from './reviewWorkflow';
import type {AnswerRadius} from './types';

type Coordinates = {latitude: number; longitude: number};
export default function MapPicker({ initial, maptilerKey, radiusKm, onClose, onConfirm }: {
  initial: Coordinates | null;
  maptilerKey: string;
  radiusKm: AnswerRadius;
  onClose: () => void;
  onConfirm: (coordinates: Coordinates) => void;
}) {
  const mapEl = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapType | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const [coords, setCoords] = useState<Coordinates>(initial ?? {latitude: 35.6762,longitude: 139.6503});
  const [error, setError] = useState('');
  useEffect(() => {
    if (!mapEl.current) return;
    const position = initial ?? {latitude: 35.6762,longitude: 139.6503};
    const style = maptilerKey.trim()
      ? `https://api.maptiler.com/maps/streets-v2/style.json?key=${encodeURIComponent(maptilerKey.trim())}`
      : 'https://tiles.openfreemap.org/styles/liberty';
    let map: MapType;
    try {
      map = new maplibregl.Map({container:mapEl.current,style,center:[position.longitude,position.latitude],zoom:initial?10:2,maxZoom:15});
    } catch (e) { setError(e instanceof Error ? e.message : 'Map initialization failed'); return; }
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    const marker = new maplibregl.Marker({color:'#bb5b43', draggable:true}).setLngLat([position.longitude,position.latitude]).addTo(map);
    markerRef.current = marker;
    const updateCircle = (point: Coordinates) => {
      (map.getSource('answer-radius') as GeoJSONSource | undefined)?.setData(
        answerCirclePolygon(point, radiusKm),
      );
    };
    map.on('load', () => {
      map.addSource('answer-radius', {
        type: 'geojson',
        data: answerCirclePolygon(position, radiusKm),
      });
      map.addLayer({
        id: 'answer-radius-fill',
        type: 'fill',
        source: 'answer-radius',
        paint: {'fill-color': '#bb5b43', 'fill-opacity': 0.13},
      });
      map.addLayer({
        id: 'answer-radius-line',
        type: 'line',
        source: 'answer-radius',
        paint: {'line-color': '#a94e39', 'line-width': 2},
      });
    });
    marker.on('dragend',()=> {
      const point=marker.getLngLat();
      const next={latitude:+point.lat.toFixed(6),longitude:+point.lng.toFixed(6)};
      setCoords(next);
      updateCircle(next);
    });
    map.on('click',event=> {
      const next={latitude:+event.lngLat.lat.toFixed(6),longitude:+event.lngLat.lng.toFixed(6)};
      setCoords(next);
      marker.setLngLat([next.longitude,next.latitude]);
      updateCircle(next);
    });
    map.on('error',()=>setError('Map tiles may be unavailable. You can still enter coordinates below.'));
    return () => {marker.remove();map.remove();mapRef.current=null;markerRef.current=null;};
  }, [initial?.latitude,initial?.longitude,maptilerKey,radiusKm]);
  const edit = (key:keyof Coordinates, value:string) => {
    const n=Number(value);
    if (Number.isFinite(n)) {
      const next={...coords,[key]:n};setCoords(next);
      if (Math.abs(next.latitude)<=90 && Math.abs(next.longitude)<=180) {
        markerRef.current?.setLngLat([next.longitude,next.latitude]);
        (mapRef.current?.getSource('answer-radius') as GeoJSONSource | undefined)?.setData(
          answerCirclePolygon(next, radiusKm),
        );
      }
    }
  };
  const valid=Number.isFinite(coords.latitude)&&Number.isFinite(coords.longitude)&&Math.abs(coords.latitude)<=90&&Math.abs(coords.longitude)<=180;
  return <div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose();}}>
    <section className="map-modal" role="dialog" aria-modal="true" aria-label="Confirm game answer location">
      <div className="modal-head"><div><p className="eyebrow">GUESS WHERE / ANSWER PIN</p><h2>Confirm the photo location</h2><span>Click or drag the Pin. The shaded circle is the {radiusKm} km correct-answer area.</span></div><button className="icon-btn" onClick={onClose} aria-label="Close map"><X size={19}/></button></div>
      <div ref={mapEl} className="map-canvas" />
      {error && <div className="map-warning">{error}</div>}
      <div className="map-bottom"><div className="map-coords"><label>Latitude<input aria-label="Latitude" type="number" step="any" value={coords.latitude} onChange={e=>edit('latitude',e.target.value)}/></label><label>Longitude<input aria-label="Longitude" type="number" step="any" value={coords.longitude} onChange={e=>edit('longitude',e.target.value)}/></label></div><button className="primary-btn" disabled={!valid} onClick={()=>onConfirm(coords)}><Check size={16}/> Confirm pin</button></div>
      <div className="footnote"><MapPin size={13}/> The answer is stored locally, not exported to your public Gallery. <Crosshair size={13}/> OpenFreeMap / MapLibre; map attribution appears on the map.</div>
    </section>
  </div>;
}
