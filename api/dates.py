import json
from http.server import BaseHTTPRequestHandler
import urllib.parse

from fli.core import resolve_airport, build_date_search_segments, parse_max_stops, parse_cabin_class
from fli.search.dates import SearchDates
from fli.models import DateSearchFilters, PassengerInfo


def _run_date_search(origin, destination, start_date, end_date, adults, max_stops_str, cabin_str, trip_duration, is_round_trip):
    origin_airport = resolve_airport(origin)
    dest_airport = resolve_airport(destination)
    stops = parse_max_stops(max_stops_str)
    cabin = parse_cabin_class(cabin_str)

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

    return SearchDates().search(filters) or []


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
        start_date = p("start_date")
        end_date = p("end_date")
        adults = int(p("adults", "1"))
        max_stops = p("max_stops", "ANY")
        cabin_class = p("cabin_class", "ECONOMY")
        trip_duration = int(p("trip_duration", "3"))
        is_round_trip = p("is_round_trip", "false").lower() in ("true", "1", "yes")

        if not origin or not destination or not start_date or not end_date:
            self.send_json(400, {"error": "origin, destination, start_date, and end_date are required"})
            return

        try:
            results = _run_date_search(
                origin, destination, start_date, end_date,
                adults, max_stops, cabin_class, trip_duration, is_round_trip
            )

            dates = []
            for r in results:
                entry = {"price": r.price}
                if hasattr(r, "date"):
                    entry["date"] = str(r.date)
                if hasattr(r, "return_date"):
                    entry["return_date"] = str(r.return_date) if r.return_date else None
                dates.append(entry)

            self.send_json(200, {
                "origin": origin,
                "destination": destination,
                "start_date": start_date,
                "end_date": end_date,
                "is_round_trip": is_round_trip,
                "trip_duration": trip_duration if is_round_trip else None,
                "count": len(dates),
                "dates": dates,
            })

        except ValueError as e:
            self.send_json(400, {"error": str(e)})
        except Exception as e:
            self.send_json(500, {"error": str(e)})
