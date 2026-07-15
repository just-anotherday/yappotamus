export default function SiteFooter() {
  return (
    <footer className="mt-12 border-t border-black/10 bg-yellow-300 px-4 py-8 text-center text-sm font-semibold text-black md:px-6">
      <p>© 2026 Jason Yap — This website is my personal project.</p>
      <p className="mt-2">
        <a className="underline-offset-4 hover:underline" href="mailto:jason@yapvibes.com">
          Email
        </a>{' '}
        |{' '}
        <a
          className="underline-offset-4 hover:underline"
          href="https://instagram.com/yappotamus"
          target="_blank"
          rel="noreferrer"
        >
          Instagram
        </a>{' '}
        |{' '}
        <a
          className="underline-offset-4 hover:underline"
          href="https://github.com/just-anotherday"
          target="_blank"
          rel="noreferrer"
        >
          GitHub
        </a>
      </p>
    </footer>
  )
}
