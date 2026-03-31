from pydantic import BaseModel
  import httpx
  import re
  import json
  from typing import Optional, List

  app = FastAPI(title="Martinhal Availability API", version="1.0.0")

  HEADERS = {
      "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)
  Chrome/120.0.0.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      "Accept-Language": "en-US,en;q=0.5",
  }


  def build_children_params(children_ages: list) -> str:
      """Build Seekda child URL params: child_room1_1=5&child_room1_2=6"""
      return "".join(f"&child_room1_{i+1}={age}" for i, age in enumerate(children_ages))


  async def scrape_martinhal(checkin: str, checkout: str, adults: int, rooms: int = 1, children_ages: list =
  None) -> list:
      if children_ages is None:
          children_ages = []

      url = (
          f"https://booking.martinhal.com/"
          f"?checkin={checkin}&checkout={checkout}"
          f"&adult_room1={adults}&skd-total-rooms={rooms}"
      )

      async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
          response = await client.get(url, headers=HEADERS)
          html = response.text

      nights = calculate_nights(checkin, checkout)
      children_suffix = build_children_params(children_ages)
      results = []

      match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
      if match:
          data = json.loads(match.group(1))
          hotels = _find_hotels(data)
          for hotel in hotels:
              name = hotel.get("name", "")
              price = hotel.get("price")
              if name and price is not None:
                  marketing = hotel.get("marketing", {})
                  meal_plan = marketing.get("mealPlan", "No meal plan")
                  code = hotel.get("code", "")
                  booking_url = (
                      f"https://booking.martinhal.com/property/{code}"
                      f"?checkin={checkin}&checkout={checkout}"
                      f"&adult_room1={adults}{children_suffix}&skd-total-rooms={rooms}"
                      if code else ""
                  )
                  results.append({
                      "property": name.strip(),
                      "price_adults_only": f"\u20ac {float(price):,.2f}",
                      "price_note": f"Pre\u00e7o de partida para {adults} adulto(s).",
                      "meal_plan": meal_plan,
                      "nights": nights,
                      "adults": adults,
                      "children": children_ages,
                      "rooms": rooms,
                      "booking_url": booking_url,
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
      children: str = Query("", description="Children ages comma-separated, e.g. 5,6"),
  ):
      try:
          children_ages = [int(a.strip()) for a in children.split(",") if a.strip()] if children else []
          results = await scrape_martinhal(checkin, checkout, adults, rooms, children_ages)
          nights = calculate_nights(checkin, checkout)
          return {
              "checkin": checkin,
              "checkout": checkout,
              "nights": nights,
              "adults": adults,
              "children": children_ages,
              "rooms": rooms,
              "properties": results,
          }
      except Exception as e:
          return {"error": str(e), "properties": []}


  def _sanitize_children(v: str | None) -> str:
      """Return empty string for None, unresolved templates, or invalid values."""
      if not v or re.match(r"^\{\{.*\}\}$", str(v).strip()):
          return ""
      return str(v)


  def _sanitize_adults(v) -> int:
      """Return integer adults, defaulting to 2 for None or unresolved templates."""
      if v is None:
          return 2
      s = str(v).strip()
      if re.match(r"^\{\{.*\}\}$", s):
          return 2
      try:
          return int(s)
      except (ValueError, TypeError):
          return 2


  class AvailabilityRequest(BaseModel):
      checkin: str
      checkout: str
      adults: int = 2
      rooms: int = 1
      children: Optional[str] = ""


  @app.post("/availability")
  async def post_availability(body: AvailabilityRequest):
      try:
          raw_children = _sanitize_children(body.children)
          raw_adults = _sanitize_adults(body.adults)
          children_ages = [int(a.strip()) for a in raw_children.split(",") if a.strip()] if raw_children else
   []
          results = await scrape_martinhal(body.checkin, body.checkout, raw_adults, body.rooms,
  children_ages)
          nights = calculate_nights(body.checkin, body.checkout)
          return {
              "checkin": body.checkin,
              "checkout": body.checkout,
              "nights": nights,
              "adults": raw_adults,
              "children": children_ages,
              "rooms": body.rooms,
              "properties": results,
          }
      except Exception as e:
          return {"error": str(e), "properties": []}


  @app.get("/health")
  async def health():
      return {"status": "ok"}
