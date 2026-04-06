#!/usr/bin/env python3
"""
Rwanda Air Watch - CLI
Usage: python3 cli.py [command] [options]
"""

import sys
import json
import urllib.request
import urllib.error
from datetime import datetime

# point this at your load balancer or a worker directly
BASE_URL = "http://3.95.187.87:8001"

CITIES = ["Kigali", "Musanze", "Rubavu"]

# AQI color codes for terminal
RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
ORANGE = "\033[38;5;208m"
RED    = "\033[91m"
DIM    = "\033[2m"
CYAN   = "\033[96m"


def aqi_color(aqi):
    if aqi is None:
        return DIM
    if aqi <= 50:
        return GREEN
    if aqi <= 100:
        return YELLOW
    if aqi <= 150:
        return ORANGE
    return RED


def aqi_label(aqi):
    if aqi is None:
        return "N/A"
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Moderate"
    if aqi <= 150:
        return "Unhealthy"
    return "Hazardous"


def fetch(path):
    url = BASE_URL + path
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        print(f"{RED}Error {e.code}: {e.reason}{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"{RED}Could not connect to {BASE_URL}: {e}{RESET}")
        print(f"{DIM}Make sure your servers are running.{RESET}")
        sys.exit(1)


def post(path):
    url = BASE_URL + path
    try:
        req = urllib.request.Request(url, data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        print(f"{RED}Error {e.code}: {e.reason}{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"{RED}Could not connect to {BASE_URL}: {e}{RESET}")
        sys.exit(1)


def rel_time(iso):
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        diff = int((datetime.now().astimezone() - dt).total_seconds())
        if diff < 60:
            return f"{diff}s ago"
        if diff < 3600:
            return f"{diff // 60}m ago"
        return f"{diff // 3600}h ago"
    except Exception:
        return iso[:16]


def cmd_health():
    """Check if all workers are up"""
    print(f"\n{BOLD}Server Health{RESET}")
    print("─" * 40)
    data = fetch("/health")
    status = data.get("status", "unknown")
    color = GREEN if status == "ok" else RED
    print(f"  Status : {color}{status}{RESET}")
    print(f"  Worker : {data.get('worker', '—')}")
    print()


def cmd_latest(city=None, sort="desc"):
    """Show latest air quality readings"""
    path = f"/readings/latest?sort={sort}&limit=10"
    if city:
        path += f"&city={city}"

    data = fetch(path)

    title = f"Latest Readings — {city}" if city else "Latest Readings — All Cities"
    print(f"\n{BOLD}{title}{RESET}")
    print("─" * 60)

    if not data:
        print(f"  {DIM}No readings found. Try running: python3 cli.py poll{RESET}")
        return

    for r in data:
        color = aqi_color(r.get("aqi"))
        label = aqi_label(r.get("aqi"))
        aqi   = r.get("aqi") or "—"
        print(f"\n  {BOLD}{r['city']}{RESET}  {color}AQI {aqi} · {label}{RESET}  {DIM}{rel_time(r.get('recorded_at'))}{RESET}")
        print(f"    PM2.5 : {r.get('pm25') or '—'} µg/m³")
        print(f"    PM10  : {r.get('pm10') or '—'} µg/m³")
        print(f"    NO₂   : {r.get('no2') or '—'} µg/m³")
        print(f"    O₃    : {r.get('o3') or '—'} µg/m³")

    print()


def cmd_history(city, limit=10):
    """Show reading history for a city"""
    if city not in CITIES:
        print(f"{RED}Unknown city: {city}{RESET}")
        print(f"Valid cities: {', '.join(CITIES)}")
        sys.exit(1)

    data = fetch(f"/readings/history?city={city}&limit={limit}")

    print(f"\n{BOLD}Reading History — {city} (last {len(data)}){RESET}")
    print("─" * 70)
    print(f"  {'Time':<18} {'AQI':>5}  {'PM2.5':>7}  {'PM10':>7}  {'NO₂':>7}  {'O₃':>7}")
    print(f"  {'─'*18} {'─'*5}  {'─'*7}  {'─'*7}  {'─'*7}  {'─'*7}")

    for r in data:
        color = aqi_color(r.get("aqi"))
        aqi   = str(r.get("aqi") or "—")
        time  = rel_time(r.get("recorded_at"))
        print(
            f"  {time:<18} {color}{aqi:>5}{RESET}"
            f"  {str(r.get('pm25') or '—'):>7}"
            f"  {str(r.get('pm10') or '—'):>7}"
            f"  {str(r.get('no2') or '—'):>7}"
            f"  {str(r.get('o3') or '—'):>7}"
        )
    print()


def cmd_alerts():
    """Show recent anomaly alerts"""
    data = fetch("/alerts/recent")

    print(f"\n{BOLD}Recent Anomaly Alerts{RESET}")
    print("─" * 60)

    if not data:
        print(f"  {GREEN}No anomalies detected. Air quality is normal.{RESET}\n")
        return

    for a in data[:10]:
        zscore = a.get("z_score") or 0
        color  = RED if zscore > 3.5 else ORANGE
        print(
            f"  {color}{BOLD}{a.get('city')}{RESET}"
            f"  {CYAN}{a.get('pollutant', '').upper()}{RESET}"
            f"  z={zscore:.2f}"
            f"  value={a.get('value', '—')}"
            f"  {DIM}{rel_time(a.get('fired_at'))}{RESET}"
        )
    print()


def cmd_poll():
    """Trigger an immediate data poll from Open-Meteo"""
    print(f"\n{DIM}Polling Open-Meteo Air Quality API...{RESET}")
    data = post("/poll/now")
    count = data.get("polled", 0)
    cities = data.get("cities", [])
    print(f"  {GREEN}Polled {count} cities: {', '.join(cities)}{RESET}")
    print(f"  {DIM}Run 'python3 cli.py latest' to see results{RESET}\n")


def cmd_status():
    """Show system status"""
    data = fetch("/status")
    print(f"\n{BOLD}System Status{RESET}")
    print("─" * 40)
    print(f"  Worker         : {data.get('worker', '—')}")
    print(f"  Total readings : {data.get('total_readings', '—')}")
    print(f"  Last poll      : {rel_time(data.get('last_poll'))}")
    print(f"  Cities         : {', '.join(data.get('cities', []))}")
    print()


def usage():
    print(f"""
{BOLD}Rwanda Air Watch — CLI{RESET}
{DIM}Real-time air quality monitoring for Rwanda{RESET}

{BOLD}Usage:{RESET}
  python3 cli.py <command> [options]

{BOLD}Commands:{RESET}
  {CYAN}latest{RESET}                    Show latest readings for all cities
  {CYAN}latest --city Kigali{RESET}      Filter by city (Kigali, Musanze, Rubavu)
  {CYAN}latest --sort asc{RESET}         Sort by AQI ascending
  {CYAN}history Kigali{RESET}            Show reading history for a city
  {CYAN}history Kigali --limit 20{RESET} Show last 20 readings
  {CYAN}alerts{RESET}                    Show recent anomaly alerts
  {CYAN}poll{RESET}                      Trigger immediate data fetch
  {CYAN}status{RESET}                    Show system status
  {CYAN}health{RESET}                    Check if servers are up

{BOLD}Examples:{RESET}
  python3 cli.py latest
  python3 cli.py latest --city Musanze
  python3 cli.py history Rubavu --limit 5
  python3 cli.py alerts
  python3 cli.py poll
""")


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        usage()
        return

    cmd = args[0]

    if cmd == "health":
        cmd_health()

    elif cmd == "latest":
        city = None
        sort = "desc"
        i = 1
        while i < len(args):
            if args[i] == "--city" and i + 1 < len(args):
                city = args[i + 1]
                i += 2
            elif args[i] == "--sort" and i + 1 < len(args):
                sort = args[i + 1]
                i += 2
            else:
                i += 1
        cmd_latest(city=city, sort=sort)

    elif cmd == "history":
        if len(args) < 2:
            print(f"{RED}Usage: python3 cli.py history <city> [--limit N]{RESET}")
            sys.exit(1)
        city  = args[1]
        limit = 10
        if "--limit" in args:
            idx = args.index("--limit")
            if idx + 1 < len(args):
                limit = int(args[idx + 1])
        cmd_history(city, limit)

    elif cmd == "alerts":
        cmd_alerts()

    elif cmd == "poll":
        cmd_poll()

    elif cmd == "status":
        cmd_status()

    else:
        print(f"{RED}Unknown command: {cmd}{RESET}")
        usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
