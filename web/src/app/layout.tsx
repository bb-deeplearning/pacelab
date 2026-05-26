import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "pacelab — evidence-based F1 driver scouting",
  description:
    "Per-driver scouting reports for Formula 1. Every number on every page has a derivation, a sample size, and a confidence interval.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
