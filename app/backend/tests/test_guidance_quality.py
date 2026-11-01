"""Guidance passages fit to show and synthesised how-to steps (U9, C1)."""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.config import Settings
from app.services import explain_service as es

GOOD = (
    "In the Ethiopian highlands, farmers apply crop residue mulch at the start of the rainy season. "
    "Spread the mulch evenly between the rows so that the soil surface is covered, and keep it in place "
    "until harvest. Mulch reduces runoff and protects the soil from the impact of heavy rain, which is "
    "why extension agents in Amhara recommend it on sloping plots where erosion is a problem."
)
BIBLIOGRAPHY = (
    "Abera, W., Tamene, L. (2019). Soil loss in Ethiopia. Catena 12, 1-9. Van Wesemael, B., Poesen, J. "
    "(2003). Rainfall. Geoderma 19, 3-14. Smith, J. et al. (2010). Mulch. Soil Use 4, 11-19. Jones, K. et "
    "al. (2012). Runoff. Hydrol. 7, 2-8. Lal, R. (1998). Mulching. J. Soil 3, 1-3. La"
)
SPANISH = (
    "Las zanjas de infiltración se construyen en curvas de nivel para retener el agua de lluvia y "
    "reducir la escorrentía en las laderas de los Andes. El mulch se coloca sobre el suelo para proteger "
    "la superficie de la erosión y mejorar la infiltración del agua en las parcelas de los agricultores."
)
ANDEAN = (
    "In the Andean highlands of Peru, farmers spread mulch between potato rows to protect the soil. "
    "Mulch keeps the soil moist through the dry season and reduces runoff on the steep terraces, and "
    "the practice has spread through farmer field schools in Bolivia and Ecuador over the last decade."
)
OFF_TOPIC = (
    "Dairy cooperatives in the Ethiopian highlands collect milk twice a day and pay farmers every two "
    "weeks. The cooperative keeps records of the volume delivered and the fat content of the milk, and "
    "members elect a committee that manages the cooling centre and the transport to the processor."
)


def chunk(text: str, practice: str = "Mulch") -> dict[str, Any]:
    return {"text": text, "for_practice": practice, "tier": "guidance", "title": "Guide", "url": f"u:{hash(text)}"}


def test_only_clean_english_on_region_relevant_passages_survive() -> None:
    kept = es.usable_guidance([chunk(GOOD), chunk(BIBLIOGRAPHY), chunk(SPANISH), chunk(ANDEAN), chunk(OFF_TOPIC)])
    assert [c["text"] for c in kept] == [GOOD]


def test_an_andean_passage_that_also_speaks_to_africa_is_kept() -> None:
    both = ANDEAN + " The same mulching approach is used in Ethiopia and across East Africa."
    assert es.usable_guidance([chunk(both)])


def test_howto_steps_keep_only_cited_and_guarded_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(es, "get_settings", lambda: Settings(_env_file=None, openai_api_key="sk-test"))
    reply = {"steps": {"Mulch": [
        "1. Spread residue mulch between rows at the start of the rains [G1].",
        "Keep the mulch in place until harvest [G1].",
        "Apply 7 tonnes of mulch per hectare [G1].",   # number not in the passage -> dropped
        "Water the field every day.",                   # no citation -> dropped
    ]}}
    monkeypatch.setattr(es, "_call_llm", lambda messages, json_mode=False: json.dumps(reply))
    steps = es.howto_steps(["Mulch"], [chunk(GOOD)], {"model": set(), "study": set(), "context": set(), "count": set()}, "en")
    assert steps == {"Mulch": ["Spread residue mulch between rows at the start of the rains [G1].",
                               "Keep the mulch in place until harvest [G1]."]}


def test_howto_steps_are_empty_without_a_key_or_passages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(es, "get_settings", lambda: Settings(_env_file=None, openai_api_key=""))
    assert es.howto_steps(["Mulch"], [chunk(GOOD)], {}, "en") == {}
