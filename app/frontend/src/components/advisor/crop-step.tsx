"use client";

import { Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Combobox } from "@/components/ui/combobox";

export function CropStep({
  cropTypes,
  value,
  onChange,
  onSubmit,
}: {
  cropTypes: string[];
  value: string | null;
  onChange: (crop: string | null) => void;
  onSubmit: () => void;
}) {
  const t = useTranslations("advisor.crop");
  const ta = useTranslations("advisor");
  const tc = useTranslations("common");
  // crop_type values are the dataset's own (English) labels — a data contract.
  const options = cropTypes.map((c) => ({ value: c, label: c }));
  return (
    <div className="space-y-5">
      <div>
        <h2 id="advisor-step-title" className="text-xl sm:text-2xl">
          {t("title")}
        </h2>
        <p className="mt-1 text-sm text-muted">{t("help")}</p>
      </div>
      <Combobox
        options={options}
        value={value}
        onChange={onChange}
        label={`${t("label")} (${tc("optional")})`}
        placeholder={t("placeholder")}
        emptyLabel={t("noMatch")}
        clearLabel={t("any")}
        className="max-w-md"
      />
      <div className="flex justify-end">
        <Button type="button" size="lg" onClick={onSubmit}>
          <Sparkles className="h-4 w-4" aria-hidden />
          {ta("getRecommendation")}
        </Button>
      </div>
    </div>
  );
}
