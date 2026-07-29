import { supabase } from '../lib/supabase'
import type {
  RecipeIngredient,
  RecipeIngredientInsert,
  RecipeIngredientUpdate,
} from '../types/recipeBooks'

function requireData<T>(data: T | null, error: { message: string } | null): T {
  if (error) throw new Error(error.message)
  if (data === null) throw new Error('Supabase returned no ingredient data.')
  return data
}

export async function listRecipeIngredients(recipeId: string): Promise<RecipeIngredient[]> {
  const { data, error } = await supabase
    .from('recipe_ingredients')
    .select('*')
    .eq('recipe_id', recipeId)
    .order('position', { ascending: true })
    .order('created_at', { ascending: true })
    .order('id', { ascending: true })
  return requireData(data as RecipeIngredient[] | null, error)
}

export async function createRecipeIngredient(
  input: RecipeIngredientInsert,
): Promise<RecipeIngredient> {
  const { data, error } = await supabase
    .from('recipe_ingredients')
    .insert(input)
    .select()
    .single()
  return requireData(data as RecipeIngredient | null, error)
}

export async function updateRecipeIngredient(
  id: string,
  input: RecipeIngredientUpdate,
): Promise<RecipeIngredient> {
  const { data, error } = await supabase
    .from('recipe_ingredients')
    .update(input)
    .eq('id', id)
    .select()
    .single()
  return requireData(data as RecipeIngredient | null, error)
}

export async function deleteRecipeIngredient(id: string): Promise<void> {
  const { error } = await supabase.from('recipe_ingredients').delete().eq('id', id)
  if (error) throw new Error(error.message)
}

export async function reorderRecipeIngredients(items: RecipeIngredient[]): Promise<void> {
  const results = await Promise.all(items.map((item, position) => (
    supabase
      .from('recipe_ingredients')
      .update({ position })
      .eq('id', item.id)
      .eq('recipe_id', item.recipe_id)
      .eq('user_id', item.user_id)
  )))
  const failure = results.find(result => result.error)
  if (failure?.error) throw new Error(failure.error.message)
}
