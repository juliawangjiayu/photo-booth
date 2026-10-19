import type {AiPlaceInterpretation, Place} from './types';

export type PlaceSearchMode = 'automatic' | 'forced';
export type PlaceSearchOutcome = {
  places: Place[];
  source: 'direct' | 'interpreted' | 'insufficient';
  originalQuery: string;
  queryUsed: string;
  modelAttempted: boolean;
  interpretation: AiPlaceInterpretation | null;
  clarification: string;
  modelError: string;
};

export type SearchPlaces = (query: string) => Promise<Place[]>;
export type ReinterpretPlace = (query: string) => Promise<AiPlaceInterpretation>;

export async function searchWithFallback(
  rawQuery: string,
  searchPlaces: SearchPlaces,
  reinterpret: ReinterpretPlace,
  mode: PlaceSearchMode = 'automatic',
): Promise<PlaceSearchOutcome> {
  const originalQuery = rawQuery.trim();
  if (!originalQuery) {
    return {
      places: [], source: 'direct', originalQuery, queryUsed: '', modelAttempted: false,
      interpretation: null, clarification: '', modelError: '',
    };
  }

  if (mode === 'automatic') {
    const direct = await searchPlaces(originalQuery);
    if (direct.length) {
      return {
        places: direct, source: 'direct', originalQuery, queryUsed: originalQuery,
        modelAttempted: false, interpretation: null, clarification: '', modelError: '',
      };
    }
  }

  let interpretation: AiPlaceInterpretation;
  try {
    interpretation = await reinterpret(originalQuery);
  } catch (error) {
    return {
      places: [], source: 'direct', originalQuery, queryUsed: originalQuery,
      modelAttempted: true, interpretation: null, clarification: '',
      modelError: error instanceof Error ? error.message : String(error),
    };
  }

  if (interpretation.status === 'insufficient' || !interpretation.normalized_query.trim()) {
    return {
      places: [], source: 'insufficient', originalQuery, queryUsed: originalQuery,
      modelAttempted: true, interpretation,
      clarification: interpretation.clarification || 'Add a city, region, or landmark clue.',
      modelError: '',
    };
  }

  const queryUsed = interpretation.normalized_query.trim();
  const places = await searchPlaces(queryUsed);
  return {
    places, source: 'interpreted', originalQuery, queryUsed, modelAttempted: true,
    interpretation, clarification: interpretation.clarification, modelError: '',
  };
}
