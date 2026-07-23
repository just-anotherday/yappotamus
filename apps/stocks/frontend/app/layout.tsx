import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { WatchlistConfigProvider } from "@/lib/WatchlistConfigContext";
import ThemeProvider from "@/components/ThemeProvider";
import AppHeader from "@/components/AppHeader";
import Footer from "@/components/Footer";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import AuthGate from "@/components/AuthGate";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Stock Dashboard",
  description: "Search and view real-time stock market data",
  icons: {
    icon: '/yapvibes_orange.png',
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-gray-50 dark:bg-gradient-to-br dark:from-slate-800 dark:via-gray-900 dark:to-slate-700">
        <ThemeProvider>
          <AuthGate>
            <WatchlistConfigProvider>
              <AppHeader />
              <ErrorBoundary>
                <main className="min-h-0 flex-1">{children}</main>
              </ErrorBoundary>
              <Footer />
            </WatchlistConfigProvider>
          </AuthGate>
        </ThemeProvider>
      </body>
    </html>
  );
}
