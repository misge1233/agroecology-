import { redirect } from "@/i18n/navigation";

/** The old analyst view lives on as the Advisor (U1). */
export default async function DashboardRedirect({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect({ href: "/advisor", locale });
}
