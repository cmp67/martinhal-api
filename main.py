from fastapi import FastAPI, Query
import httpx
import re
import json

app = FastAPI(title="Martinhal Availability API", version="1.0.0")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


async def scrape_martinhal(checkin: str, checkout: str, adults: int, rooms: int = 1) -> list:
    url = (
        f"https://booking.martinhal.com/"
        f"?checkin={checkin}&checkout={checkout}"
        f"&adult_room1={adults}&skd-total-rooms={rooms}"
    )

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        response = await client.get(url, headers=HEADERS)
        html = response.text

    # Extract property+price pairs: name appears just before its price in the HTML
    pairs = re.findall(r'"name":"(Martinhal[^"]+)"[^}]{0,200}?"price":(\d+(?:\.\d+)?)', html)

    nights = calculate_nights(checkin, checkout)
    results = []

    for name, price in pairs:
        results.append({
            "property": name.strip(),
            "starting_from": f"€ {float(price):,.2f}",
            "nights": nights,
            "adults": adults,
            "rooms": rooms,
        })

    return results


def calculate_nights(checkin: str, checkout: str) -> int:
    from datetime import date
    return (date.fromisoformat(checkout) - date.fromisoformat(checkin)).days


@app.get("/availability")
async def get_availability(
    checkin: str = Query(..., description="Check-in date (YYYY-MM-DD)"),
    checkout: str = Query(..., description="Check-out date (YYYY-MM-DD)"),
    adults: int = Query(2, description="Number of adults"),
    rooms: int = Query(1, description="Number of rooms"),
):
    """
    Consulta disponibilidade e preços no motor de reservas Martinhal.
    Retorna lista de propriedades com preço inicial para o período solicitado.
    """
    try:
        results = await scrape_martinhal(checkin, checkout, adults, rooms)
        nights = calculate_nights(checkin, checkout)
        return {
            "checkin": checkin,
            "checkout": checkout,
            "nights": nights,
            "adults": adults,
            "rooms": rooms,
            "properties": results,
        }
    except Exception as e:
        return {"error": str(e), "properties": []}


@app.get("/health")
async def health():
    return {"status": "ok"}
