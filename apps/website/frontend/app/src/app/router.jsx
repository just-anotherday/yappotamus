import { createBrowserRouter, Navigate } from 'react-router-dom'
import MainLayout from '../components/layout/MainLayout'
import HomePage from '../features/home/HomePage'
import ProjectsPage from '../features/projects/ProjectsPage'
import RecipesPage from '../features/recipes/RecipesPage'
import RecipePage from '../features/recipes/RecipePage'

function LegacyRecipeRedirect() {
  const recipeParam = new URLSearchParams(window.location.search).get('recipe')
  const recipeId = recipeParam || 'panmee'
  return <Navigate to={`/recipes/${recipeId}`} replace />
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <MainLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'projects', element: <ProjectsPage /> },
      { path: 'recipes', element: <RecipesPage /> },
      { path: 'recipes/:recipeId', element: <RecipePage /> },
      { path: 'recipe', element: <LegacyRecipeRedirect /> },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
])
