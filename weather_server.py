"""
Weather MCP server.

A minimal Model Context Protocol server built with FastMCP that exposes a
single tool, `get_weather`, which looks up current conditions for a city by
calling the free Open-Meteo API (no API key required).

Setup:
    pip install mcp httpx          # or: uv add mcp httpx

Run locally over stdio:
    python weather_server.py
    # or, with uv and no install step:
    uv run --with mcp --with httpx weather_server.py

Test it in isolation with the MCP Inspector:
    npx @modelcontextprotocol/inspector python weather_server.py
"""

import httpx
from mcp.server.fastmcp import FastMCP

# The name shown to hosts when they discover this server.
mcp = FastMCP(
    "weather",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 10000)),
)


_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
# Always bound external calls with a timeout so a slow upstream can't hang
# the server (and the host waiting on it) indefinitely.
_TIMEOUT = httpx.Timeout(10.0)


@mcp.tool()
async def get_weather(city: str) -> dict:
    """Get the current weather for a city.

    Args:
        city: Name of the city to look up, e.g. "Pune" or "Tokyo".

    Returns:
        The resolved location plus current temperature, wind speed, and the
        Open-Meteo weather code. Raises a clear error if the city can't be
        found or the upstream service is unavailable.
    """
    # Validate input server-side rather than trusting the model's argument.
    city = city.strip()
    if not city:
        raise ValueError("city must not be empty")

    # Reuse a single client for both calls within this request.
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        # 1. Resolve the city name to coordinates.
        geo = await client.get(_GEOCODE_URL, params={"name": city, "count": 1})
        geo.raise_for_status()
        results = geo.json().get("results")
        if not results:
            raise ValueError(f"Could not find a location named {city!r}")

        place = results[0]
        lat, lon = place["latitude"], place["longitude"]

        # 2. Fetch current conditions for those coordinates.
        forecast = await client.get(
            _FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,wind_speed_10m,weather_code",
            },
        )
        forecast.raise_for_status()
        current = forecast.json()["current"]

    # Return a small, structured payload rather than the raw upstream blob.
    return {
        "location": f"{place['name']}, {place.get('country', '')}".strip(", "),
        "temperature_c": current["temperature_2m"],
        "wind_speed_kmh": current["wind_speed_10m"],
        "weather_code": current["weather_code"],
    }


if __name__ == "__main__":
    # stdio is the standard transport for a local server launched by a host
    # such as Claude Desktop. Switch to mcp.run(transport="streamable-http")
    # to serve it over HTTP for remote clients instead.
     mcp.run(transport="streamable-http")
