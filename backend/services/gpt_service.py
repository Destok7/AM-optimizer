import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def evaluate_lead_time(
    inquiry_name: str,
    customer_number: str,
    requested_delivery_date: str,
    lead_time_flexible: bool,
    current_build_time_h: float,
    combined_build_time_h: float
) -> str:
    """
    GPT-4 evaluates whether combining this inquiry into a build job
    is advisable given the lead time impact.
    """
    prompt = f"""
Du bist ein Experte für additive Fertigung und Produktionsplanung (LPBF - Laser Powder Bed Fusion).

Bewerte, ob es sinnvoll ist, die folgende Anfrage in einen kombinierten Build-Job einzubeziehen,
unter Berücksichtigung der Lieferzeitauswirkungen.

Anfrage: {inquiry_name}
Kundennummer: {customer_number}
Gewünschtes Lieferdatum: {requested_delivery_date or 'nicht angegeben'}
Lieferzeit flexibel: {'Ja' if lead_time_flexible else 'Nein'}
Aktuelle Bauzeit (einzeln): {current_build_time_h:.1f} Stunden
Neue Bauzeit (kombiniert): {combined_build_time_h:.1f} Stunden
Zeitliche Mehrbelastung: {combined_build_time_h - current_build_time_h:.1f} Stunden

Gib eine kurze, klare Einschätzung (2-3 Sätze) auf Deutsch, ob die Kombination empfehlenswert ist
und warum. Berücksichtige das Lieferdatum und die Flexibilität des Kunden.
"""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.3
    )
    return response.choices[0].message.content.strip()


def generate_email_draft(
    notification_type: str,
    customer_number: str,
    inquiry_number: str,
    order_number: str,
    part_name: str,
    quantity: int,
    original_price: float,
    new_price: float,
    price_reduction_percent: float,
    original_build_time_h: float,
    new_build_time_h: float
) -> dict:
    """
    GPT-4 generates a professional German email draft for the customer.
    Returns subject and body.
    """
    if notification_type == "price_reduction_current":
        context = "aktuellen Auftrags/Anfrage"
        intro = "Im Rahmen unserer Produktionsplanung haben wir die Möglichkeit identifiziert, Ihre aktuelle Anfrage mit anderen Aufträgen zu kombinieren."
    else:
        context = "früheren Anfrage"
        intro = "Im Rahmen unserer laufenden Produktionsplanung haben wir festgestellt, dass Ihre frühere Anfrage nun zu einem günstigeren Preis realisiert werden kann."

    prompt = f"""
Erstelle eine professionelle E-Mail auf Deutsch an einen Kunden eines LPBF-Fertigungsunternehmens.

Kontext: {intro}

Details:
- Kundennummer: {customer_number}
- Anfrage-/Auftragsnummer: {inquiry_number or order_number or 'nicht angegeben'}
- Bauteilname: {part_name}
- Menge: {quantity} Stück
- Ursprünglicher Stückpreis: {original_price:.2f} €
- Neuer Stückpreis: {new_price:.2f} €
- Preisersparnis: {price_reduction_percent:.1f}%
- Ursprüngliche Bauzeit: {original_build_time_h:.1f} Stunden
- Neue Bauzeit (kombiniert): {new_build_time_h:.1f} Stunden

Erstelle:
1. Einen prägnanten Betreff
2. Eine professionelle E-Mail (mit Anrede "Sehr geehrte Damen und Herren,", da kein Name bekannt)

Die E-Mail soll:
- Den Preisvorteil klar kommunizieren
- Die längere Bauzeit transparent erklären
- Um Rückmeldung bitten, ob der Kunde dem zustimmt
- Professionell und freundlich sein
- Mit "Mit freundlichen Grüßen" enden (ohne Absendername)

Antworte im Format:
BETREFF: [Betreff hier]
EMAIL: [E-Mail-Text hier]
"""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        temperature=0.4
    )

    content = response.choices[0].message.content.strip()

    # Parse subject and body
    subject = ""
    body = ""
    if "BETREFF:" in content and "EMAIL:" in content:
        parts = content.split("EMAIL:", 1)
        subject = parts[0].replace("BETREFF:", "").strip()
        body = parts[1].strip()
    else:
        subject = "Preisoptimierung Ihrer Anfrage"
        body = content

    return {"subject": subject, "body": body}
