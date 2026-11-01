"use client";

import { useMemo, useState } from "react";
import Image from "next/image";
import { Leaf } from "lucide-react";
import { cn } from "@/lib/utils";
import { practiceImagePath } from "@/lib/practice-images";

type PracticeImageProps = {
  practice: string;
  /** Localised alt text, e.g. "Illustration of Mulching". */
  alt: string;
  /** Localised fallback caption when no image exists. */
  fallbackLabel: string;
  /** Localised display name shown in the text fallback (U2 item 5). */
  title?: string;
  className?: string;
  priority?: boolean;
  sizes?: string;
};

// A 16×9 blurred placeholder in the palette (≈300 bytes): paints at once on
// slow links, so the card never shows a blank rectangle before the photo.
const BLUR_DATA_URL =
  "data:image/svg+xml;charset=utf-8," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="9"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#e3efe8"/><stop offset="1" stop-color="#f3eadf"/></linearGradient></defs><rect width="16" height="9" fill="url(#g)"/></svg>'
  );

/** A practice photo (own, alias or first component) under /public/practices, via next/image. */
export function PracticeImage({
  practice,
  alt,
  fallbackLabel,
  title,
  className,
  priority,
  sizes = "(max-width: 768px) 100vw, 480px",
}: PracticeImageProps) {
  // Resolved against the list of photos on disk: a missing photo costs no request (U9, D12).
  const path = useMemo(() => practiceImagePath(practice), [practice]);
  const [failed, setFailed] = useState(false);

  if (failed || !path) {
    return (
      <div
        className={cn(
          "flex aspect-[16/9] w-full items-center justify-center bg-gradient-to-br from-primary-soft to-secondary-soft",
          className
        )}
        role="img"
        aria-label={fallbackLabel}
      >
        <div className="flex flex-col items-center gap-2 px-6 text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-control bg-surface text-primary shadow-1">
            <Leaf className="h-6 w-6" aria-hidden />
          </span>
          {title ? <p className="text-base font-semibold text-text">{title}</p> : null}
          <p className="text-xs font-medium uppercase tracking-widest text-muted">{fallbackLabel}</p>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("relative aspect-[16/9] w-full overflow-hidden bg-surface-2", className)}>
      <Image
        src={path}
        alt={alt}
        fill
        className="object-cover"
        sizes={sizes}
        priority={priority}
        loading={priority ? undefined : "lazy"}
        placeholder="blur"
        blurDataURL={BLUR_DATA_URL}
        onError={() => setFailed(true)}
      />
    </div>
  );
}
