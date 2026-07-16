import { useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import SiteHeader from './SiteHeader'
import SiteFooter from './SiteFooter'

const SITE_URL = 'https://yapvibes.com'

const routeMeta = {
  '/': {
    title: 'Jason Yap | Portfolio',
    description:
      'Software engineer building practical software, AI-powered tools, and interactive projects.',
  },
  '/projects': {
    title: 'Projects | Jason Yap',
    description:
      "Explore Jason Yap's software, AI, and game development projects with technical highlights and demos.",
  },
  '/recipes': {
    title: 'Recipes | Jason Yap',
    description: 'A collection of recipes and food projects curated by Jason Yap.',
  },
}

function setMeta(selector, attribute, value) {
  const element = document.querySelector(selector)
  if (element) {
    element.setAttribute(attribute, value)
  }
}

export default function MainLayout() {
  const location = useLocation()

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
  }, [location.pathname])

  useEffect(() => {
    const pathname = location.pathname
    const meta = routeMeta[pathname] || {
      title: 'Jason Yap | Portfolio',
      description: 'Software engineer portfolio by Jason Yap.',
    }
    const pageUrl = `${SITE_URL}${pathname}`

    document.title = meta.title

    setMeta('meta[name="description"]', 'content', meta.description)
    setMeta('link[rel="canonical"]', 'href', pageUrl)

    setMeta('meta[property="og:title"]', 'content', meta.title)
    setMeta('meta[property="og:description"]', 'content', meta.description)
    setMeta('meta[property="og:url"]', 'content', pageUrl)

    setMeta('meta[name="twitter:title"]', 'content', meta.title)
    setMeta('meta[name="twitter:description"]', 'content', meta.description)

    const existingLd = document.getElementById('person-website-jsonld')
    if (existingLd) existingLd.remove()

    const schema = {
      '@context': 'https://schema.org',
      '@graph': [
        {
          '@type': 'Person',
          name: 'Jason Yap',
          url: SITE_URL,
          image: `${SITE_URL}/assets/tempProfilePhoto-432.webp`,
          jobTitle: 'Software Engineer',
          alumniOf: {
            '@type': 'CollegeOrUniversity',
            name: 'University of Central Florida',
          },
          knowsAbout: ['Software Engineering', 'AI', 'Backend Development', 'Game Development'],
        },
        {
          '@type': 'WebSite',
          name: 'Jason Yap Portfolio',
          url: SITE_URL,
        },
      ],
    }

    const script = document.createElement('script')
    script.id = 'person-website-jsonld'
    script.type = 'application/ld+json'
    script.text = JSON.stringify(schema)
    document.head.appendChild(script)

    return () => {
      const staleLd = document.getElementById('person-website-jsonld')
      if (staleLd) staleLd.remove()
    }
  }, [location.pathname])

  return (
    <div className="min-h-screen bg-gradient-to-br from-yellow-200 via-white to-yellow-100 text-zinc-800">
      <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
        <div className="absolute -left-20 top-16 h-72 w-72 rounded-full bg-yellow-300/40 blur-3xl" />
        <div className="absolute -right-24 top-48 h-80 w-80 rounded-full bg-amber-300/30 blur-3xl" />
        <div className="absolute bottom-0 left-1/2 h-80 w-80 -translate-x-1/2 rounded-full bg-black/5 blur-3xl" />
      </div>

      <div className="relative flex min-h-screen flex-col">
        <SiteHeader />
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 md:px-6 md:py-8">
          <Outlet />
        </main>
        <SiteFooter />
      </div>
    </div>
  )
}
