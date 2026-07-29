import { supabase } from '../lib/supabase'
import type { RecipeStep, RecipeStepInsert, RecipeStepUpdate } from '../types/recipeBooks'

function requireData<T>(data: T | null, error: { message: string } | null): T {
  if (error) throw new Error(error.message)
  if (data === null) throw new Error('Supabase returned no recipe-step data.')
  return data
}

export async function listRecipeSteps(recipeId: string): Promise<RecipeStep[]> {
  const { data, error } = await supabase
    .from('recipe_steps')
    .select('*')
    .eq('recipe_id', recipeId)
    .order('position', { ascending: true })
    .order('created_at', { ascending: true })
    .order('id', { ascending: true })
  return requireData(data as RecipeStep[] | null, error)
}

export async function createRecipeStep(input: RecipeStepInsert): Promise<RecipeStep> {
  const { data, error } = await supabase.from('recipe_steps').insert(input).select().single()
  return requireData(data as RecipeStep | null, error)
}

export async function updateRecipeStep(
  id: string,
  input: RecipeStepUpdate,
): Promise<RecipeStep> {
  const { data, error } = await supabase
    .from('recipe_steps')
    .update(input)
    .eq('id', id)
    .select()
    .single()
  return requireData(data as RecipeStep | null, error)
}

export async function deleteRecipeStep(id: string): Promise<void> {
  const { error } = await supabase.from('recipe_steps').delete().eq('id', id)
  if (error) throw new Error(error.message)
}

export async function reorderRecipeSteps(items: RecipeStep[]): Promise<void> {
  const results = await Promise.all(items.map((item, position) => (
    supabase
      .from('recipe_steps')
      .update({ position })
      .eq('id', item.id)
      .eq('recipe_id', item.recipe_id)
      .eq('user_id', item.user_id)
  )))
  const failure = results.find(result => result.error)
  if (failure?.error) throw new Error(failure.error.message)
}
