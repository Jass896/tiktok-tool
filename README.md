# ShopClips – automatische TikTok-Produktvideos

Jeden Morgen entstehen in der Cloud fertige TikTok-Videos zu deinen Produkten (9:16, KI-Stimme, Wort-für-Wort-Untertitel, Hook, Call-to-Action). In der **ShopClips-App** auf deinem Handy siehst du sie, tippst auf **„An TikTok teilen“** (die Caption wird dabei automatisch kopiert) und postest. Produkte, Fotos und Einstellungen verwaltest du ebenfalls in der App.

**Kosten:** 0 € (GitHub gratis, Stimme gratis). Optional Claude für bessere Texte: ca. 2 Cent im Monat.

---

## Wie es zusammenhängt

- **GitHub-Repository** = das Gehirn. Hier liegt das Tool, hier laufen die Videos vom Band (GitHub Actions).
- **ShopClips-App** = deine Fernbedienung. Eine Web-App, die du wie eine normale App auf den Startbildschirm legst.
- Fertige Videos bleiben 4 Tage in der App abrufbar.

---

## Einrichtung (einmalig, ca. 20 Minuten – am besten am PC)

### 1. Repository anlegen
1. Kostenloses Konto auf [github.com](https://github.com) erstellen.
2. **New repository** → Name `tiktok-tool` → **Public** → *Create repository*.
   > Öffentlich, weil GitHub die App-Seite (GitHub Pages) im Gratis-Tarif nur für öffentliche Repositories hostet. Sichtbar sind damit Code, Produktliste und Videos – deine Schlüssel (Secrets) bleiben immer geheim.
3. **uploading an existing file** anklicken → den **Inhalt** dieses Ordners hineinziehen → *Commit changes*.
   ⚠ Der versteckte Ordner `.github` muss mit. Fehlt er danach: **Add file → Create new file**, als Namen `.github/workflows/daily.yml` eintippen und den Inhalt der Datei hineinkopieren.

### 2. App-Seite einschalten
**Settings → Pages** → bei *Source* „Deploy from a branch“ → Branch **main**, Ordner **/docs** → *Save*.
Nach 1–2 Minuten ist die App erreichbar unter: `https://DEINNAME.github.io/tiktok-tool/`

### 3. Zugangsschlüssel für die App erstellen
**Profilbild → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**
- Name: `ShopClips`, Ablauf: 1 Jahr
- Repository access: **Only select repositories** → `tiktok-tool`
- Permissions → Repository permissions: **Contents: Read and write**, **Actions: Read and write**
- *Generate token* → Token kopieren (beginnt mit `github_pat_`)

### 4. App aufs Handy
1. Die App-Adresse aus Schritt 2 im Handy-Browser öffnen.
2. Menü (⋮) → **„App installieren“** bzw. **„Zum Startbildschirm hinzufügen“**.
3. App öffnen → Benutzername, `tiktok-tool` und den Token eintragen → **Verbinden**.

### 5. Optional: Extras
Im Repository unter **Settings → Secrets and variables → Actions → New repository secret**:

| Name | Wofür |
|---|---|
| `ANTHROPIC_API_KEY` | Bessere, abwechslungsreichere Texte durch Claude ([console.anthropic.com](https://console.anthropic.com)). Ohne Key: eingebaute Vorlagen. |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | Push-Nachricht aufs Handy, wenn neue Videos fertig sind (siehe unten). |

### 6. Erster Test
In der App: **Produkte** → Beispielprodukte durch echte ersetzen (mit Fotos!) → **Videos** → **Jetzt erstellen**. Nach 2–5 Minuten erscheint das Video.

Ab jetzt läuft es jeden Morgen um ca. 7–8 Uhr automatisch.

---

## Täglicher Ablauf in der App

1. **Videos**-Tab öffnen → Video ansehen.
2. **An TikTok teilen** → TikTok auswählen → Caption ins Textfeld einfügen (ist schon kopiert).
3. Sobald du Affiliate bist: **Link hinzufügen → Produkte → Produkt wählen** und **Inhaltsoffenlegung** einschalten.
4. In der App **Gepostet** abhaken.

Funktioniert „Teilen“ in deinem Browser nicht: **Speichern** und das Video in TikTok aus der Galerie hochladen.

**Wöchentlich (5 Min.):** Im TikTok-Affiliate-Marktplatz neue Produkte suchen und in der App eintragen: Preis, Provision, Verkaufszahl, Trend (1–5), Vorteile und 2–5 Fotos. Die App zeigt dir sofort, wie viel Provision pro Verkauf drin ist und welches Produkt als Nächstes drankommt.

---

## Wie das Tool Produkte auswählt

Punkte = Provision pro Verkauf × Nachfrage (Verkäufe) × Trend × Preis-Faktor × Frische

- **Preis-Faktor:** 10–35 € = volle Punkte (Spontankauf-Bereich), billiger oder teurer gibt Abzug.
- **Frische:** Ein Produkt pausiert nach einem Video ein paar Tage und kommt dann mit einem anderen Aufhänger wieder – bis zum eingestellten Maximum.

---

## Regeln, damit dein Account sicher bleibt

- **Affiliate-Voraussetzungen:** mind. 18 Jahre und meist um die 1.000 Follower. Bis dahin in den Einstellungen **Affiliate aktiv** ausgeschaltet lassen – die Videos bauen dann Follower auf.
- **Werbung kennzeichnen:** Mit Provision immer die Inhaltsoffenlegung einschalten (das Tool setzt zusätzlich `#Werbung`).
- **KI-Stimme:** Sicherheitshalber das Label „KI-generierte Inhalte“ aktivieren.
- **Nur echte Vorteile eintragen** – daraus entsteht der Videotext.
- **Abwechslung statt Masse:** Eigene Fotos und kurze Handy-Clips vom Produkt bringen deutlich mehr Reichweite als reine Shop-Bilder.

---

## Optional: Telegram-Benachrichtigung
1. In Telegram **@BotFather** → `/newbot` → Token kopieren.
2. Deinem Bot `/start` schreiben.
3. `https://api.telegram.org/bot<TOKEN>/getUpdates` im Browser öffnen → die Zahl bei `"chat":{"id":` ist deine Chat-ID.
4. Beide als Secrets eintragen (siehe Schritt 5).

In `config.toml` bei `modus` kannst du außerdem `"telegram"` wählen – dann kommt das ganze Video zusätzlich per Telegram.

---

## Optional: Direkt in den TikTok-Posteingang
Mit einer eigenen App auf [developers.tiktok.com](https://developers.tiktok.com) (Login Kit + Content Posting API, Scope `video.upload`) kann das Video direkt als Entwurf in TikTok landen (`modus = "tiktok_inbox"`). TikTok prüft solche Apps und verlangt u. a. eine Website mit Datenschutzerklärung – eher etwas für später. Danach: Secrets `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` setzen, lokal `python run.py tiktok-login` ausführen und das Token als `TIKTOK_REFRESH_TOKEN` eintragen.

---

## Wenn etwas nicht klappt
- **App zeigt „Fehler beim letzten Lauf“:** Auf „Fehler ansehen“ tippen → die rote Zeile öffnen → Text kopieren und Claude schicken.
- **„Token ungültig“:** Token abgelaufen → neuen erstellen (Schritt 3) und in der App neu verbinden.
- **Keine Videos trotz Lauf:** Alle Produkte sind in Pause oder am Limit → neue Produkte eintragen.

## Für Bastler: lokal am PC
Python 3.11+ und ffmpeg installieren, dann:
```
pip install -r requirements.txt
python run.py rank                       # Ranking anzeigen
python run.py make --count 1             # Video erstellen → Ordner output/
```
