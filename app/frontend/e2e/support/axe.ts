import type { Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * axe-core runner. `@axe-core/playwright` bundles an older `playwright-core`
 * type for `Page`, so the test's Page is cast once here instead of in every spec.
 */
export function axe(page: Page): AxeBuilder {
  return new AxeBuilder({ page: page as unknown as ConstructorParameters<typeof AxeBuilder>[0]["page"] });
}
