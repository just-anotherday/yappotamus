import { supabase } from '../lib/supabase'
import {
  validateUserSettingsRow,
  validateUserSettingsUpdate,
  type UserSettingsInsert,
  type UserSettingsRow,
  type UserSettingsUpdate,
  type UserSettingsWritableFields,
} from '../types/userSettings'

interface SupabaseFailure {
  code?: string
  message?: string
}

export class UserSettingsServiceError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'UserSettingsServiceError'
  }
}

function safeSettingsError(error: unknown): UserSettingsServiceError {
  const failure = error as SupabaseFailure | null
  if (failure?.code === '42501') {
    return new UserSettingsServiceError(
      'Your settings could not be accessed for this account.',
    )
  }
  if (failure?.code === '23514' || failure?.code === '22P02') {
    return new UserSettingsServiceError(
      'A settings value was rejected. Refresh and try again.',
    )
  }
  if (failure?.message?.toLowerCase().includes('network')) {
    return new UserSettingsServiceError(
      'Your settings could not be saved because the network is unavailable.',
    )
  }
  return new UserSettingsServiceError(
    'Your settings could not be saved. Please try again.',
  )
}

function isPrimaryKeyConflict(error: unknown): boolean {
  return (error as SupabaseFailure | null)?.code === '23505'
}

export async function fetchCurrentUserSettings(
  userId: string,
): Promise<UserSettingsRow | null> {
  const { data, error } = await supabase
    .from('user_settings')
    .select('*')
    .eq('user_id', userId)
    .maybeSingle()

  if (error) throw safeSettingsError(error)
  if (data === null) return null

  const settings = validateUserSettingsRow(data)
  if (settings.user_id !== userId) {
    throw new UserSettingsServiceError(
      'The settings response did not belong to the current account.',
    )
  }
  return settings
}

export async function insertInitialSettings(
  userId: string,
  values: UserSettingsWritableFields,
): Promise<UserSettingsRow> {
  const input: UserSettingsInsert = { user_id: userId, ...values }
  const { data, error } = await supabase
    .from('user_settings')
    .insert(input)
    .select('*')
    .single()

  if (error) {
    if (isPrimaryKeyConflict(error)) {
      const existing = await fetchCurrentUserSettings(userId)
      if (existing) return existing
    }
    throw safeSettingsError(error)
  }

  const settings = validateUserSettingsRow(data)
  if (settings.user_id !== userId) {
    throw new UserSettingsServiceError(
      'The created settings did not belong to the current account.',
    )
  }
  return settings
}

export async function updateCurrentUserSettings(
  userId: string,
  patch: UserSettingsUpdate,
): Promise<UserSettingsRow> {
  const validatedPatch = validateUserSettingsUpdate(patch)
  if (Object.keys(validatedPatch).length === 0) {
    const existing = await fetchCurrentUserSettings(userId)
    if (!existing) {
      throw new UserSettingsServiceError('No settings row exists for this account.')
    }
    return existing
  }

  const { data, error } = await supabase
    .from('user_settings')
    .update(validatedPatch)
    .eq('user_id', userId)
    .select('*')
    .single()

  if (error) throw safeSettingsError(error)

  const settings = validateUserSettingsRow(data)
  if (settings.user_id !== userId) {
    throw new UserSettingsServiceError(
      'The updated settings did not belong to the current account.',
    )
  }
  return settings
}
