/**
 * Full document navigation (not a client transition). Used for a language
 * switch: changing the [locale] root layout client-side would make React
 * create the <head> theme script in the browser (React 19.2 warns), and a
 * fresh server render also brings the right <html lang> and fonts.
 * A function of its own so tests can observe it.
 */
export function hardNavigate(url: string): void {
  window.location.assign(url);
}
