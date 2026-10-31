/**
 * Theme bootstrap shared by the server layout and the client ThemeProvider.
 * Lives outside any "use client" module so the server layout can read the
 * string itself (exports of a client module reach server code only as
 * references).
 */
export const THEME_STORAGE_KEY = "agro-theme";

/**
 * Inline script for <head>: applies the stored/preferred theme class BEFORE
 * first paint so there is no flash. Rendered by the server layout as a plain
 * <script>, which React hydrates but never creates on the client.
 */
export const THEME_INIT_SCRIPT = `(function(){try{var s=localStorage.getItem("${THEME_STORAGE_KEY}");var d=s?s==="dark":window.matchMedia("(prefers-color-scheme: dark)").matches;if(d)document.documentElement.classList.add("dark");}catch(e){}})();`;
