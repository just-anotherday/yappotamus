import { supabase } from '../lib/supabase'
import type { Recipe, RecipeInsert, RecipeUpdate } from '../types/recipeBooks'

function requireData<T>(data: T | null, error: { message: string } | null): T {
  if (error) throw new Error(error.message)
  if (data === null) throw new Error('Supabase returned no recipe data.')
  return data
}

export async function listRecipes(
  recipeBookId: string,
  includeArchived = false,
): Promise<Recipe[]> {
  let query = supabase
    .from('recipes')
    .select('*')
    .eq('recipe_book_id', recipeBookId)
    .order('is_archived', { ascending: true })
    .order('is_favorite', { ascending: false })
    .order('updated_at', { ascending: false })
    .order('name', { ascending: true })
  if (!includeArchived) query = query.eq('is_archived', false)
  const { data, error } = await query
  return requireData(data as Recipe[] | null, error)
}

export async function fetchRecipe(id: string): Promise<Recipe> {
  const { data, error } = await supabase.from('recipes').select('*').eq('id', id).single()
  return requireData(data as Recipe | null, error)
}

export async function createRecipe(input: RecipeInsert): Promise<Recipe> {
  const { data, error } = await supabase.from('recipes').insert(input).select().single()
  return requireData(data as Recipe | null, error)
}

export async function updateRecipe(id: string, input: RecipeUpdate): Promise<Recipe> {
  const { data, error } = await supabase
    .from('recipes')
    .update(input)
    .eq('id', id)
    .select()
    .single()
  return requireData(data as Recipe | null, error)
}

export function moveRecipe(id: string, recipeBookId: string): Promise<Recipe> {
  return updateRecipeCollection(id, recipeBookId)
}

async function updateRecipeCollection(id: string, recipeBookId: string): Promise<Recipe> {
  const { data, error } = await supabase
    .from('recipes')
    .update({ recipe_book_id: recipeBookId })
    .eq('id', id)
    .select()
    .single()
  return requireData(data as Recipe | null, error)
}

export function setRecipeArchived(id: string, isArchived: boolean) {
  return updateRecipe(id, { is_archived: isArchived })
}

export function setRecipeFavorite(id: string, isFavorite: boolean) {
  return updateRecipe(id, { is_favorite: isFavorite })
}

export async function deleteRecipe(id: string): Promise<void> {
  const { error } = await supabase.from('recipes').delete().eq('id', id)
  if (error) throw new Error(error.message)
}
