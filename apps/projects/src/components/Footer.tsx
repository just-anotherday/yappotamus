export default function Footer() {
  return (
    <footer className="mt-auto border-t border-gray-200 bg-white text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400">
      <div className="mx-auto max-w-4xl px-4 py-6 text-center text-sm">
        <p>© 2026 Jason Yap — This website is my personal project.</p>
        <p className="mt-2">
          <a
            className="text-blue-600 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:text-blue-400"
            href="mailto:jason@yapvibes.com"
          >
            Email
          </a>
          {' | '}
          <a
            className="text-blue-600 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:text-blue-400"
            href="https://instagram.com/yappotamus"
            target="_blank"
            rel="noopener noreferrer"
          >
            Instagram
          </a>
          {' | '}
          <a
            className="text-blue-600 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:text-blue-400"
            href="https://github.com/just-anotherday"
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub
          </a>
        </p>
      </div>
    </footer>
  )
}
