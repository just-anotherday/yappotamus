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
      </div>
    </footer>
  );
}
