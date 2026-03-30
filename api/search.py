import json
from http.server import BaseHTTPRequestHandler
import urllib.parse

_IMPORT_ERROR = None
try:
    from fli.core import resolve_airport, build_flight_segments, parse_max_stops, parse_cabin_class, parse_sort_by
    from fli.search.flights import SearchFlights
    from fli.models import FlightSearchFilters, PassengerInfo, SortBy
except Exception as e:
    _IMPORT_ERROR = str(e)


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
    return {
        "price": result.price,
        "airline": airlines[0] if airlines else None,
        "airlines": airlines,
        "duration_minutes": result.duration,
        "stops": result.stops,
        "departure": legs[0].departure_datetime.isoformat() if legs else None,
        "arrival": legs[-1].arrival_datetime.isoformat() if legs else None,
        "legs": [_serialize_leg(leg) for leg in legs],
    }


def _run_search(origin, destination, depart_date, return_date, adults, max_stops_str, cabin_str, top_n, sort_by_str="CHEAPEST"):
    origin_airport = resolve_airport(origin)
    dest_airport = resolve_airport(destination)
    stops = parse_max_stops(max_stops_str)
    cabin = parse_cabin_class(cabin_str)
    sort_by = parse_sort_by(sort_by_str) if sort_by_str else SortBy.CHEAPEST

    segments, trip_type = build_flight_segments(
        origin=origin_airport,
        destination=dest_airport,
        departure_date=depart_date,
        return_date=return_date or None,
    )

    filters = FlightSearchFilters(
        trip_type=trip_type,
        passenger_info=PassengerInfo(adults=adults),
        flight_segments=segments,
        stops=stops,
        seat_type=cabin,
        sort_by=sort_by,
    )

    return SearchFlights().search(filters, top_n=top_n) or []


class handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, status, data):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

        def p(key, default=""):
            return (qs.get(key, [default])[0] or default).strip()

        origin = p("origin").upper()
        destination = p("destination").upper()
        _dd = p("depart_date")
        depart_date = _dd if _dd and _dd.lower() not in ("undefined", "null", "none") else ""
        _rd = p("return_date")
        return_date = _rd if _rd and _rd.lower() not in ("undefined", "null", "none") else None
        adults = int(p("adults", "1"))
        max_stops = p("max_stops", "ANY")
        cabin_class = p("cabin_class", "ECONOMY")
        sort_by = p("sort_by", "CHEAPEST")
        top_n = int(p("top_n", "20"))

        if not origin or not destination or not depart_date:
            self.send_json(400, {"error": "origin, destination, and depart_date are required"})
            return

        try:
            results = _run_search(origin, destination, depart_date, return_date, adults, max_stops, cabin_class, top_n, sort_by)

            flights = []
            for r in results[:top_n]:
                if isinstance(r, tuple):
                    outbound, ret = r
                    flights.append({
                        "outbound": _serialize_flight(outbound),
                        "return": _serialize_flight(ret),
                        "price": (outbound.price or 0) + (ret.price or 0),
                    })
                else:
                    flights.append(_serialize_flight(r))

            self.send_json(200, {
                "origin": origin,
                "destination": destination,
                "depart_date": depart_date,
                "return_date": return_date,
                "adults": adults,
                "count": len(flights),
                "flights": flights,
            })

        except ValueError as e:
            self.send_json(400, {"error": str(e)})
        except Exception as e:
            self.send_json(500, {"error": str(e)})
