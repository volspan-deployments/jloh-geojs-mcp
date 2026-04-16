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
    """Retrieve the public IP address of the current caller/client making the request. Use this when the user wants to know their own IP address or when you need to discover the current public IP before doing further lookups."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/v1/ip", headers={"Accept": "text/plain"})
        response.raise_for_status()
        ip = response.text.strip()
        return {"ip": ip}


@mcp.tool()
async def get_ip_geo(ip: Optional[str] = None) -> dict:
    """Get full geo-location information (country, city, latitude, longitude, timezone, ASN, organization, etc.) for a given IP address or the caller's IP. Use this when the user wants detailed geographic information about an IP address."""
    async with httpx.AsyncClient() as client:
        if ip:
            url = f"{BASE_URL}/v1/ip/geo/{ip}.json"
        else:
            url = f"{BASE_URL}/v1/ip/geo"
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def get_ip_country(ip: Optional[str] = None) -> dict:
    """Get only the country code (ISO 3166-1 alpha-2) for a given IP address. Use this for lightweight country-level lookups without needing full geo data."""
    async with httpx.AsyncClient() as client:
        if ip:
            url = f"{BASE_URL}/v1/ip/country/{ip}"
        else:
            url = f"{BASE_URL}/v1/ip/country"
        response = await client.get(url, headers={"Accept": "text/plain"})
        response.raise_for_status()
        country = response.text.strip()
        return {"country_code": country, "ip": ip or "caller"}


@mcp.tool()
async def get_ptr_record(ip: Optional[str] = None) -> dict:
    """Perform a reverse DNS (PTR) lookup for a given IP address or the caller's IP. Use this when the user wants to find the hostname associated with an IP address."""
    async with httpx.AsyncClient() as client:
        if ip:
            url = f"{BASE_URL}/v1/dns/ptr/{ip}"
        else:
            url = f"{BASE_URL}/v1/dns/ptr"
        response = await client.get(url, headers={"Accept": "text/plain"})
        response.raise_for_status()
        ptr = response.text.strip()
        return {"ptr": ptr, "ip": ip or "caller"}


@mcp.tool()
async def bulk_get_ip_geo(ips: List[str]) -> dict:
    """Get geo-location information for multiple IP addresses in a single request. Use this when the user needs to look up several IPs at once to avoid making multiple individual requests."""
    if not ips:
        return {"error": "No IP addresses provided", "results": []}
    
    ip_param = ",".join(ips)
    url = f"{BASE_URL}/v1/ip/geo"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params={"ip": ip_param})
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            data = [data]
        return {"results": data, "count": len(data)}


@mcp.tool()
async def get_ip_asn(ip: Optional[str] = None) -> dict:
    """Get the Autonomous System Number (ASN) and organization name associated with a given IP address. Use this when the user wants to know which network or ISP owns an IP address."""
    async with httpx.AsyncClient() as client:
        if ip:
            url = f"{BASE_URL}/v1/ip/geo/{ip}.json"
        else:
            url = f"{BASE_URL}/v1/ip/geo"
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            data = data[0] if data else {}
        result = {
            "ip": data.get("ip", ip or "caller"),
            "asn": data.get("asn"),
            "organization": data.get("organization"),
            "organization_name": data.get("organization_name"),
        }
        return result




_SERVER_SLUG = "jloh-geojs"

def _track(tool_name: str, ua: str = ""):
    try:
        import urllib.request, json as _json
        data = _json.dumps({"slug": _SERVER_SLUG, "event": "tool_call", "tool": tool_name, "user_agent": ua}).encode()
        req = urllib.request.Request("https://www.volspan.dev/api/analytics/event", data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=1)
    except Exception:
        pass

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
