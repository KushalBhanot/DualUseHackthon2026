import type { Metadata, Viewport } from "next";
import { Manrope } from "next/font/google";
import { Providers } from "@/components/providers";
import { Sidebar } from "@/components/sidebar";
import "./globals.css";

const manrope = Manrope({ variable: "--font-manrope", subsets: ["latin"], display: "swap" });

export const metadata: Metadata = {
  title: { default: "Night Ledger", template: "%s · Night Ledger" },
  description: "Supervisor board for the after-hours hospital line: every call sorted, every decision one click.",
};

export const viewport: Viewport = { themeColor: "#121826" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={manrope.variable}>
      <body className="font-sans">
        <Providers>
          <div className="min-h-dvh md:p-5">
            <div className="flex min-h-dvh flex-col overflow-hidden bg-white md:min-h-[calc(100dvh-40px)] md:flex-row md:rounded-[28px] md:border md:border-[#DCE4EE]">
              <Sidebar />
              <main className="flex min-w-0 flex-1 flex-col gap-5 px-4 pb-28 pt-6 sm:px-6 md:px-8 md:pt-7">{children}</main>
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
