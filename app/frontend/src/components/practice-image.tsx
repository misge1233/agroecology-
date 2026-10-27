"use client";

import { useCallback, useMemo, useState } from "react";
import Image from "next/image";
import { Leaf } from "lucide-react";
import { cn } from "@/lib/utils";
import { PRACTICE_IMAGE_EXTENSIONS, practiceSlug } from "@/lib/practice-images";

type PracticeImageProps = {
  practice: string;
  /** Localised alt text, e.g. "Illustration of Mulching". */
  alt: string;
  /** Localised fallback caption when no image exists. */
  fallbackLabel: string;
  className?: string;
  priority?: boolean;
  sizes?: string;
};

/** One of the 55 practice photos under /public/practices, via next/image. */
export function PracticeImage({
  practice,
  alt,
  fallbackLabel,
  className,
  priority,
  sizes = "(max-width: 768px) 100vw, 480px",
}: PracticeImageProps) {
  const slug = useMemo(() => practiceSlug(practice), [practice]);
  const [extIdx, setExtIdx] = useState(0);
  const [failed, setFailed] = useState(false);

  const path = `/practices/${slug}.${PRACTICE_IMAGE_EXTENSIONS[extIdx]}`;

  const onError = useCallback(() => {
    if (extIdx < PRACTICE_IMAGE_EXTENSIONS.length - 1) {
      setExtIdx((i) => i + 1);
      return;
    }
    setFailed(true);
  }, [extIdx]);

  if (failed) {
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
          <p className="text-xs font-medium uppercase tracking-widest text-muted">{fallbackLabel}</p>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("relative aspect-[16/9] w-full overflow-hidden bg-surface-2", className)}>
      <Image src={path} alt={alt} fill className="object-cover" sizes={sizes} priority={priority} onError={onError} />
    </div>
  );
}
