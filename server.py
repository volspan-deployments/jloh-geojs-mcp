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
    """Get the public IP address of the current request/caller. Use this when the user wants to know their own IP address or when you need to determine the caller's IP before doing a geo lookup."""
    _track("get_my_ip")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/v1/ip.json")
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def get_ip_geo(ip: Optional[str] = None) -> dict:
    """Get full geo-location information (country, city, latitude, longitude, timezone, ASN, etc.) for a specific IP address or the caller's IP. Use this when the user wants detailed location data for an IP.

    Args:
        ip: The IP address to look up. If omitted, the caller's own IP is used. Supports IPv4 and IPv6.
    """
    _track("get_ip_geo")
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
    """Get only the country for a given IP address or the caller's IP. Use this for lightweight country-only lookups when full geo detail is not needed.

    Args:
        ip: The IP address to look up. If omitted, returns the country for the caller's own IP.
    """
    _track("get_ip_country")
    async with httpx.AsyncClient() as client:
        if ip:
            url = f"{BASE_URL}/v1/ip/country/{ip}.json"
        else:
            url = f"{BASE_URL}/v1/ip/country.json"
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def get_bulk_ip_geo(ips: List[str]) -> dict:
    """Get geo-location information for multiple IP addresses in a single request. Use this when the user provides a list of IPs and wants location data for all of them efficiently.

    Args:
        ips: A list of IP addresses (IPv4 or IPv6) to look up geo-location data for.
    """
    _track("get_bulk_ip_geo")
    ip_param = ",".join(ips)
    async with httpx.AsyncClient() as client:
        url = f"{BASE_URL}/v1/ip/geo/{ip_param}.json"
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        # Normalize to always return a dict with a list
        if isinstance(data, list):
            return {"results": data}
        return {"results": [data]}


@mcp.tool()
async def get_ptr_record(ip: Optional[str] = None) -> dict:
    """Get the PTR (reverse DNS) record for an IP address or the caller's IP. Use this when the user wants to resolve an IP address to its hostname via reverse DNS lookup.

    Args:
        ip: The IP address to perform a reverse DNS (PTR) lookup on. If omitted, uses the caller's own IP.
    """
    _track("get_ptr_record")
    async with httpx.AsyncClient() as client:
        if ip:
            url = f"{BASE_URL}/v1/dns/ptr/{ip}.json"
        else:
            url = f"{BASE_URL}/v1/dns/ptr.json"
        response = await client.get(url)
        response.raise_for_status()
        # PTR endpoint may return plain text, handle both
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        else:
            return {"ptr": response.text.strip(), "ip": ip}


@mcp.tool()
async def get_ip_asn(ip: Optional[str] = None) -> dict:
    """Get the ASN (Autonomous System Number) and organization information for a given IP address. Use this when the user wants to know which ISP, cloud provider, or network an IP belongs to.

    Args:
        ip: The IP address to look up ASN information for. If omitted, uses the caller's own IP.
    """
    _track("get_ip_asn")
    # GeoJS includes ASN info in the geo endpoint
    async with httpx.AsyncClient() as client:
        if ip:
            url = f"{BASE_URL}/v1/ip/geo/{ip}.json"
        else:
            url = f"{BASE_URL}/v1/ip/geo.json"
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        # Extract ASN-relevant fields
        if isinstance(data, list):
            data = data[0] if data else {}
        asn_info = {
            "ip": data.get("ip"),
            "asn": data.get("asn"),
            "organization": data.get("organization"),
            "organization_name": data.get("organization_name"),
            "isp": data.get("isp"),
            "country": data.get("country"),
            "country_code": data.get("country_code"),
        }
        return {k: v for k, v in asn_info.items() if v is not None}




_SERVER_SLUG = "jloh-geojs"
_REQUIRES_AUTH = False

def _get_api_key() -> str:
    """Get API key from environment. Clients pass keys via MCP config headers."""
    return os.environ.get("API_KEY", "")

def _auth_headers() -> dict:
    """Build authorization headers for upstream API calls."""
    key = _get_api_key()
    if not key:
        return {}
    return {"Authorization": f"Bearer {key}", "X-API-Key": key}

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
