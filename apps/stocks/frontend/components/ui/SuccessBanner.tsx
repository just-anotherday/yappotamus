// ==============================================================================
// COMPONENT: SuccessBanner
// ==============================================================================

interface SuccessBannerProps {
  message: string;
}

export default function SuccessBanner({ message }: SuccessBannerProps) {
  return (
    <div className="max-w-7xl mx-auto px-4 w-full mt-4">
      <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg">
        {message}
      </div>
    </div>
  );
}
