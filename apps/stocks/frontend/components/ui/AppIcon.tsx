import type { SVGProps } from 'react';

const paths = {
  dashboard: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  chart: 'M3 3v18h18 M6 15l4-5 4 3 7-8',
  reports: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M8 12h8 M8 16h6',
  news: 'M4 4h13v16H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z M17 8h5v10a2 2 0 0 1-2 2h-3 M6 8h7 M6 12h7 M6 16h4',
  activity: 'M2 12h5l3-8 4 16 3-8h5',
  arrow: 'M5 12h14 M13 6l6 6-6 6',
  lock: 'M6 10h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2z M8 10V6a4 4 0 0 1 8 0v4 M12 15v3',
  eye: 'M2 12s3-7 10-7 10 7 10 7-3 7-10 7S2 12 2 12z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
  eyeOff: 'M3 3l18 18 M10.6 5.1A11 11 0 0 1 12 5c7 0 10 7 10 7a18 18 0 0 1-3 4 M6 6a20 20 0 0 0-4 6s3 7 10 7a13 13 0 0 0 5-1 M10 10a3 3 0 0 0 4 4',
  mail: 'M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z M2 6l10 7L22 6',
  logout: 'M9 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4 M9 12h12 M17 8l4 4-4 4',
  shield: 'M12 2l9 4v6c0 5-9 10-9 10S3 17 3 12V6z M8 12l3 3 5-6',
  search: 'M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
} as const;

export default function AppIcon({ name, ...props }: SVGProps<SVGSVGElement> & { name: keyof typeof paths }) {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}><path d={paths[name]} /></svg>;
}
