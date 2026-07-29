export type RecipeDifficulty = 'EASY' | 'MEDIUM' | 'HARD'
export type TemperatureUnit = 'F' | 'C'

export interface RecipeBook {
  id: string
  user_id: string
  name: string
  description: string
  cover_label: string | null
  is_archived: boolean
  created_at: string
  updated_at: string
}

export interface RecipeBookInsert {
  user_id: string
  name: string
  description?: string
  cover_label?: string | null
  is_archived?: boolean
}

export type RecipeBookUpdate = Partial<Omit<RecipeBookInsert, 'user_id'>>

export interface Recipe {
  id: string
  recipe_book_id: string
  user_id: string
  name: string
  description: string
  category: string
  cuisine: string
  servings: number | null
  prep_minutes: number | null
  cook_minutes: number | null
  difficulty: RecipeDifficulty | null
  notes: string
  source: string | null
  is_favorite: boolean
  is_archived: boolean
  created_at: string
  updated_at: string
}

export interface RecipeInsert {
  recipe_book_id: string
  user_id: string
  name: string
  description?: string
  category?: string
  cuisine?: string
  servings?: number | null
  prep_minutes?: number | null
  cook_minutes?: number | null
  difficulty?: RecipeDifficulty | null
  notes?: string
  source?: string | null
  is_favorite?: boolean
  is_archived?: boolean
}

export type RecipeUpdate = Partial<Omit<RecipeInsert, 'recipe_book_id' | 'user_id'>>

export interface RecipeIngredient {
  id: string
  recipe_id: string
  user_id: string
  name: string
  quantity_text: string
  quantity_value: number | null
  unit: string
  preparation_note: string
  position: number
  created_at: string
  updated_at: string
}

export interface RecipeIngredientInsert {
  recipe_id: string
  user_id: string
  name: string
  quantity_text?: string
  quantity_value?: number | null
  unit?: string
  preparation_note?: string
  position?: number
}

export type RecipeIngredientUpdate = Partial<
  Omit<RecipeIngredientInsert, 'recipe_id' | 'user_id'>
>

export interface RecipeStep {
  id: string
  recipe_id: string
  user_id: string
  instruction: string
  duration_minutes: number | null
  temperature_value: number | null
  temperature_unit: TemperatureUnit | null
  position: number
  created_at: string
  updated_at: string
}

export interface RecipeStepInsert {
  recipe_id: string
  user_id: string
  instruction: string
  duration_minutes?: number | null
  temperature_value?: number | null
  temperature_unit?: TemperatureUnit | null
  position?: number
}

export type RecipeStepUpdate = Partial<Omit<RecipeStepInsert, 'recipe_id' | 'user_id'>>
