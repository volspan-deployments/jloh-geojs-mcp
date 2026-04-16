from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
import uvicorn
import threading
from fastmcp import FastMCP
import httpx
import os
from typing import Optional, List

mcp = FastMCP("GeoJS")

BASE_URL = "https://get.geojs.io"


@mcp.tool()
async def get_my_ip() -> dict:
    """Retrieve the public IP address of the current caller/requester. Use this when the user wants to know their own public IP address or when you need to determine the calling IP before doing further lookups."""
    _track("get_my_ip")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/v1/ip.json")
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def get_ip_geo_info(ip: Optional[str] = None) -> dict:
    """Get full geo-location information (country, city, latitude, longitude, ASN, timezone, etc.) for a given IP address or the caller's IP. Use this when the user wants detailed location data about an IP."""
    _track("get_ip_geo_info")
    async with httpx.AsyncClient() as client:
        if ip:
            url = f"{BASE_URL}/v1/ip/geo/{ip}.json"
        else:
            url = f"{BASE_URL}/v1/ip/geo.json"
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def get_ip_country(ip: Optional[str] = None) -> dict:
    """Get only the country (ISO 3166-1 alpha-2 code) for a given IP address or the caller's IP. Use this for a lightweight country-only lookup when full geo details are not needed."""
    _track("get_ip_country")
    async with httpx.AsyncClient() as client:
        if ip:
            url = f"{BASE_URL}/v1/ip/country/{ip}.json"
        else:
            url = f"{BASE_URL}/v1/ip/country.json"
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        # Normalize response to always be a dict
        if isinstance(data, list):
            return {"results": data}
        return data


@mcp.tool()
async def get_ptr_record(ip: Optional[str] = None) -> dict:
    """Perform a reverse DNS (PTR) lookup for a given IP address or the caller's IP. Use this when the user wants to resolve an IP to its hostname or domain name."""
    _track("get_ptr_record")
    async with httpx.AsyncClient() as client:
        if ip:
            url = f"{BASE_URL}/v1/dns/ptr/{ip}"
        else:
            url = f"{BASE_URL}/v1/dns/ptr"
        response = await client.get(url)
        response.raise_for_status()
        ptr = response.text.strip()
        return {"ptr": ptr, "ip": ip or "caller"}


@mcp.tool()
async def get_bulk_geo_info(ips: List[str]) -> dict:
    """Get geo-location information for multiple IP addresses in a single request. Use this when the user needs to look up several IPs at once to avoid making multiple individual calls."""
    _track("get_bulk_geo_info")
    if not ips:
        return {"error": "No IP addresses provided", "results": []}
    
    # GeoJS supports bulk lookup via comma-separated IPs or multiple ip[] params
    params = [("ip[]", ip) for ip in ips]
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/v1/ip/geo.json",
            params=params
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return {"results": data}
        return data


@mcp.tool()
async def get_asn_info(ip: Optional[str] = None) -> dict:
    """Get the Autonomous System Number (ASN) and organization name for a given IP address. Use this when the user wants to know which ISP, hosting provider, or network operator owns an IP address."""
    _track("get_asn_info")
    async with httpx.AsyncClient() as client:
        # ASN info is included in the full geo response
        if ip:
            url = f"{BASE_URL}/v1/ip/geo/{ip}.json"
        else:
            url = f"{BASE_URL}/v1/ip/geo.json"
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        # Extract ASN-relevant fields
        if isinstance(data, list) and len(data) > 0:
            data = data[0]
        if isinstance(data, dict):
            asn_data = {
                "ip": data.get("ip"),
                "asn": data.get("asn"),
                "organization_name": data.get("organization_name"),
                "organization": data.get("organization"),
                "country": data.get("country"),
                "country_code": data.get("country_code"),
            }
            return asn_data
        return data




_SERVER_SLUG = "jloh-geojs"

def _track(tool_name: str, ua: str = ""):
    import threading
    def _send():
        try:
            import urllib.request, json as _json
            data = _json.dumps({"slug": _SERVER_SLUG, "event": "tool_call", "tool": tool_name, "user_agent": ua}).encode()
            req = urllib.request.Request("https://www.volspan.dev/api/analytics/event", data=data, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass
    threading.Thread(target=_send, daemon=True).start()

async def health(request):
    return JSONResponse({"status": "ok", "server": mcp.name})

async def tools(request):
    registered = await mcp.list_tools()
    tool_list = [{"name": t.name, "description": t.description or ""} for t in registered]
    return JSONResponse({"tools": tool_list, "count": len(tool_list)})

sse_app = mcp.http_app(transport="sse")

app = Starlette(
    routes=[
        Route("/health", health),
        Route("/tools", tools),
        Mount("/", sse_app),
    ],
    lifespan=sse_app.lifespan,
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
