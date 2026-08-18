"use client";

import { useCallback, useMemo, useState } from "react";
import Image from "next/image";
import { Leaf } from "lucide-react";
import { cn } from "@/lib/utils";
import { PRACTICE_IMAGE_EXTENSIONS, practiceSlug } from "@/lib/practice-images";

type PracticeImageProps = {
  practice: string;
  className?: string;
  priority?: boolean;
  sizes?: string;
};

export function PracticeImage({
  practice,
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
          "relative flex aspect-[16/10] w-full items-center justify-center overflow-hidden rounded-2xl bg-gradient-to-br from-leaf/25 via-brand-teal/20 to-brand-violet/15",
          className
        )}
        aria-hidden
      >
        <div className="absolute inset-0 opacity-30 [background-image:radial-gradient(circle_at_30%_20%,white_0%,transparent_50%)]" />
        <div className="relative flex flex-col items-center gap-2 px-6 text-center">
          <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-white/80 text-leaf shadow-soft backdrop-blur">
            <Leaf className="h-7 w-7" />
          </span>
          <p className="text-[11px] font-medium uppercase tracking-widest text-ink/50">
            Photo coming soon
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "relative aspect-[16/10] w-full overflow-hidden rounded-2xl bg-panel",
        className
      )}
    >
      <Image
        src={path}
        alt={`Illustration: ${practice}`}
        fill
        className="object-cover"
        sizes={sizes}
        priority={priority}
        onError={onError}
      />
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-ink/55 via-ink/10 to-transparent" />
    </div>
  );
}
