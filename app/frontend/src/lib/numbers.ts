/**
 * One display-rounding rule for every number a user sees (U9, guard v2).
 * Mirrors app/backend/app/services/numbers.py; both are pinned by
 * number-format.fixture.json. Half away from zero; |v| >= 10 to whole
 * numbers, smaller values to one decimal.
 */
export function roundHalfAway(value: number, decimals = 0): number {
  const f = 10 ** decimals;
  return Math.sign(value) * (Math.floor(Math.abs(value) * f + 0.5) / f);
}

export function displayValue(value: number): number {
  const out = Math.abs(value) >= 10 ? roundHalfAway(value, 0) : roundHalfAway(value, 1);
  return out === 0 ? 0 : out; // no "-0"
}

/** `displayValue` as text without a trailing ".0" ("80", "2.3"). */
export function displayText(value: number): string {
  const v = displayValue(value);
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}