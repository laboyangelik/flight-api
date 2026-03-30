from flask import Flask, request, jsonify
from fli.core import resolve_airport, build_flight_segments, build_date_search_segments, parse_max_stops, parse_cabin_class, parse_sort_by
from fli.search.flights import SearchFlights
from fli.search.dates import SearchDates
from fli.models import FlightSearchFilters, DateSearchFilters, PassengerInfo, SortBy

app = Flask(__name__)


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
        results = SearchFlights().search(filters, top_n=top_n) or []

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
        results = SearchDates().search(filters) or []

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


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
