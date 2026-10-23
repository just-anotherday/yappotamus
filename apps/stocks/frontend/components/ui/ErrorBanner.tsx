// ==============================================================================
// COMPONENT: ErrorBanner
// ==============================================================================

interface ErrorBannerProps {
  message: string;
}

export default function ErrorBanner({ message }: ErrorBannerProps) {
  return (
    <div className="max-w-7xl mx-auto px-4 w-full mt-6">
      <div className="bg-negative-soft border border-negative-border text-negative px-4 py-3 rounded-lg">
        {message}
      </div>
    </div>
  );
}
