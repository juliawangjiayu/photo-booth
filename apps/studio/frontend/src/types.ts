export type Precision = 'exact' | 'approximate';
export type Difficulty = 'easy' | 'medium' | 'hard';
export type AnswerRadius = 1 | 10 | 50 | 100;
export type Device = ''|'iPhone 6'|'iPhone 11'|'iPhone 14'|'Sony NEX-C3'|'Sony a6400'|'Canon G3QL';
export type Guess = {
  photo_id: string;
  latitude: number;
  longitude: number;
  precision: Precision;
  difficulty: Difficulty;
  answer_name: string;
  answer_description: string;
  answer_radius_km: AnswerRadius;
  enabled: boolean;
  confirmed: boolean;
};
export type Photo = {
  id: string;
  original_name: string;
  created_at: string;
  title: string;
  taken_at: string;
  description: string;
  country: string;
  region: string;
  city: string;
  district: string;
  location_query: string;
  device: Device;
  exif_lat: number | null;
  exif_lng: number | null;
  featured: boolean;
  status: 'draft' | 'modified' | 'published';
  thumbnailUrl: string;
  previewUrl: string;
  collectionIds: string[];
  tags: string[];
  guess: Guess | null;
};
export type Collection = { id: string; title: string; description: string; count: number };
export type Stats = { photos: number; ready: number; needReview: number; gamePool: number; collections: number };
export type Settings = { web_root: string };
export type GoogleMapsBootstrap = { apiKey: string; mapId: string };
export type GoogleMapsConfig = {
  apiKeyConfigured: boolean;
  apiKeyMask: string;
  mapId: string;
};
export type GoogleMapsConfigInput = {
  api_key?: string;
  clear_api_key?: boolean;
  map_id: string;
};
export type MaskedSecret = {
  configured: boolean;
  mask: string;
};
export type AiPlaceTestState = 'untested' | 'passed';
export type AiPlaceDraft = {
  provider: string;
  base_url: string;
  model: string;
  timeout_seconds: number;
  retry_count: number;
  prompt_text: string;
  config_hash: string;
  test_state: AiPlaceTestState;
  tested_hash: string | null;
  test_summary: string | null;
  active_version: number | null;
  created_at: string;
  updated_at: string;
};
export type AiPlaceVersion = {
  version: number;
  provider: string;
  base_url: string;
  model: string;
  timeout_seconds: number;
  retry_count: number;
  prompt_text: string;
  config_hash: string;
  test_summary: string | null;
  lifecycle_state: 'active' | 'superseded';
  activated_at: string;
  remote_published_at: string | null;
  remote_publish_receipt: string | null;
};
export type AiPlaceConfig = {
  draft: AiPlaceDraft;
  active: AiPlaceVersion | null;
  secret: MaskedSecret;
};
export type AiDraftInput = Partial<Pick<AiPlaceDraft,
  'provider' | 'base_url' | 'model' | 'timeout_seconds' | 'retry_count' | 'prompt_text'
>>;
export type AiPlaceInterpretation = {
  status: 'searchable' | 'insufficient';
  normalized_query: string;
  landmark: string;
  locality: string;
  region: string;
  country: string;
  category: string;
  uncertainty: string[];
  confidence: number;
  clarification: string;
};
export type AiPlaceTestResult = {
  interpretation: AiPlaceInterpretation;
  testedHash: string;
  modelLatencyMs: number;
};
export type Place = {
  id?: string;
  name: string;
  formattedAddress?: string;
  latitude: number;
  longitude: number;
  country: string;
  region: string;
  city: string;
  district: string;
  match_quality?: 'broader';
};
export type PublishPreview = { ready: number; issues: {id:string; name:string; problems:string[]}[]; unconfirmedGameEntries:number; note:string };
export type GradeResult = { result:'correct'|'close'|'incorrect'; score:number; confidence:number; explanation:string; distance_km?:number };
export type ImportResult = {
  added: string[];
  duplicates: {name: string; photoId: string}[];
  errors: {name: string; error: string}[];
  reviewIds: string[];
};
export type PhotoReviewInput = {
  taken_at: string;
  description: string;
  device: Exclude<Device, ''>;
  featured: boolean;
  collectionIds: string[];
  tags: string[];
  guess_enabled: boolean;
  guess: Omit<Guess, 'photo_id'> | null;
};
