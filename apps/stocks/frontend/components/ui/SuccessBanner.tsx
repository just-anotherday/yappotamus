// ==============================================================================
// COMPONENT: SuccessBanner
// ==============================================================================

interface SuccessBannerProps {
  message: string;
}

export default function SuccessBanner({ message }: SuccessBannerProps) {
  return (
    <div className="max-w-7xl mx-auto px-4 w-full mt-4">
      <div className="bg-positive-soft border border-positive-border text-positive px-4 py-3 rounded-lg">
        {message}
      </div>
    </div>
  );
}
