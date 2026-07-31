import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Unstop Calendar Sync",
  description: "Auto-sync your Unstop registrations to Google Calendar",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
