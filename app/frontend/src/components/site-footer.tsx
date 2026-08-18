import Link from "next/link";
import { Leaf } from "lucide-react";

const COLS = [
  {
    title: "Product",
    links: [
      { href: "/chat", label: "Advisor" },
      { href: "/dashboard", label: "Analyst view" },
      { href: "/#how", label: "Method" },
    ],
  },
  {
    title: "Science",
    links: [
      { href: "/#powers", label: "System architecture" },
      { href: "/#data", label: "Data provenance" },
      { href: "/#honesty", label: "Evidence honesty" },
    ],
  },
  {
    title: "Coverage",
    links: [
      { href: "/dashboard", label: "Ethiopia map" },
      { href: "/#families", label: "Practice families" },
      { href: "/#objectives", label: "Objectives" },
    ],
  },
];

export function SiteFooter() {
  return (
    <footer className="border-t border-edge bg-elevated">
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-14 sm:px-6 md:grid-cols-[1.35fr_1fr_1fr_1fr]">
        <div>
          <Link href="/" className="inline-flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-leaf text-white">
              <Leaf className="h-3.5 w-3.5" aria-hidden />
            </span>
            <span className="font-display text-lg font-semibold tracking-tight text-ink">
              AgroAdvisor-ET
            </span>
          </Link>
          <p className="mt-4 max-w-sm text-sm leading-relaxed text-mute">
            Evidence-ranked agroecological practice recommendations for
            Ethiopian farms — field trials, geospatial context, and transparent
            confidence on request.
          </p>
        </div>
        {COLS.map((col) => (
          <div key={col.title}>
            <p className="eyebrow">{col.title}</p>
            <ul className="mt-4 space-y-2.5">
              {col.links.map((l) => (
                <li key={l.href}>
                  <Link
                    href={l.href}
                    className="text-sm text-body transition hover:text-leaf-deep dark:hover:text-leaf-bright"
                  >
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-edge">
        <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-4 text-[12px] text-mute sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>© {new Date().getFullYear()} AgroAdvisor-ET. Ranking instrument — not field guarantees.</p>
          <p>Designed for extension, research, and policy audiences in Ethiopia.</p>
        </div>
      </div>
    </footer>
  );
}
