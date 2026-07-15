// ==============================================================================
// COMPONENT: ErrorBanner
// ==============================================================================

interface ErrorBannerProps {
  message: string;
}

export default function ErrorBanner({ message }: ErrorBannerProps) {
  return (
    <div className="max-w-7xl mx-auto px-4 w-full mt-6">
      <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
        {message}
      </div>
    </div>
  );
}
