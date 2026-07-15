import { NavLink } from 'react-router-dom'

const navBase =
  'rounded-lg px-4 py-2 text-sm font-semibold tracking-wide transition-all duration-200'

export default function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-black/10 bg-yellow-300/95 backdrop-blur">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-4 md:px-6">
        <NavLink to="/" className="font-['Permanent_Marker'] text-3xl text-orange-500">
          yapvibes.
        </NavLink>

        <nav className="flex items-center gap-2 rounded-xl bg-black/10 p-1.5">
          <NavLink
            to="/"
            className={({ isActive }) =>
              `${navBase} ${isActive ? 'bg-black text-yellow-300 shadow-md' : 'text-black hover:bg-black/10'}`
            }
            end
          >
            Home
          </NavLink>
          <NavLink
            to="/projects"
            className={({ isActive }) =>
              `${navBase} ${isActive ? 'bg-black text-yellow-300 shadow-md' : 'text-black hover:bg-black/10'}`
            }
          >
            Projects
          </NavLink>
        </nav>
      </div>
    </header>
  )
}
