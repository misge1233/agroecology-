"""Amharic (አማርኛ) catalog — MACHINE DRAFT, awaiting native review.

Every string here was drafted by the implementation agent (U1, 26 Oct 2026)
and is listed with status ``machine-draft`` in ``docs/i18n/TRANSLATION_STATUS.md``.
Ethiopic punctuation: ፣ (comma) ፤ (semicolon) ። (full stop) ፦ (colon).
Western digits are used throughout (the numeric guardrail is script-independent).
"""
from __future__ import annotations

STRINGS: dict[str, str] = {
    "prompt.reply_in": "Reply in Amharic (አማርኛ).",
    "social.with_prior": (
        "ምንም አይደለም — ስለረዳዎት ደስ ብሎኛል። ለምን እንደሆነ ወይም እንዴት እንደሚተገብሩት ለማወቅ፣ "
        "ወይም የተለየ ቦታ፣ ሰብል ወይም ግብ ለመሞከር በማንኛውም ጊዜ ይጠይቁ።"
    ),
    "social.no_prior": (
        "ምንም አይደለም። ዝግጁ ሲሆኑ የካርታ ቦታ፣ የፈተና መስክ እና ዓላማ ያጋሩ፤ "
        "ተስማሚ ልማዶችን እመክራለሁ።"
    ),
    "error.rate_limit": (
        "የኤአይ የጽሑፍ አገልግሎት ለአሁኑ የአጠቃቀም ገደቡን ደርሷል። እባክዎ ጥቂት ደቂቃዎች ይጠብቁና "
        "እንደገና ይሞክሩ፣ ወይም ለፈጣን ምክሮች ቅጹን ይጠቀሙ።"
    ),
    "error.generic": (
        "ለዚያ ጥያቄ ልማዶችን መመዘን አልቻልኩም። ቦታው በኢትዮጵያ ውስጥ መሆኑንና የፈተና/ዓላማ "
        "ጥምረቱ የሚደገፍ መሆኑን ያረጋግጡ፣ ከዚያ እንደገና ይሞክሩ።"
    ),
    "clarify.all_missing": (
        "በማስረጃ ላይ የተመሠረቱ የአግሮኢኮሎጂ ልማዶችን ለመምከር ሦስት ነገሮችን ማወቅ አለብኝ፦ "
        "**ፈተናዎን** (ለምሳሌ የአፈር መሸርሸር መከላከል)፣ **ዓላማዎን** (ለምሳሌ የአፈር መሸርሸርን መቀነስ)፣ "
        "እና **ቦታዎን** (የካርታ ምልክት፣ መጋጠሚያዎች ወይም በኢትዮጵያ ውስጥ ያለ የቦታ ስም)።"
    ),
    "clarify.understood_prefix": "ተረድቻለሁ፦ ",
    "clarify.understood_join": "፣ ",
    "clarify.understood_suffix": "። ",
    "clarify.place": "እርሻዎን በ**{place}** አቅራቢያ አስቀምጫለሁ",
    "clarify.challenge": "ፈተና **{challenge}**",
    "clarify.objective": "ዓላማ **{objective}**",
    "clarify.ask_challenge": (
        "የትኛው **ፈተና** ይበልጥ ይስማማል — የሰብል ምርት፣ እንስሳት፣ የአፈር ለምነት፣ "
        "መሸርሸርና ውሃ፣ ወይም አግሮ-ፎረስትሪ"
    ),
    "clarify.ask_objective_erosion": (
        "**ዓላማዎን** — የአፈር መሸርሸርን መቀነስ፣ የውሃ ፍሳሽን መቀነስ፣ ወይም የውሃ አጠቃቀም ቅልጥፍናን ማሻሻል"
    ),
    "clarify.ask_objective": (
        "**ዓላማዎን** (ለምሳሌ ምርት መጨመር፣ የአፈር መሸርሸር መቀነስ፣ የአፈር ኦርጋኒክ ቁስ ማሻሻል)"
    ),
    "clarify.ask_location": (
        "**ቦታዎን** — በካርታ ላይ ምልክት ያድርጉ፣ ኬክሮስ/ኬንትሮስ ያጋሩ፣ ወይም በኢትዮጵያ ውስጥ ያለ ቦታ ይጥቀሱ"
    ),
    "clarify.one": "ልማዶችን ከመስክ ማስረጃ ለመደርደር እባክዎ {ask} ያጋሩ።",
    "clarify.two": "እባክዎ {a}፣ እና {b} ያጋሩ።",
    "clarify.many": "እባክዎ {asks} ያጋሩ።",
    "clarify.many_join": "፤ ",
    "summary.no_evidence": (
        "ለዚያ ጥምረት በቂ የመስክ ማስረጃ አላገኘሁም። በአቅራቢያ ያለ ቦታ ወይም የተለየ ዓላማ ይሞክሩ።"
    ),
    "summary.your_area": "አካባቢዎ",
    "summary.fact_rain": "~{rain} ሚሜ ዝናብ",
    "summary.fact_slope": "ተዳፋት ~{slope}%",
    "summary.fact_clay": "ሸክላ ~{clay}%",
    "summary.fact_join": "፣ ",
    "summary.crop": " ለ{crop}ዎ",
    "summary.lead": (
        "ለእርስዎ **{zone}** አካባቢ{facts}{crop}፣ {indicator}ን {direction} ማስረጃው "
        "**{practice}**ን ቀዳሚ አድርጎ ያስቀምጣል።"
    ),
    "summary.others": " ሌሎች ጠንካራ አማራጮች፦ {others}።",
    "summary.others_join": "፣ ",
    "summary.low_confidence": " ለዚህ ሁኔታ ያለው ማስረጃ ውስን ነው — ይህንን እንደ መነሻ ነጥብ ይውሰዱት።",
    "summary.default_direction": "ለማሻሻል",
    "summary.default_indicator": "ግብዎ",
    "explain.no_chunks": (
        "ለዚህ ምክር የማስረጃ ክፍሎች አልተገኙም፣ ስለዚህ መሠረት ያለው ማብራሪያ መፍጠር አይቻልም። "
        "ከላይ ያሉት የሞዴሉ ደረጃ የተሰጣቸው ልማዶችና የውጤት ግምቶች አሁንም ይቆማሉ።"
    ),
    "explain.default_indicator": "የተመረጠው ዓላማ",
    "explain.default_practice": "ይህ ልማድ",
    "explain.untitled_study": "ርዕስ የሌለው ጥናት",
    "explain.fallback.sentence": "{practice}፦ ሞዴሉ {effect} ይገምታል",
    "explain.fallback.supported_by": "፣ ከ{cites} በተገኘ ማስረጃ የተደገፈ",
    "explain.fallback.cite": "“{title}” ({era_code})",
    "explain.fallback.cite_join": "፣ ",
    "explain.fallback.none": "ለ{indicator} በዚህ አውድ ምንም ልማድ አልተመከረም።",
    "eb.sentence": (
        "{practice}፦ በ{n_studies} {studies_word} / {n_obs} {obs_word}{belts} የተደገፈ፤ "
        "ከጥናቶቹ {in_corpus} ሊገኝ በሚችለው ስብስብ ውስጥ {is_are}።"
    ),
    "eb.study": "ጥናት",
    "eb.studies": "ጥናቶች",
    "eb.observation": "የመስክ ምልከታ",
    "eb.observations": "የመስክ ምልከታዎች",
    "eb.in_belts": " በ{belts} ውስጥ",
    "eb.belts_join": "፣ ",
    "eb.is": "ነው",
    "eb.are": "ናቸው",
    # glossary: data-contract terms shown inside backend sentences
    "direction.increase": "ለመጨመር",
    "direction.reduce": "ለመቀነስ",
    "direction.improve": "ለማሻሻል",
    "indicator.yield": "ምርት",
    "indicator.biomass yield": "የባዮማስ ምርት",
    "indicator.income": "ገቢ",
    "indicator.water use efficiency": "የውሃ አጠቃቀም ቅልጥፍና",
    "indicator.SOM content": "የአፈር ኦርጋኒክ ቁስ ይዘት",
    "indicator.soil loss": "የአፈር መሸርሸር",
    "indicator.runoff": "የውሃ ፍሳሽ",
    "family.Crop production and management": "የሰብል ምርትና አያያዝ",
    "family.Livestock production and management": "የእንስሳት እርባታና አያያዝ",
    "family.Integrated soil fertility management": "የተቀናጀ የአፈር ለምነት አያያዝ",
    "family.Erosion control and water management": "የአፈር መሸርሸር መከላከልና የውሃ አያያዝ",
    "family.Agro-forestry and forest management": "አግሮ-ፎረስትሪና የደን አያያዝ",
    "aez.Dry Dega": "ደረቅ ደጋ",
    "aez.Dry Kolla": "ደረቅ ቆላ",
    "aez.Dry Weyna Dega": "ደረቅ ወይና ደጋ",
    "aez.Moist Berha": "እርጥብ በረሃ",
    "aez.Moist Dega": "እርጥብ ደጋ",
    "aez.Moist High Dega": "እርጥብ ከፍተኛ ደጋ",
    "aez.Moist Kolla": "እርጥብ ቆላ",
    "aez.Moist Weyna Dega": "እርጥብ ወይና ደጋ",
    "aez.Wet Dega": "ዝናባማ ደጋ",
    "aez.Wet Kolla": "ዝናባማ ቆላ",
    "aez.Wet Weyna Dega": "ዝናባማ ወይና ደጋ",
    "aez.Wet Wurch": "ዝናባማ ውርጭ",
}
