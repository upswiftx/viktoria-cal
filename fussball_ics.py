#!/usr/bin/env python3
"""
fussball.de -> abonnierbare iCal-Kalender (.ics), eine Datei pro Mannschaft

Liest die Mannschaften aus mannschaften.json, lädt je Mannschaft den
Spielplan von fussball.de, holt für kommende Spiele den Spielort und schreibt:
  docs/<kuerzel>/kalender.ics   (für iPhone / Google Kalender)
  docs/<kuerzel>/spiele.json    (für die Abo-Seite)
  docs/teams.json               (Liste aller Mannschaften für die Abo-Seite)

Aufruf:  python fussball_ics.py [--config mannschaften.json] [--out docs]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BASE = "https://www.fussball.de"
TZ = ZoneInfo("Europe/Berlin")
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)

# "Sa, 03.10.26 | 11:00"  (Uhrzeit fehlt, wenn noch nicht angesetzt)
DATE_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{2})(?!\d)\s*\|?\s*(\d{1,2}:\d{2})?")
SPIEL_RE = re.compile(r"/spiel/[^/]+/-/spiel/([A-Z0-9]{20,})")
TEAM_RE = re.compile(r"/team-id/([A-Z0-9]{20,})")
SPIELNR_RE = re.compile(r"\b(\d{6,})\b")
CANCEL_WORDS = ("Absetzung", "Ausfall", "Annullierung", "Nichtantritt", "abgesetzt")
MAPS_RE = re.compile(r"(google\.[a-z.]+/maps|maps\.google\.)")


# --------------------------------------------------------------------------
# Laden
# --------------------------------------------------------------------------
def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "de-DE,de;q=0.9"})
    return s


def fetch(session: requests.Session, url: str) -> str:
    for attempt in range(3):
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
            return r.text
        except requests.RequestException as exc:
            if attempt == 2:
                raise
            print(f"  Wiederhole ({exc})", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    return ""


def matchplan_urls(team_id: str, today: dt.date) -> list[str]:
    von = (today - dt.timedelta(days=150)).isoformat()
    bis = (today + dt.timedelta(days=270)).isoformat()
    return [
        # ganzer Zeitraum (vergangene + kommende Spiele)
        f"{BASE}/ajax.team.matchplan/-/datum-von/{von}/datum-bis/{bis}"
        f"/match-type/-1/max/100/mode/PAGE/team-id/{team_id}",
        # Standardansicht als Rückfallebene
        f"{BASE}/ajax.team.matchplan/-/mode/PAGE/team-id/{team_id}",
    ]


# --------------------------------------------------------------------------
# Parsen
# --------------------------------------------------------------------------
def clean(text: str) -> str:
    return " ".join(text.split())


def team_name(a) -> str:
    el = a.select_one(".club-name")
    return clean((el or a).get_text(" ", strip=True))


def parse_matchplan(html: str, own_team_id: str) -> list[dict]:
    """Findet Datumszeilen und die jeweils folgende Begegnungszeile."""
    soup = BeautifulSoup(html, "html.parser")
    games: list[dict] = []
    current: dict | None = None

    for tr in soup.find_all("tr"):
        text = clean(tr.get_text(" ", strip=True))

        m = DATE_RE.search(text)
        if m and "row-headline" not in (tr.get("class") or []):
            day, month, year, hhmm = m.groups()
            tds = tr.find_all("td")
            competition = clean(tds[1].get_text(" ", strip=True)) if len(tds) > 1 else ""
            nr = SPIELNR_RE.search(text)
            current = {
                "date": dt.date(2000 + int(year), int(month), int(day)),
                "time": hhmm,
                "competition": competition,
                "number": nr.group(1) if nr else "",
                "row_text": text,
            }

        spiel_a = tr.find("a", href=SPIEL_RE)
        if not spiel_a or current is None:
            continue

        # Mannschafts-Links, doppelte (Logo + Name) zusammenfassen
        teams, seen = [], set()
        for a in tr.find_all("a", href=TEAM_RE):
            tid = TEAM_RE.search(a["href"]).group(1)
            if tid in seen:
                continue
            seen.add(tid)
            teams.append((tid, team_name(a)))
        if len(teams) < 2:
            continue

        (home_id, home), (away_id, away) = teams[0], teams[1]
        spiel_id = SPIEL_RE.search(spiel_a["href"]).group(1)
        href = spiel_a["href"]
        url = href if href.startswith("http") else BASE + href
        status_text = current["row_text"] + " " + text

        start = None
        if current["time"]:
            h, mi = map(int, current["time"].split(":"))
            start = dt.datetime.combine(current["date"], dt.time(h, mi), tzinfo=TZ)

        games.append({
            "id": spiel_id,
            "date": current["date"],
            "start": start,  # None = Anstoßzeit noch offen
            "home": home,
            "away": away,
            "is_home": home_id == own_team_id,
            "own": home if home_id == own_team_id else away,
            "opponent": away if home_id == own_team_id else home,
            "competition": current["competition"],
            "number": current["number"],
            "cancelled": any(w in status_text for w in CANCEL_WORDS),
            "url": url.split("#")[0],
            "venue": "",
        })
        current = None

    return games


def parse_venue(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    a = soup.find("a", href=MAPS_RE)
    return clean(a.get_text(" ", strip=True)) if a else ""


# --------------------------------------------------------------------------
# iCal schreiben
# --------------------------------------------------------------------------
VTIMEZONE = """BEGIN:VTIMEZONE
TZID:Europe/Berlin
BEGIN:DAYLIGHT
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
TZNAME:CEST
DTSTART:19700329T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
TZNAME:CET
DTSTART:19701025T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE""".splitlines()


def esc(value: str) -> str:
    return (value.replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def fold(line: str) -> str:
    """Zeilen nach RFC 5545 auf 75 Byte umbrechen (UTF-8-sicher)."""
    raw = line.encode("utf-8")
    parts, limit = [], 75
    while len(raw) > limit:
        cut = limit
        while (raw[cut] & 0xC0) == 0x80:  # nicht mitten im Zeichen trennen
            cut -= 1
        parts.append(raw[:cut])
        raw = raw[cut:]
        limit = 74  # Folgezeilen beginnen mit Leerzeichen
    parts.append(raw)
    return "\r\n ".join(p.decode("utf-8") for p in parts)


def base_title(g: dict, fmt: str = "paarung") -> str:
    if fmt == "gegner":
        return (f"Heimspiel gegen {g['opponent']}" if g["is_home"]
                else f"Auswärts bei {g['opponent']}")
    # wie im fussball.de-Widget: Heim – Gast
    return f"{g['home']} – {g['away']}"


def vevent(uid: str, stamp: str, g: dict, title: str, desc: list[str],
           start: dt.datetime | None, end: dt.datetime | None) -> list[str]:
    lines = ["BEGIN:VEVENT", f"UID:{uid}@fussball-de-ics", f"DTSTAMP:{stamp}"]
    if start and end:
        lines += [
            f"DTSTART;TZID=Europe/Berlin:{start:%Y%m%dT%H%M%S}",
            f"DTEND;TZID=Europe/Berlin:{end:%Y%m%dT%H%M%S}",
        ]
    else:
        lines += [
            f"DTSTART;VALUE=DATE:{g['date']:%Y%m%d}",
            f"DTEND;VALUE=DATE:{g['date'] + dt.timedelta(days=1):%Y%m%d}",
        ]
    lines += [
        f"SUMMARY:{esc(title)}",
        f"DESCRIPTION:{esc(chr(10).join(x for x in desc if x))}",
        f"URL:{g['url']}",
        f"STATUS:{'CANCELLED' if g['cancelled'] else 'CONFIRMED'}",
        "TRANSP:OPAQUE",
    ]
    if g["venue"]:
        lines.append(f"LOCATION:{esc(g['venue'])}")
    lines.append("END:VEVENT")
    return lines


def build_ics(games: list[dict], cal_name: str, duration_min: int, prefix: str,
              treffen_min: int = 0, modus: str = "ein", fmt: str = "paarung") -> str:
    """
    modus "ein":  ein Termin von Treffen bis Spielende (Anstoß steht im Titel)
    modus "zwei": Termin "Treffen" (Treffen bis Anstoß) + Termin "Spiel" (Anstoß bis Ende)
    treffen_min = 0 schaltet den Treffpunkt ab.
    """
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S") + "Z"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//fussball-de-ics//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{esc(cal_name)}",
        "X-WR-TIMEZONE:Europe/Berlin",
        "X-PUBLISHED-TTL:PT6H",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        *VTIMEZONE,
    ]
    for g in games:
        kick = g["start"]
        end = kick + dt.timedelta(minutes=duration_min) if kick else None
        meet = kick - dt.timedelta(minutes=treffen_min) if kick and treffen_min else None
        title = ("ABGESAGT: " if g["cancelled"] else "") + base_title(g, fmt)
        desc = [
            f"Treffen: {meet:%H:%M} Uhr" if meet else "",
            f"Anstoß: {kick:%H:%M} Uhr" if kick else "Anstoßzeit noch nicht festgelegt",
            g["competition"],
            f"{g['home']} – {g['away']} ({'Heimspiel' if g['is_home'] else 'Auswärtsspiel'})",
            f"Spielnummer {g['number']}" if g["number"] else "",
            f"Spielinfo: {g['url']}",
        ]

        if meet and modus == "zwei":
            lines += vevent(f"{g['id']}-treffen", stamp, g,
                            f"{prefix}🕐 Treffen: {title}", desc, meet, kick)
            lines += vevent(g["id"], stamp, g, f"{prefix}⚽ {title}", desc, kick, end)
        elif meet:
            lines += vevent(g["id"], stamp, g,
                            f"{prefix}⚽ {title} (Anstoß {kick:%H:%M})", desc, meet, end)
        else:
            lines += vevent(g["id"], stamp, g, f"{prefix}⚽ {title}", desc, kick, end)

    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in lines) + "\r\n"


def to_json(games: list[dict], cal_name: str, treffen_min: int = 0) -> str:
    def treffen(g):
        if not (g["start"] and treffen_min):
            return None
        return (g["start"] - dt.timedelta(minutes=treffen_min)).strftime("%H:%M")
    return json.dumps({
        "kalender": cal_name,
        "spiele": [{
            "datum": g["date"].isoformat(),
            "anstoss": g["start"].strftime("%H:%M") if g["start"] else None,
            "treffen": treffen(g),
            "heim": g["home"],
            "gast": g["away"],
            "heimspiel": g["is_home"],
            "gegner": g["opponent"],
            "wettbewerb": g["competition"],
            "ort": g["venue"],
            "abgesagt": g["cancelled"],
            "link": g["url"],
        } for g in games],
    }, ensure_ascii=False, indent=2) + "\n"


def write_if_changed(path: Path, content: str) -> bool:
    """Nur schreiben, wenn sich mehr als der Zeitstempel geändert hat."""
    def strip(s: str) -> str:
        return "\n".join(l for l in s.splitlines() if not l.startswith("DTSTAMP:"))
    if path.exists() and strip(path.read_text(encoding="utf-8")) == strip(content):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")
    return True


# --------------------------------------------------------------------------
# Konfiguration
# --------------------------------------------------------------------------
STANDARD = {
    "spieldauer_min": 90,
    "treffen_vorlauf_min": 60,
    "termin_modus": "ein",       # "ein" | "zwei"
    "titel_format": "paarung",   # "paarung" | "gegner"
    "titel_prefix": "",          # eigener Text vor jedem Termin; leer = Kürzel verwenden
    "kuerzel_im_titel": True,    # "D9: " vor jeden Termin setzen
}
UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower().translate(UMLAUTE)).strip("-")
    return s or "team"


def load_config(path: Path) -> list[dict]:
    """Liest mannschaften.json und ergänzt Standardwerte je Mannschaft."""
    cfg = json.loads(path.read_text(encoding="utf-8"))
    basis = {**STANDARD, **cfg.get("einstellungen", {})}
    teams, kuerzel_gesehen = [], set()
    for i, t in enumerate(cfg.get("mannschaften", []), 1):
        if t.get("aktiv", True) is False:
            continue
        quelle = t.get("team_id") or t.get("fussball_de", "")
        # tolerant: ganze Adresse, reine ID oder ID mit Resten wie "#!/"
        m = TEAM_RE.search(quelle) or re.search(r"\b([A-Z0-9]{32})\b", quelle)
        if not m:
            raise ValueError(f"Mannschaft {i} ({t.get('name', '?')}): keine team-id in {quelle!r} gefunden")
        team_id = m.group(1)
        name = t.get("name") or f"Mannschaft {i}"
        k = slug(t.get("kuerzel") or name)
        if k in kuerzel_gesehen:
            raise ValueError(f"Kürzel {k!r} ist doppelt vergeben")
        kuerzel_gesehen.add(k)
        teams.append({**basis, **t, "team_id": team_id, "name": name, "kuerzel": k})
    if not teams:
        raise ValueError("mannschaften.json enthält keine aktive Mannschaft")
    return teams


# --------------------------------------------------------------------------
# Ablauf
# --------------------------------------------------------------------------
def process_team(session, team: dict, out: Path, today: dt.date,
                 ort_cache: dict[str, str], ort_tage: int) -> bool:
    print(f"\n== {team['name']} ({team['kuerzel']}) ==")
    games: dict[str, dict] = {}
    for url in matchplan_urls(team["team_id"], today):
        print(f"Lade {url}")
        try:
            for g in parse_matchplan(fetch(session, url), team["team_id"]):
                games.setdefault(g["id"], g)
        except requests.RequestException as exc:
            print(f"  fehlgeschlagen: {exc}", file=sys.stderr)
        time.sleep(1.5)

    if not games:
        # Nichts überschreiben – sonst wäre der Kalender plötzlich leer.
        print("  Keine Spiele gefunden. Bestehende Dateien bleiben unverändert.", file=sys.stderr)
        return False

    ordered = sorted(games.values(),
                     key=lambda g: (g["date"], g["start"] or dt.datetime.min.replace(tzinfo=TZ)))

    for g in ordered:
        if not today - dt.timedelta(days=1) <= g["date"] <= today + dt.timedelta(days=ort_tage):
            continue
        if g["id"] not in ort_cache:  # z. B. Vereinsduell zweier eigener Teams
            try:
                ort_cache[g["id"]] = parse_venue(fetch(session, g["url"]))
            except requests.RequestException as exc:
                print(f"  Spielort nicht geladen ({exc})", file=sys.stderr)
                ort_cache[g["id"]] = ""
            time.sleep(1.5)
        g["venue"] = ort_cache[g["id"]]
        print(f"  {g['date']} {g['home']} – {g['away']}: {g['venue'] or 'Ort unbekannt'}")

    prefix = team["titel_prefix"] or (
        f"{team['kuerzel'].upper()}: " if team["kuerzel_im_titel"] else "")

    ziel = out / team["kuerzel"]
    changed = write_if_changed(ziel / "kalender.ics", build_ics(
        ordered, team["name"], int(team["spieldauer_min"]), prefix,
        int(team["treffen_vorlauf_min"]), team["termin_modus"], team["titel_format"]))
    write_if_changed(ziel / "spiele.json", to_json(ordered, team["name"], int(team["treffen_vorlauf_min"])))
    print(f"  {len(ordered)} Spiele, Kalender {'aktualisiert' if changed else 'unverändert'}.")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="mannschaften.json")
    ap.add_argument("--out", default="docs")
    ap.add_argument("--ort-tage", type=int, default=120,
                    help="für Spiele in den nächsten N Tagen den Spielort nachladen")
    args = ap.parse_args()

    try:
        teams = load_config(Path(args.config))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Fehler in {args.config}: {exc}", file=sys.stderr)
        return 2

    session = make_session()
    today = dt.datetime.now(TZ).date()
    out = Path(args.out)
    ort_cache: dict[str, str] = {}

    fehler = [t["name"] for t in teams
              if not process_team(session, t, out, today, ort_cache, args.ort_tage)]

    # Liste für die Abo-Seite (nur Mannschaften, für die es einen Kalender gibt)
    liste = [{"kuerzel": t["kuerzel"], "name": t["name"]}
             for t in teams if (out / t["kuerzel"] / "kalender.ics").exists()]
    write_if_changed(out / "teams.json", json.dumps({"mannschaften": liste}, ensure_ascii=False, indent=2) + "\n")

    if fehler:
        print(f"\nOhne Ergebnis: {', '.join(fehler)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
