import time
from flask import Flask, request, jsonify
from fli.core import resolve_airport, build_flight_segments, build_date_search_segments, parse_max_stops, parse_cabin_class, parse_sort_by
from fli.search.flights import SearchFlights
from fli.search.dates import SearchDates
from fli.models import FlightSearchFilters, DateSearchFilters, PassengerInfo, SortBy


def _with_retry(fn, retries=3, backoff=20):
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            if "429" in str(e) and attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
            else:
                raise

app = Flask(__name__)



def _build_tfs(legs_out, legs_in=None):
    """Build a Google Flights search URL from leg data."""
    origin = legs_out[0]["from"]
    destination = legs_out[-1]["to"]
    depart_date = legs_out[0]["departure"][:10]
    if legs_in:
        return_date = legs_in[0]["departure"][:10]
        return (
            f"https://www.google.com/travel/flights?hl=en"
            f"#flt={origin}.{destination}.{depart_date}"
            f"*{destination}.{origin}.{return_date};c:USD;e:1;sd:1;t:r"
        )
    else:
        return (
            f"https://www.google.com/travel/flights?hl=en"
            f"#flt={origin}.{destination}.{depart_date};c:USD;e:1;sd:1;t:o"
        )


def _serialize_leg(leg):
    try:
        airline_name = leg.airline.value
    except Exception:
        airline_name = str(leg.airline)
    try:
        from_code = leg.departure_airport.name
    except Exception:
        from_code = str(leg.departure_airport)
    try:
        to_code = leg.arrival_airport.name
    except Exception:
        to_code = str(leg.arrival_airport)
    return {
        "airline": airline_name,
        "flight_number": leg.flight_number,
        "from": from_code,
        "to": to_code,
        "departure": leg.departure_datetime.isoformat(),
        "arrival": leg.arrival_datetime.isoformat(),
        "duration_minutes": leg.duration,
    }


def _serialize_flight(result):
    legs = result.legs or []
    airlines = []
    for leg in legs:
        try:
            name = leg.airline.value
        except Exception:
            name = str(leg.airline)
        if name not in airlines:
            airlines.append(name)
    serialized_legs = [_serialize_leg(leg) for leg in legs]
    try:
        booking_url = _build_tfs(serialized_legs)
    except Exception:
        booking_url = None
    return {
        "price": result.price,
        "airline": airlines[0] if airlines else None,
        "airlines": airlines,
        "duration_minutes": result.duration,
        "stops": result.stops,
        "departure": legs[0].departure_datetime.isoformat() if legs else None,
        "arrival": legs[-1].arrival_datetime.isoformat() if legs else None,
        "legs": serialized_legs,
        "booking_url": booking_url,
    }


def p(args, key, default=""):
    val = (args.get(key, default) or default).strip()
    if val.lower() in ("undefined", "null", "none"):
        return default
    return val


@app.route("/search")
def search():
    args = request.args
    origin = p(args, "origin").upper()
    destination = p(args, "destination").upper()
    depart_date = p(args, "depart_date")
    return_date = p(args, "return_date") or None
    adults = int(p(args, "adults", "1"))
    max_stops = p(args, "max_stops", "ANY")
    cabin_class = p(args, "cabin_class", "ECONOMY")
    sort_by_str = p(args, "sort_by", "CHEAPEST")
    top_n = int(p(args, "top_n", "20"))

    if not origin or not destination or not depart_date:
        return jsonify({"error": "origin, destination, and depart_date are required"}), 400

    try:
        origin_airport = resolve_airport(origin)
        dest_airport = resolve_airport(destination)
        stops = parse_max_stops(max_stops)
        cabin = parse_cabin_class(cabin_class)
        sort_by = parse_sort_by(sort_by_str) if sort_by_str else SortBy.CHEAPEST

        segments, trip_type = build_flight_segments(
            origin=origin_airport,
            destination=dest_airport,
            departure_date=depart_date,
            return_date=return_date,
        )
        filters = FlightSearchFilters(
            trip_type=trip_type,
            passenger_info=PassengerInfo(adults=adults),
            flight_segments=segments,
            stops=stops,
            seat_type=cabin,
            sort_by=sort_by,
        )
        results = _with_retry(lambda: SearchFlights().search(filters, top_n=top_n)) or []

        flights = []
        for r in results[:top_n]:
            if isinstance(r, tuple):
                outbound, ret = r
                s_out = _serialize_flight(outbound)
                s_ret = _serialize_flight(ret)
                try:
                    booking_url = _build_tfs(s_out["legs"], s_ret["legs"])
                except Exception:
                    booking_url = s_out.get("booking_url")
                flights.append({
                    "outbound": s_out,
                    "return": s_ret,
                    "price": (outbound.price or 0) + (ret.price or 0),
                    "booking_url": booking_url,
                })
            else:
                flights.append(_serialize_flight(r))

        return jsonify({
            "origin": origin,
            "destination": destination,
            "depart_date": depart_date,
            "return_date": return_date,
            "adults": adults,
            "count": len(flights),
            "flights": flights,
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/dates")
def dates():
    args = request.args
    origin = p(args, "origin").upper()
    destination = p(args, "destination").upper()
    start_date = p(args, "start_date")
    end_date = p(args, "end_date")
    adults = int(p(args, "adults", "1"))
    max_stops = p(args, "max_stops", "ANY")
    cabin_class = p(args, "cabin_class", "ECONOMY")
    trip_duration = int(p(args, "trip_duration", "7"))
    is_round_trip = p(args, "is_round_trip", "false").lower() in ("true", "1", "yes")

    if not origin or not destination or not start_date or not end_date:
        return jsonify({"error": "origin, destination, start_date, and end_date are required"}), 400

    try:
        origin_airport = resolve_airport(origin)
        dest_airport = resolve_airport(destination)
        stops = parse_max_stops(max_stops)
        cabin = parse_cabin_class(cabin_class)

        segments, trip_type = build_date_search_segments(
            origin=origin_airport,
            destination=dest_airport,
            start_date=start_date,
            trip_duration=trip_duration,
            is_round_trip=is_round_trip,
        )
        filters = DateSearchFilters(
            trip_type=trip_type,
            passenger_info=PassengerInfo(adults=adults),
            flight_segments=segments,
            stops=stops,
            seat_type=cabin,
            from_date=start_date,
            to_date=end_date,
            duration=trip_duration if is_round_trip else None,
        )
        results = _with_retry(lambda: SearchDates().search(filters)) or []

        result_dates = []
        for r in results:
            entry = {"price": r.price}
            if hasattr(r, "date") and r.date:
                if isinstance(r.date, tuple):
                    entry["date"] = r.date[0].strftime("%Y-%m-%d") if r.date[0] else None
                    entry["return_date"] = r.date[1].strftime("%Y-%m-%d") if r.date[1] else None
                else:
                    entry["date"] = str(r.date)
            if hasattr(r, "return_date") and r.return_date and "return_date" not in entry:
                entry["return_date"] = str(r.return_date)
            result_dates.append(entry)

        return jsonify({
            "origin": origin,
            "destination": destination,
            "start_date": start_date,
            "end_date": end_date,
            "is_round_trip": is_round_trip,
            "trip_duration": trip_duration if is_round_trip else None,
            "count": len(result_dates),
            "dates": result_dates,
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/resolve_booking_url")
def resolve_booking_url():
    """Use Steel to fill Google Flights search form and capture the real tfs= URL."""
    args = request.args
    origin = p(args, "origin").upper()
    destination = p(args, "destination").upper()
    depart_date = p(args, "depart_date")
    return_date = p(args, "return_date") or None

    if not origin or not destination or not depart_date:
        return jsonify({"error": "origin, destination, and depart_date are required"}), 400

    # Simple fallback query URL — at minimum opens Google Flights with the right search pre-filled
    trip = "r" if return_date else "o"
    date_part = f"{depart_date},{return_date}" if return_date else depart_date
    fallback_url = f"https://www.google.com/travel/flights?hl=en&q=Flights+from+{origin}+to+{destination}+{date_part.replace('-', '+')}&trip={trip}"

    try:
        import os
        import steel
        from playwright.sync_api import sync_playwright

        steel_api_key = os.environ.get("STEEL_API_KEY")
        steel_client = steel.Steel(steel_api_key=steel_api_key)
        session = steel_client.sessions.create(solve_captcha=True)
        cdp_url = f"wss://connect.steel.dev?sessionId={session.id}&apiKey={steel_api_key}"

        resolved_url = fallback_url
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.connect_over_cdp(cdp_url)
                context = browser.contexts[0]
                page = context.new_page()

                def js_click(el):
                    page.evaluate("el => { el.scrollIntoView({block:'center'}); el.click(); }", el)

                page.goto("https://www.google.com/travel/flights?hl=en", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)

                # Switch to one-way if needed
                if not return_date:
                    try:
                        trip_btn = page.query_selector('[data-value="1"]')
                        if trip_btn:
                            js_click(trip_btn)
                            page.wait_for_timeout(400)
                            ow = page.wait_for_selector('[data-value="2"]', timeout=3000)
                            js_click(ow)
                            page.wait_for_timeout(400)
                    except Exception:
                        pass

                # Fill origin
                try:
                    inp = page.wait_for_selector('input[placeholder="Where from?"]', timeout=8000)
                    inp.click()
                    page.wait_for_timeout(300)
                    page.keyboard.press("Control+A")
                    page.keyboard.type(origin, delay=120)
                    page.wait_for_timeout(2000)
                    opt = page.wait_for_selector('li[role="option"]', timeout=5000)
                    js_click(opt)
                    page.wait_for_timeout(600)
                except Exception:
                    pass

                # Fill destination
                try:
                    inp = page.wait_for_selector('input[placeholder="Where to?"]', timeout=8000)
                    inp.click()
                    page.wait_for_timeout(300)
                    page.keyboard.type(destination, delay=120)
                    page.wait_for_timeout(2000)
                    opt = page.wait_for_selector('li[role="option"]', timeout=5000)
                    js_click(opt)
                    page.wait_for_timeout(600)
                except Exception:
                    pass

                # Fill departure date
                try:
                    inp = page.wait_for_selector('input[placeholder="Departure"]', timeout=6000)
                    js_click(inp)
                    page.wait_for_timeout(400)
                    inp.fill(depart_date)
                    page.wait_for_timeout(400)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(600)
                except Exception:
                    pass

                # Fill return date
                if return_date:
                    try:
                        inp = page.wait_for_selector('input[placeholder="Return"]', timeout=5000)
                        js_click(inp)
                        page.wait_for_timeout(400)
                        inp.fill(return_date)
                        page.wait_for_timeout(400)
                        page.keyboard.press("Enter")
                        page.wait_for_timeout(600)
                    except Exception:
                        pass

                # Click Search
                try:
                    btn = page.wait_for_selector('button[aria-label="Search"], button:has-text("Search")', timeout=6000)
                    js_click(btn)
                except Exception:
                    page.keyboard.press("Enter")

                # Wait for results — the URL will now have tfs= in it
                try:
                    page.wait_for_function("() => window.location.href.includes('tfs=')", timeout=20000)
                except Exception:
                    page.wait_for_timeout(5000)

                live_url = page.url
                if live_url and "google.com/travel/flights" in live_url and live_url != "https://www.google.com/travel/flights?hl=en":
                    resolved_url = live_url

                browser.close()
        finally:
            steel_client.sessions.release(session.id)

        return jsonify({"booking_url": resolved_url})

    except Exception as e:
        return jsonify({"booking_url": fallback_url, "fallback": True, "error": str(e)})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
