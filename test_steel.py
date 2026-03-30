"""
BudgetAir scraper: capture the actual flight search API endpoint.
Uses page.route() for clean request interception.
"""
import time
import json
from playwright.sync_api import sync_playwright, Route
from steel import Steel

STEEL_API_KEY = "ste-7VWiliCnCbNCCF5U5cvxYpzzhiRi7ukXLtMTsqjfHZ5uqk27yJFxIGgDWXJTf4AXBy9FsHv9hphgFYAE1YQvAm8UwiJMb3yNIye"
client = Steel(steel_api_key=STEEL_API_KEY)

captured_urls = []
captured_flight_data = []


def scrape_budgetair(origin, destination, depart_date, return_date=None):
    session = client.sessions.create()
    print(f"Session: {session.id}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(
                f"wss://connect.steel.dev?apiKey={STEEL_API_KEY}&sessionId={session.id}"
            )
            ctx = browser.contexts[0]
            page = ctx.new_page()

            # Intercept ALL requests and log non-asset ones
            def handle_route(route: Route):
                req = route.request
                url = req.url
                skip = [".css", ".js", ".png", ".svg", ".woff", ".ico", "favicon",
                        "google", "analytics", "gtm", "fonts", "static"]
                if not any(s in url.lower() for s in skip):
                    captured_urls.append(url)
                route.continue_()

            page.route("**/*", handle_route)

            print("Navigating to BudgetAir homepage...")
            page.goto("https://www.budgetair.com", wait_until="networkidle", timeout=40000)
            time.sleep(2)

            # Dismiss CCPA dialog via JS
            page.evaluate("() => { document.querySelectorAll('dialog button, [role=\"dialog\"] button').forEach(b => b.click()); }")
            time.sleep(1)

            # Focus origin input and type
            print(f"Focusing origin input...")
            page.evaluate("() => { const el = document.getElementById('DEPARTURE_AIRPORT'); if (el) el.focus(); }")
            time.sleep(0.5)

            print(f"Typing {origin}...")
            page.keyboard.type(origin, delay=200)
            time.sleep(3)

            # Check dropdown
            dd_visible = page.evaluate("() => { const dd = document.querySelector('[role=\"listbox\"], [aria-expanded=\"true\"]'); return dd ? dd.textContent.substring(0, 200) : 'none'; }")
            print(f"Dropdown content: {dd_visible[:100]}")

            page.keyboard.press("ArrowDown")
            time.sleep(0.3)
            page.keyboard.press("Enter")
            time.sleep(1)

            # Check origin value
            origin_val = page.evaluate("() => document.getElementById('DEPARTURE_AIRPORT')?.value || 'empty'")
            print(f"Origin value: {origin_val}")

            # Focus destination
            page.evaluate("() => { const el = document.getElementById('DESTINATION_AIRPORT'); if (el) el.focus(); }")
            time.sleep(0.5)
            print(f"Typing {destination}...")
            page.keyboard.type(destination, delay=200)
            time.sleep(3)

            dd2 = page.evaluate("() => { const dd = document.querySelector('[role=\"listbox\"], [aria-expanded=\"true\"]'); return dd ? dd.textContent.substring(0, 200) : 'none'; }")
            print(f"Destination dropdown: {dd2[:100]}")

            page.keyboard.press("ArrowDown")
            time.sleep(0.3)
            page.keyboard.press("Enter")
            time.sleep(1)

            dest_val = page.evaluate("() => document.getElementById('DESTINATION_AIRPORT')?.value || 'empty'")
            print(f"Destination value: {dest_val}")

            # Find and click search button via JS (avoiding the overlay issue)
            print("Clicking search button via JS...")
            page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const btn = btns.find(b => b.getAttribute('data-testid') === 'searchbox-submit-button' ||
                                          b.getAttribute('data-gtm-id') === 'sb-submit-button' ||
                                          (b.textContent.trim().toLowerCase() === 'search flights') ||
                                          (b.textContent.trim().toLowerCase() === 'search' && b.closest('form')));
                if (btn) { btn.scrollIntoView(); btn.click(); console.log('Clicked:', btn.textContent); }
                else { console.log('No search button found'); }
            }""")
            time.sleep(2)
            # Also try submitting the form directly
            page.evaluate("() => { const form = document.querySelector('form'); if (form) form.dispatchEvent(new Event('submit', {bubbles: true})); }")
            time.sleep(2)

            print("Waiting 15s for search results...")
            time.sleep(15)

            final_url = page.url
            content = page.content()

            print(f"\nFinal URL: {final_url}")

            # Show all captured API URLs (not assets)
            print(f"\n--- Captured {len(captured_urls)} non-asset URLs ---")
            flight_urls = [u for u in captured_urls if any(x in u.lower() for x in
                          ["search", "flight", "offer", "fare", "itinerary", "trip", "soa", "api"])]
            print(f"Flight-related URLs ({len(flight_urls)}):")
            for u in flight_urls[:20]:
                print(f"  {u[:120]}")

            # Check page content for Air Premia
            if "air premia" in content.lower():
                idx = content.lower().find("air premia")
                ctx_text = content[max(0,idx-150):idx+300]
                if any(x in ctx_text for x in ["$", "price", "fare", "USD", "duration"]):
                    print("\n*** AIR PREMIA FOUND WITH FLIGHT DATA! ***")
                    print(ctx_text)
                else:
                    print(f"\n(Air Premia in page, context: {ctx_text[:200]})")
            else:
                print("\nAir Premia NOT in page")

            body_text = page.inner_text("body")
            lines = [l.strip() for l in body_text.split("\n") if l.strip()]
            print(f"\n--- Page text (first 60 lines) ---")
            for line in lines[:60]:
                print(line)

            browser.close()

    finally:
        client.sessions.release(session.id)
        print(f"\nSession released.")


if __name__ == "__main__":
    scrape_budgetair("EWR", "NRT", "2026-05-01", "2026-05-15")
