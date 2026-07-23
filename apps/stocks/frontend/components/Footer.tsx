export default function Footer() {
  return (
    <footer className="mt-auto border-t border-gray-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/80 backdrop-blur">
      <div className="max-w-6xl mx-auto px-4 py-4 flex flex-col items-center justify-center gap-2">
        <div className="text-center">
          <p className="text-sm font-medium text-gray-700 dark:text-slate-300">
            Stock News Board. Built by{' '}
            <a
              href="https://yapvibes.com"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 font-semibold text-indigo-600 dark:text-indigo-400 hover:underline transition-colors"
            >
              <img
                src="/yapvibes_orange.png"
                alt="YapVibes"
                width={20}
                height={20}
                className="rounded-full"
              />
              yapvibes
            </a>
          </p>
          <p className="text-xs text-gray-400 dark:text-slate-500 mt-0.5">
            An investment research tool. Risk scores are heuristic composites, not financial advice.
          </p>
        </div>
        <div className="mt-2 flex items-center gap-1 text-xs">
          <a
            className="text-indigo-600 dark:text-indigo-400 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
            href="mailto:jason@yapvibes.com"
          >
            Email
          </a>
          {' | '}
          <a
            className="text-indigo-600 dark:text-indigo-400 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
            href="https://instagram.com/yapvibes"
            target="_blank"
            rel="noopener noreferrer"
          >
            Instagram
          </a>
          {' | '}
          <a
            className="text-indigo-600 dark:text-indigo-400 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
            href="https://github.com/just-anotherday"
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub
          </a>
        </div>
      </div>
    </footer>
  );
}
