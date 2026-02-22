# ⚙️ LPBF Optimizer

Web-Plattform zur Optimierung der LPBF-Produktionsplanung (Laser Powder Bed Fusion).

## Funktionen

- 📋 **Anfragenverwaltung** – Erfassung und Verwaltung von Kundenanfragen mit allen Bauteilparametern
- 🏗️ **Build-Job-Management** – Anlegen und Verwalten von Build-Jobs mit Plattformflächenübersicht
- 🔲 **Nesting-Algorithmus** – Automatische Zuweisung von Anfragen zu Build-Jobs basierend auf XY-Flächenoptimierung
- 🤖 **KI-Preisschätzung** – scikit-learn Regressionsmodell für Preis- und Bauzeitschätzung
- ✉️ **E-Mail-Entwürfe** – GPT-4 generiert professionelle deutsche Kundenanschreiben

## Technologie-Stack

- **Backend:** Python / FastAPI
- **Frontend:** HTML / CSS / JavaScript
- **Datenbank:** PostgreSQL (Railway)
- **KI:** OpenAI GPT-4 + scikit-learn
- **Hosting:** Railway

## Deployment auf Railway

1. Repository mit Railway verbinden
2. Umgebungsvariablen setzen (siehe `.env.example`)
3. PostgreSQL-Datenbank hinzufügen
4. Schema ausführen: `database/lpbf_schema.sql`
5. Railway deployed automatisch bei jedem Push

## Umgebungsvariablen

| Variable | Beschreibung |
|---|---|
| `DATABASE_URL` | Von Railway automatisch bereitgestellt |
| `OPENAI_API_KEY` | OpenAI API-Schlüssel |
| `SECRET_KEY` | JWT-Geheimschlüssel (zufälligen String generieren) |
| `ADMIN_USERNAME` | Standard-Admin-Benutzername (Standard: admin) |
| `ADMIN_PASSWORD` | Standard-Admin-Passwort (Standard: lpbf2024!) |

## Erster Start

Beim ersten Start wird automatisch ein Admin-Benutzer angelegt.
Zugangsdaten entsprechen den gesetzten Umgebungsvariablen `ADMIN_USERNAME` und `ADMIN_PASSWORD`.
