import {importLibrary, setOptions} from '@googlemaps/js-api-loader';
import type {GoogleMapsBootstrap, Place} from './types';

export type GoogleLibraryName = 'maps' | 'marker' | 'places';
export type GoogleLibraryImporter = (library: GoogleLibraryName) => Promise<unknown>;
export type GooglePlaceSearchRequest = {
  textQuery: string;
  fields: string[];
  maxResultCount: number;
  locationBias?: google.maps.LatLngBoundsLiteral;
};
export type GooglePlaceSearch = (
  request: GooglePlaceSearchRequest,
) => Promise<{places: GooglePlaceLike[]}>;

export type GoogleLibraries = {
  maps: google.maps.MapsLibrary;
  marker: google.maps.MarkerLibrary;
  places: google.maps.PlacesLibrary;
};

type CoordinateLike = number | (() => number);
export type GooglePlaceLike = {
  id?: string | null;
  displayName?: string | {text?: string | null} | null;
  formattedAddress?: string | null;
  location?: {lat: CoordinateLike; lng: CoordinateLike} | null;
  addressComponents?: Array<{
    longText?: string | null;
    shortText?: string | null;
    types?: string[];
  }>;
};

export type PlaceSearchOptions = {
  locationBias?: google.maps.LatLngBoundsLiteral;
};

let loadedKey = '';
let librariesPromise: Promise<GoogleLibraries> | null = null;

function coordinate(value: CoordinateLike | undefined): number {
  return typeof value === 'function' ? value() : Number(value);
}

function displayName(place: GooglePlaceLike): string {
  if (typeof place.displayName === 'string') return place.displayName;
  return place.displayName?.text ?? place.formattedAddress ?? place.id ?? 'Unknown place';
}

function component(place: GooglePlaceLike, acceptedTypes: string[]): string {
  const match = place.addressComponents?.find(item =>
    acceptedTypes.some(type => item.types?.includes(type)),
  );
  return match?.longText ?? match?.shortText ?? '';
}

export function normalizeGooglePlace(place: GooglePlaceLike): Place {
  const latitude = coordinate(place.location?.lat);
  const longitude = coordinate(place.location?.lng);
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
    throw new TypeError('Google Place has no finite coordinates');
  }
  return {
    id: place.id ?? '',
    name: displayName(place),
    formattedAddress: place.formattedAddress ?? '',
    latitude,
    longitude,
    country: component(place, ['country']),
    region: component(place, ['administrative_area_level_1']),
    city: component(place, ['locality', 'postal_town', 'administrative_area_level_2']),
    district: component(place, [
      'sublocality_level_1',
      'sublocality',
      'administrative_area_level_3',
    ]),
  };
}

function defaultImporter(library: GoogleLibraryName): Promise<unknown> {
  return importLibrary(library);
}

export function loadGoogleMaps(
  config: GoogleMapsBootstrap,
  importer: GoogleLibraryImporter = defaultImporter,
): Promise<GoogleLibraries> {
  const apiKey = config.apiKey.trim();
  if (!apiKey) return Promise.reject(new Error('Configure a Google Maps browser key first'));
  if (librariesPromise && loadedKey === apiKey) return librariesPromise;
  if (librariesPromise && loadedKey !== apiKey) {
    return Promise.reject(new Error('Google Maps key changed; reload Photo Booth to apply it'));
  }
  loadedKey = apiKey;
  if (importer === defaultImporter) {
    setOptions({key: apiKey, v: 'weekly', authReferrerPolicy: 'origin'});
  }
  librariesPromise = Promise.all([
    importer('maps'),
    importer('marker'),
    importer('places'),
  ]).then(([maps, marker, places]) => ({
    maps: maps as google.maps.MapsLibrary,
    marker: marker as google.maps.MarkerLibrary,
    places: places as google.maps.PlacesLibrary,
  }));
  return librariesPromise;
}

async function defaultSearch(request: GooglePlaceSearchRequest): Promise<{places: GooglePlaceLike[]}> {
  if (!librariesPromise) throw new Error('Google Maps has not been loaded');
  const libraries = await librariesPromise;
  return libraries.places.Place.searchByText(
    request as google.maps.places.SearchByTextRequest,
  );
}

export async function searchGooglePlaces(
  query: string,
  options: PlaceSearchOptions = {},
  search: GooglePlaceSearch = defaultSearch,
): Promise<Place[]> {
  const textQuery = query.trim();
  if (!textQuery) return [];
  const request: GooglePlaceSearchRequest = {
    textQuery,
    fields: ['id', 'displayName', 'formattedAddress', 'location', 'addressComponents'],
    maxResultCount: 5,
  };
  if (options.locationBias) request.locationBias = options.locationBias;
  const result = await search(request);
  const normalized: Place[] = [];
  for (const place of result.places.slice(0, 5)) {
    try {
      normalized.push(normalizeGooglePlace(place));
    } catch (error) {
      if (!(error instanceof TypeError)) throw error;
    }
  }
  return normalized;
}

export function resetGoogleMapsForTests(): void {
  loadedKey = '';
  librariesPromise = null;
}
