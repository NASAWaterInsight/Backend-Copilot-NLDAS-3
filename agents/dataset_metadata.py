"""
Centralized dataset coverage metadata so the agent can answer availability questions
without executing analysis code.
Update this file whenever new years or products are added.
"""

from datetime import date

DATASET_COVERAGE = {
    "forcing": {
        "description": "NLDAS-3 forcing (hourly, convertible to daily aggregates)",
        "temporal_resolution": "hourly",
        "years_available": [2023],
        "start": "2023-01-01T00:00Z",
        "end": "2023-12-31T23:00Z",
        "variables": [
            {"name": "Tair", "alias": "temperature (air)", "units": "K (convert to °C subtract 273.15)"},
            {"name": "Rainf", "alias": "precipitation rate", "units": "mm (kg/m²)"},
            {"name": "Qair", "alias": "specific humidity", "units": "kg/kg"},
            {"name": "Wind_E", "alias": "eastward wind component", "units": "m/s"},
            {"name": "Wind_N", "alias": "northward wind component", "units": "m/s"},
            {"name": "PSurf", "alias": "surface pressure", "units": "Pa"},
            {"name": "SWdown", "alias": "downward shortwave radiation", "units": "W/m²"},
            {"name": "LWdown", "alias": "downward longwave radiation", "units": "W/m²"}
        ],
        "notes": [
            "Daily values are derived by aggregating hourly data for 2023.",
            "Additional years will extend list in years_available."
        ]
    },
    "spi": {
        "description": "Standardized Precipitation Index (SPI-3 month accumulation)",
        "temporal_resolution": "monthly",
        "years_available": list(range(2003, 2024)),  # 2003–2023 inclusive
        "start": "2003-01",
        "end": "2023-12",
        "variables": [
            {"name": "SPI3", "alias": "3‑month SPI", "units": "unitless"}
        ],
        "notes": [
            "SPI data cannot be provided hourly or daily—only monthly fields exist.",
            "Values below -1.5 indicate severe drought; above 1.5 indicate very wet conditions."
        ]
    }
}

def build_coverage_summary() -> str:
    forcing_years = ", ".join(str(y) for y in DATASET_COVERAGE["forcing"]["years_available"])
    spi_years = f"{DATASET_COVERAGE['spi']['years_available'][0]}–{DATASET_COVERAGE['spi']['years_available'][-1]}"
    return (
        "Data Coverage:\n"
        f"- Forcing (hourly, aggregatable to daily): years {forcing_years} (full 2023 currently).\n"
        f"- SPI (monthly 3‑month accumulation): {spi_years} (all months).\n"  # corrected wording
        "Granularity:\n"
        "- Hourly: Tair, Rainf, Qair, Wind_E, Wind_N, PSurf, SWdown, LWdown (2023).\n"
        "- Monthly: SPI3 (2003–2023).\n"
        "Notes: Request precise variable + region + date/month. SPI cannot produce hourly or daily maps."
    )

def build_coverage_response():
    return {
        "type": "dataset_coverage",
        "summary": build_coverage_summary(),
        "metadata": DATASET_COVERAGE,
        "last_updated": str(date.today())
    }
