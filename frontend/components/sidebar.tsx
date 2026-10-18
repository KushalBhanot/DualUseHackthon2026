"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSuggestions } from "@/lib/api";
import { cx } from "./ui";

const NAV = [
  {
    href: "/",
    label: "Board",
    icon: (
      <>
        <rect x="3.5" y="4" width="5" height="16" rx="2" />
        <rect x="9.5" y="4" width="5" height="11" rx="2" />
        <rect x="15.5" y="4" width="5" height="7" rx="2" />
      </>
    ),
  },
  {
    href: "/calls",
    label: "All calls",
    icon: <path d="M6.5 3.5h3l1.5 4-2 1.5a11 11 0 0 0 6 6l1.5-2 4 1.5v3a2 2 0 0 1-2 2A16 16 0 0 1 4.5 5.5a2 2 0 0 1 2-2z" strokeLinejoin="round" />,
  },
  { href: "/analytics", label: "Analytics", icon: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" strokeLinecap="round" /> },
  {
    href: "/setup",
    label: "Setup",
    icon: (
      <>
        <path d="M5 7h14M5 17h14" strokeLinecap="round" />
        <circle cx="9" cy="7" r="2.5" fill="currentColor" fillOpacity="0.15" />
        <circle cx="15" cy="17" r="2.5" fill="currentColor" fillOpacity="0.15" />
      </>
    ),
  },
  { href: "/demo", label: "Demo controls", icon: <path d="M8 5v14l11-7z" strokeLinejoin="round" /> },
];

export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" role="img" aria-label="Night Ledger">
      <rect x="6" y="5" width="20" height="22" rx="4" fill="none" stroke="#3FA3EA" strokeWidth="2.6" />
      <path d="M11 12h10M11 17h10M11 22h6" stroke="#3FA3EA" strokeWidth="2.6" strokeLinecap="round" />
      <circle cx="25" cy="7" r="4" fill="#F6C35B" />
    </svg>
  );
}

export function Sidebar() {
  const path = usePathname();
  const { data: suggestions } = useSuggestions();
  const urgent = suggestions?.some((s) => s.type === "red_not_connected") ?? false;

  return (
    <nav
      aria-label="Main"
      className="flex shrink-0 items-center gap-2 bg-navy px-3 py-2.5 md:w-[76px] md:flex-col md:gap-2.5 md:px-0 md:py-[22px]"
    >
      <Link href="/" className="mr-2 md:mb-[18px] md:mr-0" aria-label="Night Ledger, board">
        <Logo />
      </Link>
      {NAV.map((n) => {
        const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
        return (
          <Link
            key={n.href}
            href={n.href}
            aria-label={n.label}
            title={n.label}
            aria-current={active ? "page" : undefined}
            className={cx(
              "relative flex size-11 items-center justify-center rounded-full transition-colors",
              "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue",
              active ? "bg-white text-navy" : "text-[#9AA3B5] hover:bg-navy-2 hover:text-white",
            )}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
              {n.icon}
            </svg>
            {n.href === "/" && urgent && (
              <span className="absolute right-1.5 top-1.5 size-[9px] rounded-full border-2 border-navy bg-lane-red" aria-label="Red caller not connected" />
            )}
          </Link>
        );
      })}
      <span className="flex-1" />
      <span
        className="hidden size-10 items-center justify-center rounded-full bg-navy-3 text-sm font-bold text-white sm:flex"
        title="K. Mensah, house supervisor"
      >
        KM
      </span>
    </nav>
  );
}
