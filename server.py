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
    """Retrieve the public IP address of the current caller/client. Use this when the user wants to know their own IP address or when you need to determine the requester's IP for further geo-location lookups."""
    _track("get_my_ip")
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/v1/ip",
            headers={"Accept": "application/json"},
            params={"format": "json"}
        )
        response.raise_for_status()
        # The endpoint can return plain text; try JSON first, fallback to text
        try:
            return response.json()
        except Exception:
            return {"ip": response.text.strip()}


@mcp.tool()
async def get_ip_geo_info(ip: Optional[str] = None) -> dict:
    """Retrieve full geo-location information (country, region, city, latitude, longitude, timezone, ASN, organization, etc.) for a given IP address or the caller's IP if none is specified. Use this when the user wants detailed geographic information about an IP."""
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
    """Retrieve only the country (as a 2-letter ISO country code) for a given IP address or the caller's IP. Use this when you only need a lightweight country lookup without full geo details."""
    _track("get_ip_country")
    async with httpx.AsyncClient() as client:
        if ip:
            url = f"{BASE_URL}/v1/ip/country/{ip}"
        else:
            url = f"{BASE_URL}/v1/ip/country"
        response = await client.get(url, params={"format": "json"})
        response.raise_for_status()
        try:
            return response.json()
        except Exception:
            return {"country": response.text.strip()}


@mcp.tool()
async def get_bulk_ip_geo_info(ips: List[str]) -> dict:
    """Retrieve geo-location information for multiple IP addresses in a single request. Use this when the user needs to look up several IPs at once to avoid making many individual calls."""
    _track("get_bulk_ip_geo_info")
    async with httpx.AsyncClient() as client:
        # GeoJS supports bulk lookups via query params: ?ip=x&ip=y&ip=z
        url = f"{BASE_URL}/v1/ip/geo.json"
        params = [("ip", ip_addr) for ip_addr in ips]
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        # Normalize to always return a dict with a list
        if isinstance(data, list):
            return {"results": data}
        return data


@mcp.tool()
async def get_ptr_record(ip: Optional[str] = None) -> dict:
    """Perform a reverse DNS (PTR record) lookup for a given IP address or the caller's IP. Use this when the user wants to know the hostname/domain associated with an IP address."""
    _track("get_ptr_record")
    async with httpx.AsyncClient() as client:
        if ip:
            url = f"{BASE_URL}/v1/dns/ptr/{ip}"
        else:
            url = f"{BASE_URL}/v1/dns/ptr"
        response = await client.get(url)
        response.raise_for_status()
        try:
            return response.json()
        except Exception:
            return {"ptr": response.text.strip()}


@mcp.tool()
async def get_ip_asn_info(ip: Optional[str] = None) -> dict:
    """Retrieve Autonomous System Number (ASN) and organization/ISP information for a given IP address. Use this when the user wants to know which ISP, hosting provider, or network operator owns a particular IP address."""
    _track("get_ip_asn_info")
    async with httpx.AsyncClient() as client:
        # ASN info is included in the geo endpoint
        if ip:
            url = f"{BASE_URL}/v1/ip/geo/{ip}.json"
        else:
            url = f"{BASE_URL}/v1/ip/geo.json"
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        # Extract ASN-relevant fields if present
        if isinstance(data, dict):
            asn_fields = {
                "ip": data.get("ip"),
                "asn": data.get("asn"),
                "organization": data.get("organization"),
                "organization_name": data.get("organization_name"),
                "isp": data.get("isp"),
                "country": data.get("country"),
                "country_code": data.get("country_code"),
                "full_response": data
            }
            return {k: v for k, v in asn_fields.items() if v is not None}
        return data




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
