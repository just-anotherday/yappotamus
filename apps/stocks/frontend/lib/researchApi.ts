import { apiFetch } from './apiFetch';
import { requireOk } from './apiError';
import { API_BASE } from './serviceUrls';

export async function researchRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(`${API_BASE}/api/research${path}`, { cache: 'no-store', ...init });
  await requireOk(response, 'Research data could not be loaded');
  return response.json();
}
