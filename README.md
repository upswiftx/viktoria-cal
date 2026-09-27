# Spielplan-Kalender für Vereinsmannschaften

Holt zweimal täglich die Spielpläne von fussball.de und stellt für jede Mannschaft einen abonnierbaren Kalender bereit. iPhone und Android gleichen Verlegungen danach von selbst ab. Auf der Abo-Seite wählen Eltern ihre Mannschaft aus und abonnieren mit einem Tipp.

Ablauf: GitHub Actions startet `fussball_ics.py`, das Skript liest `mannschaften.json` und schreibt je Mannschaft `docs/<kürzel>/kalender.ics`. GitHub Pages veröffentlicht den Ordner `docs/`. Es wird kein Server gebraucht und es entstehen keine Kosten.

## Einrichtung (einmalig, ca. 10 Minuten)

1. **Repository anlegen.** Auf github.com ein neues Repository erstellen, z. B. `viktoria-kalender`, Sichtbarkeit **Public** (nötig für kostenloses GitHub Pages; die Spielpläne sind ohnehin öffentlich).
2. **Dateien hochladen.** „Add file“ → „Upload files“ und den *Inhalt* des entpackten Ordners hineinziehen. Der Ordner `.github` ist auf dem Mac versteckt: Die Workflow-Datei am besten über „Add file“ → „Create new file“ mit dem Namen `.github/workflows/kalender.yml` anlegen und den Inhalt hineinkopieren.
3. **Schreibrechte.** Settings → Actions → General → „Workflow permissions“ auf **Read and write permissions**.
4. **Ersten Lauf starten.** Tab „Actions“ → „Spielplan-Kalender aktualisieren“ → „Run workflow“.
5. **GitHub Pages.** Settings → Pages → „Deploy from a branch“, Branch `main`, Ordner `/docs`.
6. **Link verteilen:** `https://<dein-github-name>.github.io/viktoria-kalender/`

## Mannschaft hinzufügen

Im Repository die Datei `mannschaften.json` öffnen, auf den Stift klicken und einen Block ergänzen:

```json
{
  "einstellungen": {
    "spieldauer_min": 90,
    "treffen_vorlauf_min": 60,
    "termin_modus": "ein",
    "titel_format": "paarung"
  },
  "mannschaften": [
    {
      "kuerzel": "e-xv",
      "name": "Viktoria Berlin XV (E-Junioren)",
      "fussball_de": "https://www.fussball.de/mannschaft/viktoria-berlin-xv-fc-viktoria-89-berlin-berlin/-/saison/2627/team-id/02PV74CN9S000000VS5489B1VTF0A3SN"
    },
    {
      "kuerzel": "d-ii",
      "name": "Viktoria Berlin II (D-Junioren)",
      "fussball_de": "HIER DIE ADRESSE DER MANNSCHAFTSSEITE EINFÜGEN",
      "treffen_vorlauf_min": 45
    }
  ]
}
```

- **`fussball_de`:** einfach die Adresse der Mannschaftsseite aus dem Browser kopieren. Die Team-ID wird daraus automatisch gelesen.
- **`name`:** so erscheint die Mannschaft auf der Abo-Seite und als Kalendername im Handy.
- **`kuerzel`:** bestimmt die Kalender-Adresse (`…/d-ii/kalender.ics`). **Nach dem Verteilen nicht mehr ändern**, sonst laufen bestehende Abos ins Leere. Ohne Angabe wird es aus dem Namen gebildet.
- **Kommas beachten:** zwischen zwei Mannschaftsblöcken steht ein Komma, nach dem letzten keines. Ist die Datei fehlerhaft, wird der Workflow rot und nennt die Stelle.

Danach „Commit changes“ und im Tab „Actions“ einmal „Run workflow“ starten, sonst erscheint die neue Mannschaft erst beim nächsten planmäßigen Lauf.

**Mannschaft vorübergehend ausblenden:** `"aktiv": false` in ihren Block schreiben. Ihr Kalender bleibt mit dem letzten Stand erreichbar, wird aber nicht mehr aktualisiert und verschwindet aus der Auswahl.

## Einstellungen

Unter `einstellungen` gelten sie für alle Mannschaften. Jeder Wert lässt sich zusätzlich im Block einer einzelnen Mannschaft überschreiben, z. B. ein kürzerer Treffpunkt für die Kleinen.

| Einstellung | Bedeutung |
|---|---|
| `spieldauer_min` | Spieldauer ab Anstoß in Minuten |
| `treffen_vorlauf_min` | Treffen so viele Minuten vor Anstoß, `0` schaltet es ab |
| `termin_modus` | `ein`: ein Termin von Treffen bis Spielende, Anstoß steht im Titel. `zwei`: getrennte Termine „Treffen“ und „Spiel“ |
| `titel_format` | `paarung`: „Viktoria Berlin XV – 1.FC Lübars IV“ wie im Widget (Heimmannschaft zuerst). `gegner`: „Heimspiel gegen 1.FC Lübars IV“ |
| `titel_prefix` | Text vor jedem Termin, z. B. `"XV: "` |

## Abonnieren

Auf der Abo-Seite oben die Mannschaft wählen, dann:

**iPhone:** „Im iPhone-Kalender abonnieren“ tippen und bestätigen. Das Aktualisierungsintervall lässt sich unter Einstellungen → Kalender → Accounts → Abonnierte Kalender einstellen.

**Android:** „In Google Kalender abonnieren“ tippen und im Browser „Hinzufügen“ bestätigen. Google ruft abonnierte Kalender nach eigenem Takt ab, typischerweise alle 8–24 Stunden.

**Mehrere Kinder:** einfach nacheinander mehrere Mannschaften abonnieren; jede erscheint als eigener Kalender mit eigener Farbe.

**Direktlink für eine Mannschaft:** Nach der Auswahl steht die Mannschaft in der Adresszeile (`…/?team=e-xv`). Diesen Link kann man gezielt in die jeweilige Elterngruppe schicken.

## Wenn etwas nicht klappt

- **Actions-Lauf rot:** Mindestens eine Mannschaft hat keine Spiele geliefert, oder `mannschaften.json` ist fehlerhaft. Das Log nennt die Mannschaft bzw. den Fehler. Die übrigen Mannschaften werden trotzdem aktualisiert, und kein bestehender Kalender wird geleert.
- **Dauerhaft rot:** fussball.de blockiert eventuell die Server von GitHub. Dann das Skript per Cronjob auf eigenem Webspace laufen lassen: `python fussball_ics.py --config mannschaften.json --out /pfad/zum/webordner`.
- **Nach der Winterpause keine Läufe mehr:** GitHub pausiert zeitgesteuerte Workflows nach 60 Tagen ohne Aktivität. Im Tab „Actions“ mit einem Klick wieder aktivieren.
- **Selbst testen, ohne fussball.de:** `python tests/test_offline.py`

## Hinweis

Das Skript nutzt die öffentlich einsehbaren Spielplanseiten von fussball.de mit wenigen Abrufen pro Tag für den internen Vereinsgebrauch. Es ist kein offizieller Dienst des DFB.
