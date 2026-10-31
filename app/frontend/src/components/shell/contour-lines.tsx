/**
 * Decorative terrace contour lines for tinted page header bands (Advisor,
 * About): stacked curves in the primary colour at low opacity, anchored right
 * and fading out to the left. Place inside a `relative isolate overflow-hidden`
 * container. Server- and client-safe.
 */
export function ContourLines() {
  const lines = Array.from({ length: 9 }, (_, i) => i);
  return (
    <svg
      aria-hidden
      className="pointer-events-none absolute inset-y-0 right-0 -z-10 h-full w-full max-w-3xl text-primary opacity-[0.14] [mask-image:linear-gradient(to_left,black_35%,transparent)]"
      viewBox="0 0 600 240"
      preserveAspectRatio="xMaxYMid slice"
      fill="none"
    >
      {lines.map((i) => (
        <path
          key={i}
          d={`M0 ${40 + i * 22} C 120 ${10 + i * 22}, 220 ${80 + i * 22}, 340 ${44 + i * 22} S 520 ${4 + i * 22}, 600 ${36 + i * 22}`}
          stroke="currentColor"
          strokeWidth="1.5"
        />
      ))}
    </svg>
  );
}
