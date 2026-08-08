def make_son_id(country_code: str, provider_code: str, station_code: str) -> str:
    """Build public station id: SON-{CC}-{PROVIDER}-{CODE}."""
    cc = country_code.strip().upper()
    provider = provider_code.strip().upper().replace("-", "").replace("_", "")
    code = station_code.strip().upper()
    return f"SON-{cc}-{provider}-{code}"
