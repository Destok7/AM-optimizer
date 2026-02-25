import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_email(calc_data: dict, inquiry_number: str, order_number: str = None) -> dict:
    """Generate a German notification email based on combined calculation results."""

    # Build parts summary for the prompt
    parts_summary = ""
    for p in calc_data.get("parts", []):
        if p.get("inquiry_number") != inquiry_number:
            continue
        manual = p.get("manual_part_price_eur") or 0
        calc = p.get("calc_part_price_eur") or 0
        savings_eur = p.get("price_reduction_eur") or 0
        savings_pct = p.get("price_reduction_percent") or 0
        parts_summary += (
            f"- {p['part_name']} (Anzahl: {p['quantity']}): "
            f"Ursprünglicher Stückpreis: {manual:.2f} €, "
            f"Neuer Stückpreis: {calc:.2f} €, "
            f"Ersparnis: {savings_eur:.2f} € ({savings_pct:.1f}%)\n"
        )

    ref = order_number if order_number else inquiry_number
    ref_type = "Auftrag" if order_number else "Anfrage"

    prompt = f"""Du bist ein professioneller Kundenberater eines LPBF-Fertigungsunternehmens.
Schreibe eine professionelle, freundliche E-Mail auf Deutsch an einen Kunden.

Kontext:
- {ref_type}: {ref}
- Maschine: {calc_data.get('machine')}
- Kalkulationsname: {calc_data.get('calc_name')}
- Ursprünglicher Gesamtpreis: {calc_data.get('total_manual_price', 0):.2f} €
- Neuer Gesamtpreis (kombinierte Kalkulation): {calc_data.get('total_calc_price', 0):.2f} €
- Gesamtersparnis: {calc_data.get('total_savings_eur', 0):.2f} € ({calc_data.get('total_savings_pct', 0):.1f}%)
- Ursprüngliche Bauzeit: wird aus Einzelkalkulation übernommen
- Neue kombinierte Bauzeit: {calc_data.get('combined_build_time_h', 0):.1f} h

Bauteilübersicht:
{parts_summary}

Die E-Mail soll:
1. Die Vorteile der kombinierten Fertigung klar erläutern
2. Die Preisersparnis pro Bauteil und insgesamt hervorheben
3. Die neue Bauzeit nennen
4. Professionell und kundenorientiert formuliert sein
5. Eine klare Betreffzeile haben

Antworte im Format:
BETREFF: [Betreff hier]
INHALT:
[E-Mail-Inhalt hier]"""

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800,
        temperature=0.7,
    )

    text = response.choices[0].message.content.strip()

    # Parse subject and body
    lines = text.split("\n")
    subject = ""
    body_lines = []
    in_body = False

    for line in lines:
        if line.startswith("BETREFF:"):
            subject = line.replace("BETREFF:", "").strip()
        elif line.startswith("INHALT:"):
            in_body = True
        elif in_body:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()
    if not body:
        body = text

    return {"subject": subject, "body": body}
