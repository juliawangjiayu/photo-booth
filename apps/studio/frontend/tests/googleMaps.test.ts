import assert from 'node:assert/strict';
import test from 'node:test';
import {
  loadGoogleMaps,
  normalizeGooglePlace,
  resetGoogleMapsForTests,
  searchGooglePlaces,
  type GoogleLibraryImporter,
  type GooglePlaceSearch,
} from '../src/googleMaps.ts';

test('normalizes a mixed-script place with partial address data', () => {
  const place = normalizeGooglePlace({
    id: 'peak-tram',
    displayName: 'The Peak Tram 太平山缆车',
    formattedAddress: '33 Garden Road, Central, Hong Kong',
    location: {lat: () => 22.2778, lng: () => 114.1592},
    addressComponents: [
      {longText: '香港', shortText: 'HK', types: ['country']},
      {longText: '中西區', types: ['administrative_area_level_1']},
      {longText: 'Central', types: ['locality']},
    ],
  });
  assert.deepEqual(place, {
    id: 'peak-tram',
    name: 'The Peak Tram 太平山缆车',
    formattedAddress: '33 Garden Road, Central, Hong Kong',
    latitude: 22.2778,
    longitude: 114.1592,
    country: '香港',
    region: '中西區',
    city: 'Central',
    district: '',
  });
});

test('drops places without finite coordinates', async () => {
  const search: GooglePlaceSearch = async () => ({places: [
    {id: 'invalid', displayName: 'No location'},
    {id: 'also-invalid', displayName: 'Bad location', location: {lat: NaN, lng: 1}},
    {id: 'valid', displayName: 'Valid', location: {lat: 26.08, lng: 119.30}},
  ]});
  const places = await searchGooglePlaces('于山 福州市', {}, search);
  assert.deepEqual(places.map(place => place.id), ['valid']);
});

test('loader returns the same promise for the same browser key', async () => {
  resetGoogleMapsForTests();
  const calls: string[] = [];
  const importer: GoogleLibraryImporter = async library => {
    calls.push(library);
    return {library};
  };
  const config = {apiKey: 'AIza-test', mapId: 'map-id'};
  const first = loadGoogleMaps(config, importer);
  const second = loadGoogleMaps(config, importer);
  assert.strictEqual(first, second);
  await first;
  assert.deepEqual(calls.sort(), ['maps', 'marker', 'places']);
});

test('search passes an intentional viewport only as location bias', async () => {
  let received: Record<string, unknown> | undefined;
  const search: GooglePlaceSearch = async request => {
    received = request;
    return {places: []};
  };
  const locationBias = {north: 23, south: 22, east: 115, west: 113};
  await searchGooglePlaces('太平山顶 缆车站', {locationBias}, search);
  assert.deepEqual(received, {
    textQuery: '太平山顶 缆车站',
    fields: ['id', 'displayName', 'formattedAddress', 'location', 'addressComponents'],
    maxResultCount: 5,
    locationBias,
  });
  assert.equal('locationRestriction' in (received ?? {}), false);
});
