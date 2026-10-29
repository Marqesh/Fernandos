"""Regression tests built from the live 2026 Saitama organiser heading diagnostics."""
from pathlib import Path
from scraper import parse_saitama_teams, validate_roster

HTML = (Path(__file__).parent / "fixtures" / "saitama_live_h1_2026.html").read_text(encoding="utf-8")
RACE = {"year": 2026, "allow_missing_bib": True, "min_riders": 5}


def test_live_h1_layout_and_guest_filter():
    parsed = parse_saitama_teams(HTML)
    assert parsed["edition_year"] == 2026
    assert len(parsed["riders"]) == 13
    names = [x["name"] for x in parsed["riders"]]
    assert "Fredrik DVERSNES LAVIK" in names
    assert "Rasmus Søjberg PEDERSEN" in names
    assert "Brandon MCNULTY" in names
    assert "Valentin PARET PEINTRE" not in names  # Special Guests, not assigned to teams
    assert all("Guests" not in x["team"] for x in parsed["riders"])
    assert validate_roster(parsed, RACE) == (True, "OK")


def test_heading_level_changes_do_not_break_it():
    html = HTML.replace("<h1>", "<h3>").replace("</h1>", "</h3>")
    assert len(parse_saitama_teams(html)["riders"]) == 13


def test_wrong_edition_is_rejected():
    html = HTML.replace("2026 ツール", "2025 ツール")
    parsed = parse_saitama_teams(html)
    assert len(parsed["riders"]) == 13
    assert validate_roster(parsed, RACE)[0] is False
