import type { Collection, GoogleMapsBootstrap, GoogleMapsConfig, GoogleMapsConfigInput, GradeResult, Guess, ImportResult, Photo, PhotoReviewInput, Place, PublishPreview, Settings, Stats } from './types';

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, options);
  const raw = await response.text();
  let data: unknown = null;
  try { data = raw ? JSON.parse(raw) : null; } catch { data = raw; }
  if (!response.ok) {
    const obj = data && typeof data === 'object' ? (data as { detail?: unknown }) : null;
    throw new Error(typeof obj?.detail === 'string' ? obj.detail : `Request failed (${response.status})`);
  }
  return data as T;
}
const json = (method: string, data: unknown): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
export const api = {
  photos: () => request<Photo[]>('/api/photos'),
  photo: (id: string) => request<Photo>(`/api/photos/${id}`),
  deletePhoto: (id: string) => request<{ok: boolean; originalKept: boolean}>(`/api/photos/${id}`, { method: 'DELETE' }),
  stats: () => request<Stats>('/api/stats'),
  collections: () => request<Collection[]>('/api/collections'),
  createCollection: (title: string, description = '') => request<Collection>('/api/collections', json('POST', { title, description })),
  editCollection: (id: string, title: string, description: string) => request<Collection>(`/api/collections/${id}`, json('PATCH', {title,description})),
  deleteCollection: (id: string) => request(`/api/collections/${id}`, { method: 'DELETE' }),
  savePhoto: (id: string, fields: Record<string, unknown>) => request<Photo>(`/api/photos/${id}`, json('PATCH', fields)),
  bulk: (body: {ids: string[]; addCollectionIds: string[]; addTags: string[]; location?: Record<string, string>}) => request<{updated: number}>('/api/photos/bulk', json('POST', body)),
  import: async (files: File[], collectionId: string) => {
    const form = new FormData();
    form.append('collection_id', collectionId);
    files.forEach(file => form.append('files', file));
    return request<ImportResult>('/api/photos/import', { method: 'POST', body: form });
  },
  tags: () => request<{tags: string[]}>('/api/tags'),
  reviewPhoto: (id: string, body: PhotoReviewInput) => request<Photo>(`/api/photos/${id}/review`, json('PUT', body)),
  setGuess: (id: string, body: Omit<Guess, 'photo_id'>) => request<Photo>(`/api/guess/${id}`, json('PUT', body)),
  removeGuess: (id: string) => request(`/api/guess/${id}`, {method:'DELETE'}),
  gradePin: (id:string, latitude:number, longitude:number) => request<GradeResult>(`/api/guess/${id}/grade-pin`, json('POST',{latitude,longitude})),
  gradeText: (id:string, answer:string) => request<GradeResult>(`/api/guess/${id}/grade-text`, json('POST',{answer})),
  searchPlace: (q: string) => request<Place[]>(`/api/geocode?q=${encodeURIComponent(q)}`),
  reverse: (latitude: number, longitude: number) => request<Place>(`/api/reverse?latitude=${latitude}&longitude=${longitude}`),
  settings: () => request<Settings>('/api/settings'),
  updateSettings: (settings: Partial<Settings>) => request<Settings>('/api/settings', json('PATCH', settings)),
  googleMapsConfig: () => request<GoogleMapsConfig>('/api/maps/config'),
  updateGoogleMapsConfig: (config: GoogleMapsConfigInput) => request<GoogleMapsConfig>('/api/maps/config', json('PUT', config)),
  googleMapsBootstrap: () => request<GoogleMapsBootstrap>('/api/maps/bootstrap'),
  publishPreview: () => request<PublishPreview>('/api/publish/preview'),
  export: (web_root: string) => request<{count:number; skipped:PublishPreview['issues'];webRoot:string}>('/api/publish/export', json('POST',{web_root})),
  github: (web_root: string, message: string) => request<{pushed:boolean;message?:string;branch?:string}>('/api/publish/github', json('POST',{web_root,message})),
};
