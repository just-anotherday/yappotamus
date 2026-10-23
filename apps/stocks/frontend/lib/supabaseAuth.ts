import { createClient, type SupabaseClient } from '@supabase/supabase-js';

export const usesSupabaseAuth = process.env.NEXT_PUBLIC_AUTH_PROVIDER === 'supabase';
let client: SupabaseClient | null = null;

export function getSupabaseAuth(): SupabaseClient {
  if (client) return client;
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key?.startsWith('sb_publishable_')) {
    throw new Error('Supabase login is not configured. Check the frontend environment and rebuild.');
  }
  client = createClient(url, key, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: false },
  });
  return client;
}
