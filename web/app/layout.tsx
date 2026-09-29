import type { Metadata } from "next";
import { Be_Vietnam_Pro, Fraunces, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const beVietnam = Be_Vietnam_Pro({
  variable: "--font-be-vietnam",
  subsets: ["latin", "vietnamese"], // the dataset's diacritics are the point
  weight: ["400", "500", "600", "700"],
  display: "swap",
});
const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  weight: ["500", "600"],
  display: "swap",
});
const jetbrains = JetBrains_Mono({
  variable: "--font-jetbrains",
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "VMLU Reading Review — bảng nghiệm thu 400 câu",
  description: "Human-acceptance review of the 400-item reading-comprehension eval set (issue #3).",
};

/** Set the theme BEFORE first paint. Without this the page paints with the OS
 *  preference and then snaps to the stored choice — a white flash on dark and a
 *  black one on light. Kept dependency-free and tiny on purpose: it runs inline,
 *  before React, and its failure mode is "no stored preference", not a crash. */
const THEME_BOOT = `(function(){try{var t=localStorage.getItem("vmlu-theme");if(t==="light"||t==="dark"){document.documentElement.dataset.theme=t;}}catch(e){}})();`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // suppressHydrationWarning: the script above mutates <html> before React
    // hydrates, so the server-rendered attributes will not match the client.
    <html
      lang="vi"
      suppressHydrationWarning
      className={`${beVietnam.variable} ${fraunces.variable} ${jetbrains.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
      </head>
      <body className="min-h-full bg-paper text-ink">{children}</body>
    </html>
  );
}
