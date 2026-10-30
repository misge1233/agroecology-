"use client";

import { Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Combobox } from "@/components/ui/combobox";
import { StepFooter, StepHeader, StepPanel } from "./step-layout";

export function CropStep({
  cropTypes,
  value,
  onChange,
  onSubmit,
  onBack,
  stepLabel,
}: {
  cropTypes: string[];
  value: string | null;
  onChange: (crop: string | null) => void;
  onSubmit: () => void;
  onBack: () => void;
  stepLabel: string;
}) {
  const t = useTranslations("advisor.crop");
  const ta = useTranslations("advisor");
  const tc = useTranslations("common");
  // crop_type values are the dataset's own (English) labels: a data contract.
  const options = cropTypes.map((c) => ({ value: c, label: c }));
  return (
    <StepPanel>
      <StepHeader step={stepLabel} title={t("title")} help={t("help")} />
      <Combobox
        options={options}
        value={value}
        onChange={onChange}
        label={`${t("label")} (${tc("optional")})`}
        placeholder={t("placeholder")}
        emptyLabel={t("noMatch")}
        clearLabel={t("any")}
        className="max-w-lg"
      />
      <StepFooter onBack={onBack}>
        <Button type="button" size="lg" onClick={onSubmit}>
          <Sparkles className="h-4 w-4" aria-hidden />
          {ta("getRecommendation")}
        </Button>
      </StepFooter>
    </StepPanel>
  );
}
