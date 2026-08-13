import { supabase } from '../lib/supabase'

export const RECIPE_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp']
export const RECIPE_IMAGE_MAX_BYTES = 5 * 1024 * 1024

export function validateRecipeImage(file: File) {
  if (!RECIPE_IMAGE_TYPES.includes(file.type)) return 'Choose a JPEG, PNG, or WebP image.'
  if (file.size > RECIPE_IMAGE_MAX_BYTES) return 'Recipe images must be 5 MB or smaller.'
  return null
}

export async function uploadRecipeImage(userId: string, file: File) {
  const validation = validateRecipeImage(file)
  if (validation) throw new Error(validation)
  const extension = file.type === 'image/png' ? 'png' : file.type === 'image/webp' ? 'webp' : 'jpg'
  const path = `${userId}/${crypto.randomUUID()}.${extension}`
  const { error } = await supabase.storage.from('recipe-images').upload(path, file, { contentType: file.type, upsert: false })
  if (error) throw new Error(error.message)
  const { data } = supabase.storage.from('recipe-images').getPublicUrl(path)
  return { path, url: data.publicUrl }
}

export async function removeRecipeImage(path: string | null | undefined) {
  if (!path) return
  const { error } = await supabase.storage.from('recipe-images').remove([path])
  if (error) throw new Error(error.message)
}
