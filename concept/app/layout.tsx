import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Yes Coach! — Real-Time AI League Coaching",
  description:
    "An always-on-top overlay that watches your League of Legends game live and coaches you in real time, powered by the Riot Live Client API and Gemini.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
