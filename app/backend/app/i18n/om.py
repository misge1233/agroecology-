"""Afaan Oromoo (Qubee) catalog — MACHINE DRAFT, awaiting native review.

Drafted by the implementation agent (U1, 26 Oct 2026); every key is listed
with status ``machine-draft`` in ``docs/i18n/TRANSLATION_STATUS.md``.
"""
from __future__ import annotations

STRINGS: dict[str, str] = {
    "prompt.reply_in": "Reply in Afaan Oromoo.",
    "social.with_prior": (
        "Homaa miti; gargaaruu isaatti gammadeera. Maaliif akka ta'e ykn akkamitti akka "
        "hojiirra oolchitan beekuuf, ykn bakka, midhaan ykn kaayyoo biraa yaaluuf yeroo "
        "kamiyyuu gaafadhaa."
    ),
    "social.no_prior": (
        "Homaa miti. Yeroo qophooftan qonni keessan eessa akka jiru, rakkoo fi kaayyoo keessan "
        "natti himaa; gochaalee mijatoo nan gorsa."
    ),
    "error.rate_limit": (
        "Tajaajilli barreeffama AI yeroo ammaa daangaa itti fayyadamaa gaheera. Maaloo "
        "daqiiqaa muraasa eegaatii irra deebi'aa yaalaa, ykn gorsa hatattamaatiif fuula Gorsaa "
        "fayyadamaa."
    ),
    "error.generic": (
        "Gaaffii saniif gochaalee madaaluu hin dandeenye. Bakki Itoophiyaa keessa ta'uu "
        "isaa fi cimdiin rakkoo/kaayyoo deeggaramuu isaa mirkaneessaa, achiis irra "
        "deebi'aa yaalaa."
    ),
    "clarify.all_missing": (
        "Gochaalee agro-ekoloojii ragaa irratti hundaa'an gorsuuf wantoota sadii beekuun "
        "na barbaachisa: **rakkoo** keessan (fkn to'annoo dhiqama biyyee), **kaayyoo** "
        "keessan (fkn dhiqama biyyee hir'isuu), fi **bakka** keessan (maqaa magaalaa ykn "
        "gandaa Itoophiyaa keessaa dhihoo jiru, ykn koordineetii)."
    ),
    "clarify.understood_prefix": "Hubadheera: ",
    "clarify.understood_join": ", ",
    "clarify.understood_suffix": ". ",
    "clarify.place": "qonna keessan naannoo **{place}** kaa'eera",
    "clarify.challenge": "rakkoo **{challenge}**",
    "clarify.objective": "kaayyoo **{objective}**",
    "clarify.ask_challenge": (
        "**rakkoo** kamtu caalaa walsima: oomisha midhaanii, horii, gabbina biyyee, "
        "dhiqama fi bishaan, ykn agroo-forestrii"
    ),
    "clarify.ask_objective_erosion": (
        "**kaayyoo** keessan: dhiqama biyyee hir'isuu, yaa'insa bishaanii hir'isuu, ykn "
        "bu'a qabeessummaa itti fayyadama bishaanii fooyyessuu"
    ),
    "clarify.ask_objective": (
        "**kaayyoo** keessan (fkn oomisha dabaluu, dhiqama biyyee hir'isuu, qabiyyee "
        "orgaanikii biyyee fooyyessuu)"
    ),
    "clarify.ask_location": (
        "**bakka** keessan: maqaa magaalaa ykn gandaa Itoophiyaa keessaa dhihoo jiru, "
        "ykn koordineetii (laatitiyuudii, longitiyuudii)"
    ),
    "clarify.one": "Gochaalee ragaa dirree irraa sadarkeessuuf, maaloo {ask} qoodaa.",
    "clarify.two": "Maaloo {a}, fi {b} qoodaa.",
    "clarify.many": "Maaloo {asks} qoodaa.",
    "clarify.many_join": "; ",
    "summary.no_evidence": (
        "Walitti dhufeenya kanaaf ragaa dirree gahaa hin arganne. Bakka dhihoo ykn "
        "kaayyoo biraa yaalaa."
    ),
    "summary.your_area": "naannoo keessan",
    "summary.fact_rain": "rooba ~{rain} mm",
    "summary.fact_slope": "gadee lafaa ~{slope}%",
    "summary.fact_clay": "dhoqqee ~{clay}%",
    "summary.fact_join": ", ",
    "summary.crop": " {crop} keessaniif",
    "summary.lead": (
        "Naannoo **{zone}** keessanitti{facts}{crop}, ragaan {indicator} {direction} "
        "**{practice}** sadarkaa duraa kaa'a."
    ),
    "summary.others": " Filannoowwan biroo cimoo: {others}.",
    "summary.others_join": ", ",
    "summary.low_confidence": (
        " Ragaan haala kanaaf jiru murtaa'aa dha; kana akka qabxii jalqabaatti fudhadhaa."
    ),
    "summary.default_direction": "fooyyessuuf",
    "summary.default_indicator": "kaayyoo keessan",
    "explain.no_chunks": (
        "Gorsa kanaaf kutaaleen ragaa hin argamne, kanaaf ibsi ragaa irratti hundaa'e "
        "uumamuu hin danda'u. Gochaaleen sadarkeeffaman fi tilmaamni bu'aa moodeelichaa "
        "kan olii ammas ni jiru."
    ),
    "explain.default_indicator": "kaayyoo filatame",
    "explain.default_practice": "Gochaan kun",
    "explain.untitled_study": "Qorannoo mata-duree hin qabne",
    "explain.fallback.sentence": "{practice}: moodeelichi {effect} tilmaama",
    "explain.fallback.supported_by": ", ragaa {cites} irraa argameen deeggarame",
    "explain.fallback.cite": "“{title}” ({era_code})",
    "explain.fallback.cite_join": ", ",
    "explain.fallback.none": "Haala kana keessatti {indicator}f gochaan hin gorfamne.",
    "eb.sentence": (
        "{practice}: {n_studies} {studies_word} / {n_obs} {obs_word}{belts}n deeggarame; "
        "qorannoowwan keessaa {in_corpus} kuusaa argamuu danda'u keessa {is_are}."
    ),
    "eb.study": "qorannoo",
    "eb.studies": "qorannoowwan",
    "eb.observation": "daawwannaa dirree",
    "eb.observations": "daawwannaawwan dirree",
    "eb.in_belts": " {belts} keessatti",
    "eb.belts_join": ", ",
    "eb.is": "jira",
    "eb.are": "jiru",
    "direction.increase": "dabaluuf",
    "direction.reduce": "hir'isuuf",
    "direction.improve": "fooyyessuuf",
    "indicator.yield": "oomisha",
    "indicator.biomass yield": "oomisha baayoomaasii",
    "indicator.income": "galii",
    "indicator.water use efficiency": "bu'a qabeessummaa itti fayyadama bishaanii",
    "indicator.SOM content": "qabiyyee orgaanikii biyyee",
    "indicator.soil loss": "dhiqama biyyee",
    "indicator.runoff": "yaa'insa bishaanii",
    "family.Crop production and management": "Oomisha fi bulchiinsa midhaanii",
    "family.Livestock production and management": "Oomisha fi bulchiinsa horii",
    "family.Integrated soil fertility management": "Bulchiinsa gabbina biyyee walitti hidhame",
    "family.Erosion control and water management": "To'annoo dhiqama biyyee fi bulchiinsa bishaanii",
    "family.Agro-forestry and forest management": "Agroo-forestrii fi bulchiinsa bosonaa",
    "aez.Dry Dega": "Baddaa gogaa",
    "aez.Dry Kolla": "Gammoojjii gogaa",
    "aez.Dry Weyna Dega": "Badda-daree gogaa",
    "aez.Moist Berha": "Gammoojjii ho'aa jiidhaa",
    "aez.Moist Dega": "Baddaa jiidhaa",
    "aez.Moist High Dega": "Baddaa ol'aanaa jiidhaa",
    "aez.Moist Kolla": "Gammoojjii jiidhaa",
    "aez.Moist Weyna Dega": "Badda-daree jiidhaa",
    "aez.Wet Dega": "Baddaa roobaa",
    "aez.Wet Kolla": "Gammoojjii roobaa",
    "aez.Wet Weyna Dega": "Badda-daree roobaa",
    "aez.Wet Wurch": "Baddaa qorraa roobaa",
    # ------------------------------------------------------------ chat: quick-reply protocol (U2)
    "protocol.farm_at": "Qonni koo {lat}, {lon} irra jira.",
    "protocol.challenge": "Rakkoon koo {family} dha.",
    "protocol.objective": "Kaayyoon koo {objective} dha.",
    "protocol.challenge_note": "Rakkoo: {family}.",
    "protocol.objective_note": "Kaayyoo: {objective}.",
    "clarify.use_advisor": (
        "Sarvarii kana irratti barreeffama bilisaa Afaan Ingilizii qofaan dubbisuu nan danda'a "
        "(tajaajilli barreeffama AI hin qindoofne). Maaloo Afaan Ingiliziin barreessaa, yookiin "
        "Gorsaa banaa; achitti tarkaanfiin hundi afaan keessaniin."
    ),
    "indicator.yield": "oomisha",
    # UI objective labels (mirror src/i18n/glossary.ts INDICATORS; read back from typed chips)
    "indicator_label.yield": "Oomisha midhaanii dabaluu",
    "indicator_label.biomass yield": "Baayoomaasii / marga dabaluu",
    "indicator_label.income": "Galii dabaluu",
    "indicator_label.water use efficiency": "Bu'a qabeessummaa itti fayyadama bishaanii fooyyessuu",
    "indicator_label.SOM content": "Qabiyyee orgaanikii biyyee fooyyessuu",
    "indicator_label.soil loss": "Dhiqama biyyee hir'isuu",
    "indicator_label.runoff": "Yaa'insa bishaanii hir'isuu",
    # ------------------------------------------------------------ advisory modes (P9)
    "mode.model_led": "Moodeela yaalii dirree",
    "mode.hybrid": "Makaa",
    "mode.knowledge_led": "Gocha galmaa'e",
    "mode.reason.strong_evidence": "{practice} kaayyoo kanaaf qorannoo {n_studies} fi daawwannaa dirree {n_obs} qaba.",
    "mode.reason.thin_evidence": (
        "Gochi ragaa guddaa qabu, {practice}, kaayyoo kanaaf qorannoo {n_studies} fi daawwannaa dirree {n_obs} qofa "
        "qaba (daangaan moodeelaan hogganamuu qorannoo {min_studies} fi daawwannaa {min_obs} dha)."
    ),
    "mode.reason.in_zone": "{practice} daawwannaa {n_obs_in_zone} godina jiidhina keessan ({zone}) keessatti safarame qaba.",
    "mode.reason.other_zones_only": "Gochaalee sadarkaa olaanaa keessaa tokkollee godina jiidhina keessan ({zone}) keessatti hin safaramne.",
    "mode.reason.zone_unknown": "Godinni agro-ekoloojii keessan hiikamuu hin dandeenye; kanaaf uwwisni godinaa hin beekamu.",
    "mode.reason.engine_no_evidence": "Kuusaan daataa yaalii dirree rakkoo fi kaayyoo kanaaf daawwannaa hin qabu.",
    "mode.reason.engine_unsupported": "Cimdiin rakkoo fi kaayyoo kun moodeela yaalii dirreetiin hin madaalamu.",
    "mode.reason.no_studies": "Gochaalee sadarkeeffaman keessaa tokkollee kaayyoo kanaaf qorannoo hin qabu.",
    "mode.reason.graph_unavailable": "Giraafiin beekumsaa hin ijaaramne; kanaaf gadi fageenyi ragaa madaalamuu hin dandeenye.",
    "mode.reason.no_candidates": "Gaaffii kanaaf gochi galmaa'e wabii qabu hin argamne.",
    "mode.hybrid_note": (
        " Ragaan yaalii dirree gaaffii kanaaf qal'aa dha; kanaaf {practices_word} galmaa'an {n} sanadoota qajeelfamaa "
        "fi galmeewwan gochaa irraa maddoota waliin cinaatti {is_are}; lakkoofsa bu'aa hin qaban."
    ),
    "mode.knowledge_led.lead": (
        "Naannoo keessanitti **{challenge}** kaayyoo **{objective}** waliin ragaan yaalii dirree hin jiru; kanaaf "
        "gochaalee sadarkeessuu yookiin bu'aa tilmaamuu hin danda'u. Gochaaleen galmaa'an kunneen sanadoota qajeelfamaa "
        "fi galmeewwan gochaa haalawwan walfakkaataniif qophaa'an irraa dhufan, maddoota isaanii waliin, lakkoofsa bu'aa malee:"
    ),
    "mode.knowledge_led.item": "- **{label}**: {rationale}",
    "mode.knowledge_led.none": (
        "Naannoo keessanitti **{challenge}** kaayyoo **{objective}** waliin ragaan yaalii dirree hin jiru, akkasumas "
        "gochi galmaa'e wabii qabu hin argamne. Rakkoo kanaaf kaayyoo biraa yookiin bakka dhihoo yaalaa."
    ),
    "mode.practice": "gocha",
    "mode.practices": "gochaalee",
    "kc.rationale.guidance": "{label} {family} fi {objective}f haala kana keessatti sanadoota qajeelfamaa {n_docs} ({docs_word}) argaman keessatti ibsameera.",
    "kc.rationale.other_objectives": "{label} kaayyoowwan biroof ragaa yaalii dirree qaba: {objectives}.",
    "kc.rationale.record": "{label} galmee gochaa haala walfakkaataa ({country}) irraa galmaa'e dha.",
    "kc.objective_item": "{objective} ({studies_word} {n})",
    "kc.join": ", ",
    "kc.document": "sanada",
    "kc.documents": "sanadoota",
    "kc.study": "qorannoo",
    "kc.studies": "qorannoowwan",
}
