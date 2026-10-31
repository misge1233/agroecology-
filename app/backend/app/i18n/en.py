"""English catalog — the reference. Must stay byte-identical to the pre-U1 texts."""
from __future__ import annotations

STRINGS: dict[str, str] = {
    # ------------------------------------------------------------ prompt
    "prompt.reply_in": "Reply in English.",
    # ------------------------------------------------------------ chat: social
    "social.with_prior": (
        "You're welcome, glad it helped. Ask anytime if you want to know why, "
        "how to apply it, or try a different location, crop, or goal."
    ),
    "social.no_prior": (
        "You're welcome. Whenever you're ready, tell me where your farm is, the challenge "
        "you face and your goal, and I'll recommend suitable practices."
    ),
    # ------------------------------------------------------------ chat: errors
    "error.rate_limit": (
        "The AI text service has reached its usage limit for now. Please wait a "
        "few minutes and try again, or use the Advisor page for instant recommendations."
    ),
    "error.generic": (
        "I couldn't score practices for that request. Check the location is in "
        "Ethiopia and that the challenge/objective pair is supported, then try again."
    ),
    # ------------------------------------------------------------ chat: clarification
    "clarify.all_missing": (
        "I can recommend evidence-based CSA practices once I know three things: "
        "your **challenge** (e.g. erosion control), your **objective** "
        "(e.g. reduce soil loss), and your **location** (the nearest town or village in "
        "Ethiopia, or coordinates)."
    ),
    "clarify.understood_prefix": "I understood ",
    "clarify.understood_join": ", ",
    "clarify.understood_suffix": ". ",
    "clarify.place": "I placed your farm near **{place}**",
    "clarify.challenge": "challenge **{challenge}**",
    "clarify.objective": "objective **{objective}**",
    "clarify.ask_challenge": (
        "which **challenge** fits best: crop production, livestock, soil fertility, "
        "erosion & water, or agro-forestry"
    ),
    "clarify.ask_objective_erosion": (
        "your **objective**: reduce soil loss / erosion, reduce runoff, "
        "or improve water-use efficiency"
    ),
    "clarify.ask_objective": (
        "your **objective** (e.g. increase yield, reduce soil loss, improve soil organic matter)"
    ),
    "clarify.ask_location": (
        "your **location**: the nearest town or village in Ethiopia, or coordinates (latitude, longitude)"
    ),
    "clarify.one": "To rank practices from field evidence, please share {ask}.",
    "clarify.two": "Please share {a}, and {b}.",
    "clarify.many": "Please share {asks}.",
    "clarify.many_join": "; ",
    # ------------------------------------------------------------ chat: evidence summary
    "summary.no_evidence": (
        "I couldn't find enough field evidence for that combination. "
        "Try a nearby location or a different objective."
    ),
    "summary.your_area": "your area",
    "summary.fact_rain": "~{rain} mm rainfall",
    "summary.fact_slope": "slope ~{slope}%",
    "summary.fact_clay": "clay ~{clay}%",
    "summary.fact_join": ", ",
    "summary.crop": " for your {crop}",
    "summary.lead": (
        "For your **{zone}** area{facts}{crop}, the evidence ranks "
        "**{practice}** to {direction} {indicator}."
    ),
    "summary.others": " Other strong options: {others}.",
    "summary.others_join": ", ",
    "summary.low_confidence": (
        " Evidence for this setting is limited, so treat this as a starting point."
    ),
    "summary.default_direction": "improve",
    "summary.default_indicator": "your goal",
    # ------------------------------------------------------------ explain
    "explain.no_chunks": (
        "No evidence passages were retrieved for this recommendation, "
        "so no grounded explanation can be generated. The model's "
        "ranked practices and effect estimates above still stand."
    ),
    "explain.default_indicator": "the selected objective",
    "explain.default_practice": "This practice",
    "explain.untitled_study": "Untitled study",
    "explain.fallback.sentence": "{practice}: the model estimates {effect}",
    "explain.fallback.supported_by": ", supported by evidence from {cites}",
    "explain.fallback.cite": "“{title}” ({era_code})",
    "explain.fallback.cite_join": ", ",
    "explain.fallback.none": "No practices were recommended for {indicator} in this context.",
    # ------------------------------------------------------------ explain: evidence base
    "eb.sentence": (
        "{practice}: backed by {n_studies} {studies_word} / {n_obs} field {obs_word}"
        "{belts}; {in_corpus} of the studies {is_are} in the retrievable corpus."
    ),
    "eb.study": "study",
    "eb.studies": "studies",
    "eb.observation": "observation",
    "eb.observations": "observations",
    "eb.in_belts": " in {belts}",
    "eb.belts_join": ", ",
    "eb.is": "is",
    "eb.are": "are",
    # ------------------------------------------------------------ glossary (identity in English)
    "direction.increase": "increase",
    "direction.reduce": "reduce",
    "direction.improve": "improve",
    # ------------------------------------------------------------ chat: quick-reply protocol (U2)
    # Mirrors the UI's chat.protocol.* strings (asserted in tests/test_i18n_sync.py).
    "protocol.farm_at": "My farm is at {lat}, {lon}.",
    "protocol.challenge": "My challenge is {family}.",
    "protocol.objective": "My objective is to {objective}.",
    "protocol.challenge_note": "Challenge: {family}.",
    "protocol.objective_note": "Objective: {objective}.",
    # Shown for am/om free text when no LLM is configured (U2).
    "clarify.use_advisor": (
        "I can only read free text in English on this server (the AI text service "
        "is not configured). Please write in English, or open the "
        "Advisor, where every step is in your language."
    ),
    # ------------------------------------------------------------ advisory modes (P9)
    "mode.model_led": "Field-trial model",
    "mode.hybrid": "Hybrid",
    "mode.knowledge_led": "Documented practice",
    "mode.reason.strong_evidence": (
        "{practice} has {n_studies} studies and {n_obs} field observations for this objective."
    ),
    "mode.reason.thin_evidence": (
        "The best-evidenced practice, {practice}, has only {n_studies} studies and {n_obs} field "
        "observations for this objective (the model-led threshold is {min_studies} studies and "
        "{min_obs} observations)."
    ),
    "mode.reason.in_zone": "{practice} has {n_obs_in_zone} observations measured in your moisture zone ({zone}).",
    "mode.reason.other_zones_only": "None of the top-ranked practices was measured in your moisture zone ({zone}).",
    "mode.reason.zone_unknown": "Your agro-ecological belt could not be resolved, so zone coverage is unknown.",
    "mode.reason.engine_no_evidence": "The field-trial dataset has no observations for this challenge and objective.",
    "mode.reason.engine_unsupported": "This challenge and objective pair is not scored by the field-trial model.",
    "mode.reason.no_studies": "None of the ranked practices has a study for this objective.",
    "mode.reason.graph_unavailable": "The knowledge graph is not built, so evidence depth could not be assessed.",
    "mode.reason.no_candidates": "No documented practice with a citation was found for this request.",
    "mode.hybrid_note": (
        " Field-trial evidence for this request is thin, so {n} documented {practices_word} from "
        "guidance documents and practice records {is_are} listed alongside with their "
        "sources; they carry no effect numbers."
    ),
    "mode.knowledge_led.lead": (
        "There is no field-trial evidence for **{challenge}** with the objective **{objective}** "
        "in your area, so I cannot rank practices or estimate effects. These documented practices "
        "come from guidance documents and practice records for comparable settings, with their "
        "sources and no effect numbers:"
    ),
    "mode.knowledge_led.item": "- **{label}**: {rationale}",
    "mode.knowledge_led.none": (
        "There is no field-trial evidence for **{challenge}** with the objective **{objective}** "
        "in your area, and no documented practice with a citation was found either. Try another "
        "objective for this challenge, or a nearby location."
    ),
    "mode.practice": "practice",
    "mode.practices": "practices",
    # ------------------------------------------------------------ knowledge candidates (P9)
    "kc.rationale.guidance": (
        "{label} is described in {n_docs} guidance {docs_word} retrieved for {family} and "
        "{objective} in this context."
    ),
    "kc.rationale.other_objectives": "{label} has field-trial evidence for other objectives: {objectives}.",
    "kc.rationale.record": "{label} is a documented practice record from a comparable context ({country}).",
    "kc.objective_item": "{objective} ({n} {studies_word})",
    "kc.join": ", ",
    "kc.document": "document",
    "kc.documents": "documents",
    "kc.study": "study",
    "kc.studies": "studies",
}
