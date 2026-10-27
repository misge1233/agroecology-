import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  const t = useTranslations("notFound");
  return (
    <div className="mx-auto max-w-xl px-4 py-20 text-center sm:px-6">
      <p className="text-3xl font-semibold text-text">404</p>
      <h1 className="mt-2 text-xl">{t("title")}</h1>
      <p className="mt-2 text-muted">{t("body")}</p>
      <Button className="mt-6" asChild>
        <Link href="/">{t("home")}</Link>
      </Button>
    </div>
  );
}
