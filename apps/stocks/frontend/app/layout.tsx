import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { WatchlistConfigProvider } from "@/lib/WatchlistConfigContext";
import ThemeProvider from "@/components/ThemeProvider";
import AppHeader from "@/components/AppHeader";
import Footer from "@/components/Footer";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import AuthGate from "@/components/AuthGate";
import { NewsSyncProvider } from "@/components/NewsSync";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "YapVibes · Your market workspace",
  description: "Your private workspace for market news, watchlists, and research.",
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
      <body className="min-h-full flex flex-col">
        <ThemeProvider>
          <AuthGate>
            <NewsSyncProvider>
            <WatchlistConfigProvider>
              <AppHeader />
              <ErrorBoundary>
                <main id="main-content" tabIndex={-1} className="workspace-main min-h-0 flex-1">{children}</main>
              </ErrorBoundary>
              <Footer />
            </WatchlistConfigProvider>
            </NewsSyncProvider>
          </AuthGate>
        </ThemeProvider>
      </body>
    </html>
  );
}
