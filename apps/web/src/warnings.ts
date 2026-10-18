/**
 * Warning codes (docs/contracts/agent-research.md, "Typed fields"). The readable text stays in `warnings`; codes say
 * which of ClipCart's own warnings are present without matching on wording.
 */
import type { Recommendation } from "@contracts";

export type WarningCode = NonNullable<Recommendation["warningCodes"]>[number];

/**
 * Pulls one coded warning out of a warnings list. The server appends the warnings it adds itself after any provider
 * text, one per code and in code order (search pipeline and research verification alike), so the codes line up with
 * the tail of `warnings`. `text` is null when the code is present but the lists don't line up; callers then show
 * their own wording and leave `rest` untouched.
 */
export function takeWarning(
  warnings: string[],
  codes: readonly WarningCode[] | null | undefined,
  code: WarningCode,
): { present: boolean; text: string | null; rest: string[] } {
  const i = codes?.indexOf(code) ?? -1;
  if (!codes || i < 0) return { present: false, text: null, rest: warnings };
  const at = warnings.length - codes.length + i;
  if (warnings.length < codes.length) return { present: true, text: null, rest: warnings };
  return { present: true, text: warnings[at], rest: warnings.filter((_, j) => j !== at) };
}

/** Fallback wording for seller_claims_unverified, used only when the server's own sentence can't be located. */
export const SELLER_CLAIMS_TEXT = "Metal, stones and authenticity are the seller's description; ClipCart doesn't verify them.";
