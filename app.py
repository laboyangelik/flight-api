from flask import Flask, request, jsonify
from fast_flights import FlightData, Passengers, get_flights

app = Flask(__name__)


@app.route("/")
def search():
    origin      = request.args.get("origin",      "").strip().upper()
    destination = request.args.get("destination", "").strip().upper()
    depart_date = request.args.get("depart_date", "").strip()
    return_date = request.args.get("return_date", "").strip() or None
    adults      = int(request.args.get("adults",  1))

    if not origin or not destination or not depart_date:
        return jsonify({"error": "origin, destination, and depart_date are required"}), 400

    try:
        flight_data = [FlightData(date=depart_date, from_airport=origin, to_airport=destination)]
        if return_date:
            flight_data.append(FlightData(date=return_date, from_airport=destination, to_airport=origin))

        result = get_flights(
            flight_data=flight_data,
            trip="round-trip" if return_date else "one-way",
            seat="economy",
            passengers=Passengers(adults=adults),
        )

        flights = []
        for f in result.flights[:15]:
            # Parse price string like "$443" or "$1,234" into a number
            try:
                price_num = float(str(f.price).replace("$", "").replace(",", ""))
            except (ValueError, AttributeError):
                price_num = None

            flights.append({
                "price":     price_num,
                "airline":   f.name or "",
                "duration":  f.duration or "",
                "stops":     f.stops,
                "departure": f.departure or "",
                "arrival":   f.arrival or "",
                "is_best":   f.is_best,
            })

        return jsonify({
            "origin":      origin,
            "destination": destination,
            "depart_date": depart_date,
            "return_date": return_date,
            "adults":      adults,
            "flights":     flights,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
