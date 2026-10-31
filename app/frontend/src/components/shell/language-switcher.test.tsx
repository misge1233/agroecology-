// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import en from "../../../messages/en.json";
import { LanguageSwitcher } from "./language-switcher";

const hardNavigate = vi.fn();
vi.mock("@/lib/hard-navigate", () => ({ hardNavigate: (url: string) => hardNavigate(url) }));
vi.mock("@/i18n/navigation", () => ({
  usePathname: () => "/advisor",
  getPathname: ({ href, locale }: { href: string; locale: string }) => `/${locale}${href}`,
}));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("lat=8.38&lon=39.37&family=Erosion+control+and+water+management"),
}));

describe("LanguageSwitcher", () => {
  it("switches the locale while keeping the route and the query string", async () => {
    const user = userEvent.setup();
    render(
      <NextIntlClientProvider locale="en" messages={en}>
        <LanguageSwitcher />
      </NextIntlClientProvider>
    );
    const trigger = screen.getByRole("combobox", { name: "Change language" });
    expect(trigger).toHaveTextContent("English");

    await user.click(trigger);
    await user.click(await screen.findByRole("option", { name: "አማርኛ" }));

    // A full navigation to the same route and query in the new language.
    expect(hardNavigate).toHaveBeenCalledWith(
      "/am/advisor?lat=8.38&lon=39.37&family=Erosion+control+and+water+management"
    );
  });
});
