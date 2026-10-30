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
    "indicator.SOM content": "የአፈር ኦርጋኒክ ቁስ",
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
    # ------------------------------------------------------------ chat: quick-reply protocol (U2)
    "protocol.farm_at": "እርሻዬ በ{lat}፣ {lon} ላይ ነው።",
    "protocol.challenge": "ፈተናዬ {family} ነው።",
    "protocol.objective": "ዓላማዬ {objective} ነው።",
    "protocol.challenge_note": "ፈተና፦ {family}።",
    "protocol.objective_note": "ዓላማ፦ {objective}።",
    "clarify.use_advisor": (
        "በዚህ አገልጋይ ላይ ነፃ ጽሑፍን በእንግሊዝኛ ብቻ ማንበብ እችላለሁ (የኤአይ የጽሑፍ አገልግሎት አልተዋቀረም)። "
        "ከታች ያሉትን ምርጫዎች ይጠቀሙ፣ ወይም አማካሪውን ይክፈቱ — እዚያ እያንዳንዱ ደረጃ በቋንቋዎ ነው።"
    ),
    "indicator.yield": "ምርት",
    # UI objective labels (mirror src/i18n/glossary.ts INDICATORS; read back from typed chips)
    "indicator_label.yield": "የሰብል ምርትን መጨመር",
    "indicator_label.biomass yield": "ባዮማስ / መኖን መጨመር",
    "indicator_label.income": "ገቢን መጨመር",
    "indicator_label.water use efficiency": "የውሃ አጠቃቀም ቅልጥፍናን ማሻሻል",
    "indicator_label.SOM content": "የአፈር ኦርጋኒክ ቁስን ማሻሻል",
    "indicator_label.soil loss": "የአፈር መሸርሸርን መቀነስ",
    "indicator_label.runoff": "የውሃ ፍሳሽን መቀነስ",
    # ------------------------------------------------------------ advisory modes (P9)
    "mode.model_led": "የመስክ ሙከራ ሞዴል",
    "mode.hybrid": "ድብልቅ",
    "mode.knowledge_led": "የተመዘገበ ልማድ",
    "mode.reason.strong_evidence": "{practice} ለዚህ ዓላማ {n_studies} ጥናቶችና {n_obs} የመስክ ምልከታዎች አሉት።",
    "mode.reason.thin_evidence": (
        "በጣም የተደገፈው ልማድ {practice} ለዚህ ዓላማ {n_studies} ጥናቶችና {n_obs} የመስክ ምልከታዎች ብቻ አሉት "
        "(የሞዴል መሪ ወሰን {min_studies} ጥናቶችና {min_obs} ምልከታዎች ነው)።"
    ),
    "mode.reason.in_zone": "{practice} በእርስዎ የእርጥበት ዞን ({zone}) የተለኩ {n_obs_in_zone} ምልከታዎች አሉት።",
    "mode.reason.other_zones_only": "ከከፍተኛ ደረጃ ልማዶች አንዱም በእርስዎ የእርጥበት ዞን ({zone}) አልተለካም።",
    "mode.reason.zone_unknown": "የአግሮ-ኢኮሎጂ ቀጠናዎ ሊፈታ አልቻለም፤ ስለዚህ የዞን ሽፋን አይታወቅም።",
    "mode.reason.engine_no_evidence": "ለዚህ ፈተናና ዓላማ የመስክ ሙከራ መረጃ ስብስቡ ምልከታዎች የሉትም።",
    "mode.reason.engine_unsupported": "ይህ የፈተናና ዓላማ ጥምረት በመስክ ሙከራ ሞዴል አይመዘንም።",
    "mode.reason.no_studies": "ከደረጃ ከተሰጣቸው ልማዶች አንዱም ለዚህ ዓላማ ጥናት የለውም።",
    "mode.reason.graph_unavailable": "የእውቀት ግራፉ አልተገነባም፤ ስለዚህ የማስረጃ ጥልቀት ሊገመገም አልቻለም።",
    "mode.reason.no_candidates": "ለዚህ ጥያቄ ጥቅስ ያለው የተመዘገበ ልማድ አልተገኘም።",
    "mode.hybrid_note": (
        " ለዚህ ጥያቄ የመስክ ሙከራ ማስረጃ ቀጭን ነው፤ ስለዚህ ከመመሪያ ሰነዶችና ከልማድ መዝገቦች {n} የተመዘገቡ {practices_word} "
        "ከምንጮች ጋር ጎን ለጎን {is_are} — የውጤት ቁጥሮች የላቸውም።"
    ),
    "mode.knowledge_led.lead": (
        "በአካባቢዎ ለ**{challenge}** በ**{objective}** ዓላማ የመስክ ሙከራ ማስረጃ የለም፤ ስለዚህ ልማዶችን ደረጃ መስጠት ወይም "
        "ውጤቶችን መገመት አልችልም። እነዚህ የተመዘገቡ ልማዶች ከተመሳሳይ ሁኔታዎች መመሪያ ሰነዶችና የልማድ መዝገቦች ናቸው፣ "
        "ከምንጮቻቸው ጋር እና ያለ የውጤት ቁጥር፦"
    ),
    "mode.knowledge_led.item": "- **{label}** — {rationale}",
    "mode.knowledge_led.none": (
        "በአካባቢዎ ለ**{challenge}** በ**{objective}** ዓላማ የመስክ ሙከራ ማስረጃ የለም፣ እንዲሁም ጥቅስ ያለው የተመዘገበ "
        "ልማድ አልተገኘም። ለዚህ ፈተና ሌላ ዓላማ ወይም የቅርብ ቦታ ይሞክሩ።"
    ),
    "mode.practice": "ልማድ",
    "mode.practices": "ልማዶች",
    "kc.rationale.guidance": "{label} ለ{family} እና {objective} በዚህ አውድ በተገኙ {n_docs} የመመሪያ {docs_word} ውስጥ ተገልጿል።",
    "kc.rationale.other_objectives": "{label} ለሌሎች ዓላማዎች የመስክ ሙከራ ማስረጃ አለው፦ {objectives}።",
    "kc.rationale.record": "{label} ከተመሳሳይ አውድ ({country}) የተመዘገበ የልማድ መዝገብ ነው።",
    "kc.objective_item": "{objective} ({n} {studies_word})",
    "kc.join": "፣ ",
    "kc.document": "ሰነድ",
    "kc.documents": "ሰነዶች",
    "kc.study": "ጥናት",
    "kc.studies": "ጥናቶች",
}
