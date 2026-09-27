"""Offline-Test: prüft Parser und iCal-Ausgabe ohne Zugriff auf fussball.de.
Aufruf:  python tests/test_offline.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fussball_ics as f  # noqa: E402

OWN = "02PV74CN9S000000VS5489B1VTF0A3SN"
T = "https://www.fussball.de/mannschaft/x/-/saison/2627/team-id/"
S = "https://www.fussball.de/spiel/x/-/spiel/"


def game_rows(date, time_, comp, nr, home, hid, away, aid, sid, extra=""):
    return f"""
<tr class="odd row-headline visible-small"><td colspan="6">Samstag, {date}.2026 - {time_} Uhr | {comp}</td></tr>
<tr class="odd row-competition hidden-small">
  <td class="column-date"><span class="hidden-small inline">Sa, {date}.26 |</span>{time_}</td>
  <td colspan="3" class="column-team"><a>{comp}</a></td>
  <td colspan="2"><a>ME | {nr}</a>{extra}</td>
</tr>
<tr class="odd">
  <td class="hidden-small"></td>
  <td class="column-club"><a href="{T}{hid}" class="club-wrapper"><div class="club-logo"></div><div class="club-name">{home}</div></a></td>
  <td class="column-colon">:</td>
  <td class="column-club no-border"><a href="{T}{aid}" class="club-wrapper"><div class="club-name">{away}</div></a></td>
  <td class="column-score"><a href="{S}{sid}"><span data-obfuscation="x">&#xE6A1;</span></a></td>
  <td class="column-detail"><a href="{S}{sid}">Zum Spiel</a></td>
</tr>"""


MATCHPLAN = "<table>" + "".join([
    game_rows("03.10", "11:00", "Kreisklasse C", "666240023", "Viktoria Berlin XV", OWN,
              "1.FC Lübars IV", "0313FG5DE8000000VS5489BSVSCPI5U4", "031G0BQ3EG000000VS5489BTVVG7L386"),
    game_rows("10.10", "09:30", "Kreisklasse C", "666240027", "Viktoria Berlin XIV", "02M8PJIFDO000000VS5489B2VUHJA7LU",
              "Viktoria Berlin XV", OWN, "031G0BQ3B8000000VS5489BTVVG7L386"),
    game_rows("07.11", "**", "Kreisklasse C", "666240034", "Viktoria Berlin XV", OWN,
              "Nordberliner SC VII", "02Q4LMH8CK000000VS5489B1VTILVS2U", "031G0BQ374000000VS5489BTVVG7L386"),
    game_rows("28.11", "14:30", "Kreisklasse C", "666240045", "CFC Berlin, IV; Test", "02PQHNG0J0000000VS5489B2VUGLP840",
              "Viktoria Berlin XV", OWN, "031G0BQ32S000000VS5489BTVVG7L386", extra="<span>Absetzung</span>"),
    '<tr><td class="column-date">Sa, 14.11.26 | </td><td>SPIELFREI</td></tr>',
]) + "</table>"

SPIELSEITE = ('<a href="https://www.google.de/maps?q=Ostpreu%C3%9Fendamm+3-17">'
              'Kunstrasenplatz, Stadion Lichterfelde KR1, Ostpreußendamm 3-17, 12207 Berlin</a>')


def main():
    games = f.parse_matchplan(MATCHPLAN, OWN)
    assert len(games) == 4, games
    g1, g2, g3, g4 = games
    assert g1["is_home"] and g1["opponent"] == "1.FC Lübars IV" and g1["start"].hour == 11
    assert not g2["is_home"] and g2["opponent"] == "Viktoria Berlin XIV"
    assert g3["start"] is None, "Anstoßzeit ** muss ganztägig werden"
    assert g4["cancelled"] and not g1["cancelled"]
    assert g1["number"] == "666240023"

    venue = f.parse_venue(SPIELSEITE)
    assert venue.startswith("Kunstrasenplatz"), venue
    for g in games:
        g["venue"] = venue

    ics = f.build_ics(games, "Viktoria Berlin XV (E-Junioren)", 90, "", fmt="gegner")
    assert all(len(l.encode()) <= 75 for l in ics.split("\r\n")), "Zeilen zu lang"

    from icalendar import Calendar  # unabhängiger Parser als Gegenprobe
    cal = Calendar.from_ical(ics)
    events = [c for c in cal.walk("VEVENT")]
    assert len(events) == 4
    assert str(events[0]["SUMMARY"]) == "⚽ Heimspiel gegen 1.FC Lübars IV"
    assert str(events[3]["STATUS"]) == "CANCELLED"
    assert str(events[3]["SUMMARY"]).startswith("⚽ ABGESAGT: Auswärts bei CFC Berlin, IV; Test")
    assert str(events[0]["LOCATION"]).endswith("12207 Berlin")

    # Modus "ein": Termin beginnt 60 min vor Anstoß, endet 90 min nach Anstoß
    ein = [c for c in Calendar.from_ical(f.build_ics(games, "T", 90, "", 60, "ein", "gegner")).walk("VEVENT")]
    assert len(ein) == 4
    assert ein[0]["DTSTART"].dt.strftime("%H:%M") == "10:00"
    assert ein[0]["DTEND"].dt.strftime("%H:%M") == "12:30"
    assert str(ein[0]["SUMMARY"]) == "⚽ Heimspiel gegen 1.FC Lübars IV (Anstoß 11:00)"
    assert "Treffen: 10:00 Uhr" in str(ein[0]["DESCRIPTION"])
    assert ein[2]["DTSTART"].dt.isoformat() == "2026-11-07", "ohne Anstoßzeit ganztägig, kein Treffen"

    # Modus "zwei": Treffen 10:00-11:00 + Spiel 11:00-12:30
    zwei = [c for c in Calendar.from_ical(f.build_ics(games, "T", 90, "", 60, "zwei", "gegner")).walk("VEVENT")]
    assert len(zwei) == 7  # 3 Spiele mit Uhrzeit x2 + 1 ganztägig
    tr, sp = zwei[0], zwei[1]
    assert str(tr["SUMMARY"]) == "🕐 Treffen: Heimspiel gegen 1.FC Lübars IV"
    assert (tr["DTSTART"].dt.strftime("%H:%M"), tr["DTEND"].dt.strftime("%H:%M")) == ("10:00", "11:00")
    assert (sp["DTSTART"].dt.strftime("%H:%M"), sp["DTEND"].dt.strftime("%H:%M")) == ("11:00", "12:30")
    assert str(tr["UID"]) != str(sp["UID"])
    assert all(str(e["STATUS"]) == "CANCELLED" for e in zwei if "CFC" in str(e["SUMMARY"]))

    # Standard-Titel wie im Widget: Heim – Gast
    std = [c for c in Calendar.from_ical(f.build_ics(games, "T", 90, "", 60)).walk("VEVENT")]
    assert str(std[0]["SUMMARY"]) == "⚽ Viktoria Berlin XV – 1.FC Lübars IV (Anstoß 11:00)", std[0]["SUMMARY"]
    assert str(std[1]["SUMMARY"]) == "⚽ Viktoria Berlin XIV – Viktoria Berlin XV (Anstoß 09:30)"
    assert "(Heimspiel)" in str(std[0]["DESCRIPTION"])

    import json
    assert json.loads(f.to_json(games, "T", 60))["spiele"][0]["treffen"] == "10:00"
    print(f.to_json(games, "Test")[:400])
    print("OK – alle Prüfungen bestanden")


if __name__ == "__main__":
    main()


def test_mehrere_mannschaften(tmp: Path):
    """Zwei Mannschaften aus mannschaften.json, fussball.de simuliert."""
    import json
    cfg = tmp / "mannschaften.json"
    cfg.write_text(json.dumps({
        "einstellungen": {"treffen_vorlauf_min": 60},
        "mannschaften": [
            {"name": "Viktoria Berlin XV (E-Junioren)", "kuerzel": "e-xv",
             "fussball_de": "https://www.fussball.de/mannschaft/x/-/saison/2627/team-id/" + OWN + "#!/"},
            {"name": "Viktoria Berlin XIV (E-Junioren)", "team_id": "02M8PJIFDO000000VS5489B2VUHJA7LU",
             "treffen_vorlauf_min": 45},
            {"name": "Ruht", "team_id": "X" * 32, "aktiv": False},
        ]}), encoding="utf-8")

    teams = f.load_config(cfg)
    assert [t["kuerzel"] for t in teams] == ["e-xv", "viktoria-berlin-xiv-e-junioren"]
    assert teams[0]["team_id"] == OWN and teams[1]["treffen_vorlauf_min"] == 45

    aufrufe = []
    def fake_fetch(_s, url):
        aufrufe.append(url)
        return SPIELSEITE if "/spiel/" in url else MATCHPLAN
    f.fetch, f.time.sleep = fake_fetch, (lambda s: None)
    out = tmp / "docs"
    sys.argv = ["x", "--config", str(cfg), "--out", str(out)]
    assert f.main() == 0

    liste = json.loads((out / "teams.json").read_text())["mannschaften"]
    assert [t["kuerzel"] for t in liste] == ["e-xv", "viktoria-berlin-xiv-e-junioren"]
    for k in ("e-xv", "viktoria-berlin-xiv-e-junioren"):
        assert (out / k / "kalender.ics").exists() and (out / k / "spiele.json").exists()
    xiv = json.loads((out / "viktoria-berlin-xiv-e-junioren" / "spiele.json").read_text())
    assert xiv["spiele"][0]["treffen"] == "10:15", "eigener Vorlauf je Mannschaft"
    spielseiten = [u for u in aufrufe if "/spiel/" in u]
    assert len(spielseiten) == len(set(spielseiten)), "Spielorte nur einmal laden"

    # Fehlerhafte Konfiguration wird sauber gemeldet
    cfg.write_text('{"mannschaften": [{"name": "A", "fussball_de": "https://www.fussball.de/ohne-id"}]}')
    assert f.main() == 2
    print("OK – mehrere Mannschaften")


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        test_mehrere_mannschaften(Path(d))
