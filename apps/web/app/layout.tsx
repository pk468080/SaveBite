import type { Metadata } from "next";
import { ToastProvider } from "@/components/ui/toast";
import { config } from "@/lib/config";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "SaveBite — Surplus food, rescued at a discount",
    template: "%s · SaveBite",
  },
  description:
    "SaveBite is a surplus-food marketplace: bakeries, cafes, and restaurants list unsold food at a discount, and customers reserve and collect it before it goes to waste.",
  metadataBase: new URL(config.siteUrl),
  icons: { icon: "/favicon.svg" },
  openGraph: {
    type: "website",
    siteName: "SaveBite",
    title: "SaveBite — Surplus food, rescued at a discount",
    description:
      "Reserve surplus food from nearby bakeries, cafes, and restaurants and collect it before it goes to waste.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
