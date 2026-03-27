from fastapi import FastAPI, Query
from pydantic import BaseModel
import httpx
import re
import json
from typing import Optional

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

    nights = calculate_nights(checkin, checkout)
    results = []

    # Parse from Next.js __NEXT_DATA__ JSON blob
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if match:
        data = json.loads(match.group(1))
        # Navigate: props -> pageProps -> ... find pages key recursively
        hotels = _find_hotels(data)
        for hotel in hotels:
            name = hotel.get("name", "")
            price = hotel.get("price")
            if name and price is not None:
                marketing = hotel.get("marketing", {})
                meal_plan = marketing.get("mealPlan", "No meal plan")
                results.append({
                    "property": name.strip(),
                    "price_adults_only": f"€ {float(price):,.2f}",
                    "price_note": f"Preço apenas para {adults} adulto(s). Crianças têm custo adicional — confirmar no motor de reservas.",
                    "meal_plan": meal_plan,
                    "nights": nights,
                    "adults": adults,
                    "rooms": rooms,
                })

    return results


def _find_hotels(obj) -> list:
    """Recursively find the hotels list inside __NEXT_DATA__."""
    if isinstance(obj, dict):
        if "pages" in obj and isinstance(obj["pages"], dict):
            page1 = obj["pages"].get("1", [])
            if isinstance(page1, list) and page1 and isinstance(page1[0], dict) and "name" in page1[0]:
                return page1
        for v in obj.values():
            result = _find_hotels(v)
            if result:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _find_hotels(item)
            if result:
                return result
    return []


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


class AvailabilityRequest(BaseModel):
    checkin: str
    checkout: str
    adults: int = 2
    rooms: int = 1


@app.post("/availability")
async def post_availability(body: AvailabilityRequest):
    try:
        results = await scrape_martinhal(body.checkin, body.checkout, body.adults, body.rooms)
        nights = calculate_nights(body.checkin, body.checkout)
        return {
            "checkin": body.checkin,
            "checkout": body.checkout,
            "nights": nights,
            "adults": body.adults,
            "rooms": body.rooms,
            "properties": results,
        }
    except Exception as e:
        return {"error": str(e), "properties": []}


@app.get("/health")
async def health():
    return {"status": "ok"}
