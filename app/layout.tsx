import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "BroadcastIQ",
  description:
    "AI-powered TV analytics, streaming diagnostics and actionable insights platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-background text-foreground relative overflow-x-hidden`}
      >
        {/* HT Magenta ambient glow */}
        <div className="pointer-events-none fixed inset-0 -z-10">
          <div className="absolute top-[-150px] left-1/2 -translate-x-1/2 h-[500px] w-[500px] rounded-full bg-[hsl(var(--primary)/0.15)] blur-[120px]" />
        </div>

        {children}
      </body>
    </html>
  );
}
