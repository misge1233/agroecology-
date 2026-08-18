"""Tests for NL slot filling + place-name geocoding (evidence-gated chat)."""
from app.services.geocode import geocode_text, lookup_gazetteer
from app.services.slot_extraction import clarification_message, extract_slots


def test_debre_birhan_soil_loss_extracts_all_slots():
    text = "I want to reduce soil loss on my sloping field near Debre Birhan"
    slots = extract_slots(text)
    assert slots.indicator == "soil loss"
    assert slots.practice_family == "Erosion control and water management"
    assert slots.lat is not None and slots.lon is not None
    assert abs(slots.lat - 9.6795) < 0.02
    assert abs(slots.lon - 39.5326) < 0.02
    assert slots.is_complete
    assert slots.missing == []


def test_geocode_debre_berhan_alias():
    hit = lookup_gazetteer("Debre Berhan")
    assert hit is not None
    assert abs(hit.lat - 9.6795) < 0.02


def test_geocode_text_finds_addis():
    hit = geocode_text("wheat farm near Addis Ababa")
    assert hit is not None
    assert abs(hit.lat - 9.03) < 0.05


def test_incomplete_asks_only_for_location():
    text = "I want to reduce soil loss on my sloping field"
    slots = extract_slots(text)
    assert slots.indicator == "soil loss"
    assert slots.practice_family == "Erosion control and water management"
    assert "location" in slots.missing
    msg = clarification_message(slots).lower()
    assert "location" in msg
    assert "contour" not in msg  # no invented practices


def test_coords_still_work():
    slots = extract_slots("My farm is at 8.38, 39.37 and I want to reduce erosion.")
    assert slots.is_complete
    assert slots.indicator == "soil loss"
    assert abs(slots.lat - 8.38) < 1e-6


def test_water_use_efficiency_hyphen_and_short_reply():
    """UI label uses 'water-use'; short clarifying replies must still match."""
    full = (
        "Near Hawassa I have limited water — which water management practices "
        "improve water-use efficiency?"
    )
    slots = extract_slots(full)
    assert slots.indicator == "water use efficiency"
    assert slots.practice_family == "Erosion control and water management"
    assert slots.lat is not None
    assert slots.is_complete

    # Follow-up after a clarifying ask (history carries place + challenge).
    follow = extract_slots(
        "improve water-use efficiency",
        history=[
            {
                "role": "user",
                "content": (
                    "Near Hawassa I have limited water — which water management "
                    "practices improve water use?"
                ),
            }
        ],
    )
    assert follow.indicator == "water use efficiency"
    assert follow.practice_family == "Erosion control and water management"
    assert follow.place_name or follow.lat
    assert follow.is_complete
