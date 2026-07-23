import { useState } from 'react'
import { useAuth } from '../hooks/useAuth'
import { useTheme } from '../hooks/useTheme'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isSignUp, setIsSignUp] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const { signIn, signUp } = useAuth()
  const { theme, toggleTheme } = useTheme()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      if (isSignUp) {
        const { error } = await signUp(email, password)
        if (error) {
          setError(error.message)
        } else {
          // Check email confirmation needed
          setError('Check your email for the confirmation link.')
        }
      } else {
        const { error } = await signIn(email, password)
        if (error) setError(error.message)
      }
    } catch (err) {
      setError('An unexpected error occurred.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950">
      <button
        onClick={toggleTheme}
        className="absolute top-4 right-4 p-2 bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-100 rounded-md hover:bg-gray-300 dark:hover:bg-gray-600 transition cursor-pointer"
        title={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
      >
        {theme === 'light' ? '🌙' : '☀️'}
      </button>
      <div className="bg-white border border-gray-200 dark:border-gray-600 dark:bg-gray-850 p-8 rounded-lg shadow-md w-full max-w-sm">
        <h1 className="mb-6 text-center text-2xl font-bold text-gray-800 dark:text-gray-50">
          Planner
        </h1>
        <p className="text-center text-gray-500 dark:text-gray-300 mb-6">
          {isSignUp ? 'Create an account' : 'Sign in to your account'}
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-gray-900 placeholder:text-gray-500 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-400 dark:border-gray-500 dark:bg-gray-700 dark:text-gray-50 dark:placeholder:text-gray-400"
            />
          </div>

          <div>
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-gray-900 placeholder:text-gray-500 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-400 dark:border-gray-500 dark:bg-gray-700 dark:text-gray-50 dark:placeholder:text-gray-400"
            />
          </div>

          {error && (
            <p className="text-red-500 dark:text-red-400 text-sm">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 transition disabled:opacity-50"
          >
            {loading ? '...' : isSignUp ? 'Sign Up' : 'Sign In'}
          </button>
        </form>

        <div className="mt-4 text-center text-sm">
          <button
            onClick={() => setIsSignUp(!isSignUp)}
            className="text-blue-500 hover:underline"
          >
            {isSignUp ? 'Already have an account? Sign in' : "Don't have an account? Sign up"}
          </button>
        </div>
      </div>
    </div>
  )
}
