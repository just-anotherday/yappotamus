import { supabase } from '../lib/supabase'
import type { RecipeBook, RecipeBookInsert, RecipeBookUpdate } from '../types/recipeBooks'

function requireData<T>(data: T | null, error: { message: string } | null): T {
  if (error) throw new Error(error.message)
  if (data === null) throw new Error('Supabase returned no Recipe Collection data.')
  return data
}

export async function listRecipeBooks(includeArchived = false): Promise<RecipeBook[]> {
  let query = supabase
    .from('recipe_books')
    .select('*')
    .order('is_archived', { ascending: true })
    .order('updated_at', { ascending: false })
    .order('name', { ascending: true })

  if (!includeArchived) query = query.eq('is_archived', false)
  const { data, error } = await query
  return requireData(data as RecipeBook[] | null, error)
}

export async function createRecipeBook(input: RecipeBookInsert): Promise<RecipeBook> {
  const { data, error } = await supabase.from('recipe_books').insert(input).select().single()
  return requireData(data as RecipeBook | null, error)
}

export async function updateRecipeBook(
  id: string,
  input: RecipeBookUpdate,
): Promise<RecipeBook> {
  const { data, error } = await supabase
    .from('recipe_books')
    .update(input)
    .eq('id', id)
    .select()
    .single()
  return requireData(data as RecipeBook | null, error)
}

export function setRecipeBookArchived(id: string, isArchived: boolean) {
  return updateRecipeBook(id, { is_archived: isArchived })
}

export async function deleteRecipeBook(id: string): Promise<void> {
  const { error } = await supabase.from('recipe_books').delete().eq('id', id)
  if (error) throw new Error(error.message)
}
