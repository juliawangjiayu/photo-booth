import {useEffect, useRef, useState} from 'react';
import {Check, Crosshair, MapPin, Settings2, X} from 'lucide-react';
import {api} from './api';
import {loadGoogleMaps} from './googleMaps';
import {validCoordinates} from './reviewWorkflow';
import type {AnswerRadius} from './types';

type Coordinates = {latitude: number; longitude: number};

const DEFAULT_POSITION: Coordinates = {latitude: 35.6762, longitude: 139.6503};

function markerCoordinates(
  position: google.maps.LatLng | google.maps.LatLngLiteral | google.maps.LatLngAltitude | google.maps.LatLngAltitudeLiteral | null | undefined,
): Coordinates | null {
  if (!position) return null;
  const latitude = typeof position.lat === 'function' ? position.lat() : position.lat;
  const longitude = typeof position.lng === 'function' ? position.lng() : position.lng;
  if (!validCoordinates(latitude, longitude)) return null;
  return {latitude: +latitude.toFixed(6), longitude: +longitude.toFixed(6)};
}

export default function MapPicker({initial, radiusKm, onClose, onConfigure, onConfirm}: {
  initial: Coordinates | null;
  radiusKm: AnswerRadius;
  onClose: () => void;
  onConfigure: () => void;
  onConfirm: (coordinates: Coordinates) => void;
}) {
  const mapEl = useRef<HTMLDivElement>(null);
  const mapRef = useRef<google.maps.Map | null>(null);
  const markerRef = useRef<google.maps.marker.AdvancedMarkerElement | null>(null);
  const circleRef = useRef<google.maps.Circle | null>(null);
  const [coords, setCoords] = useState<Coordinates>(initial ?? DEFAULT_POSITION);
  const [error, setError] = useState('');
  const [needsConfiguration, setNeedsConfiguration] = useState(false);

  useEffect(() => {
    if (!mapEl.current) return;
    let disposed = false;
    let mapClickListener: google.maps.MapsEventListener | null = null;
    let markerDragListener: google.maps.MapsEventListener | null = null;
    const position = initial ?? DEFAULT_POSITION;

    const initialize = async () => {
      try {
        const config = await api.googleMapsBootstrap();
        if (!config.apiKey.trim()) {
          setNeedsConfiguration(true);
          throw new Error('Add a restricted Google Maps browser key in AI & Places to load the map.');
        }
        const {maps, marker} = await loadGoogleMaps(config);
        if (disposed || !mapEl.current) return;
        const map = new maps.Map(mapEl.current, {
          center: {lat: position.latitude, lng: position.longitude},
          zoom: initial ? 10 : 2,
          mapId: config.mapId || 'DEMO_MAP_ID',
          mapTypeControl: false,
          streetViewControl: false,
          fullscreenControl: false,
        });
        const answerMarker = new marker.AdvancedMarkerElement({
          map,
          position: {lat: position.latitude, lng: position.longitude},
          gmpDraggable: true,
          title: 'Guess Where answer Pin',
        });
        const circle = new maps.Circle({
          map,
          center: {lat: position.latitude, lng: position.longitude},
          radius: radiusKm * 1000,
          clickable: false,
          fillColor: '#bb5b43',
          fillOpacity: 0.13,
          strokeColor: '#a94e39',
          strokeOpacity: 0.9,
          strokeWeight: 2,
        });
        mapRef.current = map;
        markerRef.current = answerMarker;
        circleRef.current = circle;
        mapClickListener = map.addListener('click', (event: google.maps.MapMouseEvent) => {
          if (!event.latLng) return;
          const next = markerCoordinates(event.latLng);
          if (next) setCoords(next);
        });
        markerDragListener = answerMarker.addListener('dragend', () => {
          const next = markerCoordinates(answerMarker.position);
          if (next) setCoords(next);
        });
      } catch (reason) {
        if (disposed) return;
        setNeedsConfiguration(true);
        const message = reason instanceof Error ? reason.message : 'Google Map initialization failed';
        setError(`${message} You can still enter coordinates below.`);
      }
    };
    void initialize();
    return () => {
      disposed = true;
      mapClickListener?.remove();
      markerDragListener?.remove();
      if (markerRef.current) markerRef.current.map = null;
      circleRef.current?.setMap(null);
      markerRef.current = null;
      circleRef.current = null;
      mapRef.current = null;
    };
  }, [initial?.latitude, initial?.longitude]);

  useEffect(() => {
    if (!validCoordinates(coords.latitude, coords.longitude)) return;
    const center = {lat: coords.latitude, lng: coords.longitude};
    if (markerRef.current) markerRef.current.position = center;
    circleRef.current?.setCenter(center);
    circleRef.current?.setRadius(radiusKm * 1000);
  }, [coords, radiusKm]);

  const edit = (key: keyof Coordinates, value: string) => {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) setCoords(current => ({...current, [key]: numeric}));
  };
  const valid = validCoordinates(coords.latitude, coords.longitude);

  return <div className="modal-backdrop" onMouseDown={event => {if (event.target === event.currentTarget) onClose();}}>
    <section className="map-modal" role="dialog" aria-modal="true" aria-label="Confirm game answer location">
      <div className="modal-head"><div><p className="eyebrow">GUESS WHERE / ANSWER PIN</p><h2>Confirm the photo location</h2><span>Click or drag the Pin. The shaded circle is the {radiusKm} km correct-answer area.</span></div><button className="icon-btn" onClick={onClose} aria-label="Close map"><X size={19}/></button></div>
      <div ref={mapEl} className="map-canvas" />
      {error && <div className="map-warning"><span>{error}</span>{needsConfiguration && <button className="inline-action" onClick={onConfigure}><Settings2 size={13}/> Open AI & Places settings</button>}</div>}
      <div className="map-bottom"><div className="map-coords"><label>Latitude<input aria-label="Latitude" type="number" step="any" value={coords.latitude} onChange={event => edit('latitude', event.target.value)}/></label><label>Longitude<input aria-label="Longitude" type="number" step="any" value={coords.longitude} onChange={event => edit('longitude', event.target.value)}/></label></div><button className="primary-btn" disabled={!valid} onClick={() => onConfirm(coords)}><Check size={16}/> Confirm pin</button></div>
      <div className="footnote"><MapPin size={13}/> The answer is stored locally, not exported to your public Gallery. <Crosshair size={13}/> Google Maps; provider attribution appears on the map.</div>
    </section>
  </div>;
}
