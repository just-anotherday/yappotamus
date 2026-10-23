import Image from 'next/image';

export default function BrandMark({ size = 48 }: { size?: number }) {
  return <Image
    src="/yapvibes_orange.png"
    alt=""
    width={size}
    height={Math.round(size * 0.8)}
    preload
    style={{ width: size, height: 'auto', flexShrink: 0, borderRadius: 6 }}
  />;
}
