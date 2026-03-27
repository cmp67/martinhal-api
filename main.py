from fastapi import FastAPI, Query
from playwright.async_api import async_playwright
import re
import asyncio

app = FastAPI(title="Martinhal Availability API", version="1.0.0")


async def scrape_martinhal(checkin: str, checkout: str, adults: int, rooms: int = 1) -> list:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        url = (
            f"https://booking.martinhal.com/"
            f"?checkin={checkin}&checkout={checkout}"
            f"&adult_room1={adults}&skd-total-rooms={rooms}"
        )

        await page.goto(url, wait_until="networkidle", timeout=40000)
        await page.wait_for_timeout(5000)

        # Extrair propriedades via seletores
        results = []
        property_blocks = await page.query_selector_all(".skd-hotel")

        if not property_blocks:
            # Fallback: parse texto bruto
            content = await page.inner_text("body")
            results = parse_text_fallback(content, checkin, checkout, adults, rooms)
        else:
            for block in property_blocks:
                try:
                    name = await block.query_selector(".skd-hotel-name")
                    name_text = await name.inner_text() if name else "N/A"

                    price = await block.query_selector(".skd-price")
                    price_text = await price.inner_text() if price else "N/A"

                    results.append({
                        "property": name_text.strip(),
                        "starting_from": price_text.strip(),
                        "nights": calculate_nights(checkin, checkout),
                        "adults": adults,
                        "rooms": rooms,
                    })
                except Exception:
                    continue

        if not results:
            content = await page.inner_text("body")
            results = parse_text_fallback(content, checkin, checkout, adults, rooms)

        await browser.close()
        return results


def parse_text_fallback(content: str, checkin, checkout, adults, rooms) -> list:
    properties = [
        "Martinhal Lisbon Oriente",
        "Martinhal Lisbon Chiado",
        "Martinhal Quinta Family Resort",
        "Martinhal Sagres Beach Family Resort Hotel",
    ]
    nights = calculate_nights(checkin, checkout)
    results = []

    for prop in properties:
        if prop in content:
            idx = content.index(prop)
            snippet = content[idx:idx+900]
            prices = re.findall(r"€\s*([\d,\.]+)", snippet)
            price = f"€ {prices[0]}" if prices else "N/A"
            results.append({
                "property": prop,
                "starting_from": price,
                "nights": nights,
                "adults": adults,
                "rooms": rooms,
            })

    return results


def calculate_nights(checkin: str, checkout: str) -> int:
    from datetime import date
    fmt = "%Y-%m-%d"
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
