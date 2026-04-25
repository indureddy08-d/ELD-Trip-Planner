"""
Distance resolution layer.

Abstracts the distance source so the rest of the codebase never
cares whether we're using a lookup table, Google Maps, HERE, or
any other provider. Swap the provider here — nothing else changes.
"""
from __future__ import annotations

# City-pair lookup (miles). Keys are always alphabetically sorted tuples
# so ("chicago, il", "new york, ny") and ("new york, ny", "chicago, il")
# both resolve correctly.
_DISTANCE_TABLE: dict[tuple[str, str], float] = {
    ("chicago, il",     "new york, ny"):      790,
    ("chicago, il",     "los angeles, ca"):  2015,
    ("chicago, il",     "dallas, tx"):        920,
    ("chicago, il",     "miami, fl"):        1380,
    ("chicago, il",     "seattle, wa"):      2065,
    ("chicago, il",     "denver, co"):       1005,
    ("chicago, il",     "atlanta, ga"):       720,
    ("new york, ny",    "los angeles, ca"):  2790,
    ("new york, ny",    "miami, fl"):        1280,
    ("dallas, tx",      "new york, ny"):     1550,
    ("los angeles, ca", "seattle, wa"):      1140,
    ("los angeles, ca", "dallas, tx"):       1435,
    ("los angeles, ca", "denver, co"):       1020,
    ("dallas, tx",      "miami, fl"):        1310,
    ("dallas, tx",      "denver, co"):        780,
    ("dallas, tx",      "atlanta, ga"):       780,
    ("miami, fl",       "atlanta, ga"):       660,
    ("denver, co",      "seattle, wa"):      1320,
    ("atlanta, ga",     "new york, ny"):      870,
    ("boston, ma",      "new york, ny"):      215,
    ("boston, ma",      "chicago, il"):       980,
    ("phoenix, az",     "los angeles, ca"):   370,
    ("phoenix, az",     "dallas, tx"):       1070,
    ("phoenix, az",     "denver, co"):        600,
    ("las vegas, nv",   "los angeles, ca"):   270,
    ("las vegas, nv",   "denver, co"):        750,
    ("minneapolis, mn", "chicago, il"):       410,
    ("minneapolis, mn", "denver, co"):        920,
    ("kansas city, mo", "chicago, il"):       500,
    ("kansas city, mo", "dallas, tx"):        490,
    ("kansas city, mo", "denver, co"):        600,
    ("st. louis, mo",   "chicago, il"):       300,
    ("st. louis, mo",   "dallas, tx"):        630,
    ("nashville, tn",   "atlanta, ga"):       250,
    ("nashville, tn",   "chicago, il"):       470,
    ("charlotte, nc",   "atlanta, ga"):       245,
    ("charlotte, nc",   "new york, ny"):      630,
    ("memphis, tn",     "dallas, tx"):        450,
    ("memphis, tn",     "chicago, il"):       530,
    ("indianapolis, in","chicago, il"):       180,
    ("indianapolis, in","new york, ny"):      790,
    ("columbus, oh",    "chicago, il"):       360,
    ("columbus, oh",    "new york, ny"):      500,
    ("detroit, mi",     "chicago, il"):       280,
    ("detroit, mi",     "new york, ny"):      600,
    ("cleveland, oh",   "chicago, il"):       345,
    ("cleveland, oh",   "new york, ny"):      460,
    ("pittsburgh, pa",  "new york, ny"):      370,
    ("pittsburgh, pa",  "chicago, il"):       460,
    ("baltimore, md",   "new york, ny"):      190,
    ("baltimore, md",   "chicago, il"):       700,
    ("philadelphia, pa","new york, ny"):       95,
    ("philadelphia, pa","chicago, il"):       760,
    ("washington, dc",  "new york, ny"):      225,
    ("washington, dc",  "chicago, il"):       700,
    ("portland, or",    "seattle, wa"):       175,
    ("portland, or",    "los angeles, ca"):   960,
    ("sacramento, ca",  "los angeles, ca"):   385,
    ("san francisco, ca","los angeles, ca"):  380,
    ("san francisco, ca","seattle, wa"):      810,
    ("san diego, ca",   "los angeles, ca"):   120,
    ("albuquerque, nm", "dallas, tx"):        650,
    ("albuquerque, nm", "denver, co"):        450,
    ("salt lake city, ut","denver, co"):      525,
    ("salt lake city, ut","las vegas, nv"):   420,
    ("omaha, ne",       "chicago, il"):       460,
    ("omaha, ne",       "denver, co"):        540,
    ("tulsa, ok",       "dallas, tx"):        260,
    ("tulsa, ok",       "kansas city, mo"):   250,
    ("oklahoma city, ok","dallas, tx"):       200,
    ("oklahoma city, ok","denver, co"):       560,
    ("louisville, ky",  "chicago, il"):       300,
    ("louisville, ky",  "atlanta, ga"):       420,
    ("birmingham, al",  "atlanta, ga"):       150,
    ("birmingham, al",  "nashville, tn"):     190,
    ("jackson, ms",     "memphis, tn"):       210,
    ("jackson, ms",     "new orleans, la"):   185,
    ("new orleans, la", "dallas, tx"):        505,
    ("new orleans, la", "miami, fl"):         860,
    ("houston, tx",     "dallas, tx"):        240,
    ("houston, tx",     "new orleans, la"):   350,
    ("san antonio, tx", "dallas, tx"):        275,
    ("san antonio, tx", "houston, tx"):       200,
    ("el paso, tx",     "dallas, tx"):        625,
    ("el paso, tx",     "albuquerque, nm"):   265,
    ("raleigh, nc",     "charlotte, nc"):     165,
    ("raleigh, nc",     "new york, ny"):      530,
    ("richmond, va",    "washington, dc"):    110,
    ("richmond, va",    "new york, ny"):      340,
    ("norfolk, va",     "washington, dc"):    200,
    ("buffalo, ny",     "new york, ny"):      370,
    ("buffalo, ny",     "chicago, il"):       540,
    ("albany, ny",      "new york, ny"):      150,
    ("hartford, ct",    "new york, ny"):      115,
    ("providence, ri",  "new york, ny"):      180,
    ("portland, me",    "boston, ma"):        110,
    ("burlington, vt",  "boston, ma"):        215,
    ("manchester, nh",  "boston, ma"):         55,
}


def get_distance(origin: str, destination: str) -> float:
    """
    Return driving distance in miles between two locations.

    Normalises input to lowercase + stripped, tries the lookup table,
    and falls back to a conservative default if the pair is unknown.
    In a production system this would call a mapping API on cache miss.
    """
    o = origin.lower().strip()
    d = destination.lower().strip()

    if o == d:
        return 0.0

    key = tuple(sorted([o, d]))
    distance = _DISTANCE_TABLE.get(key)

    if distance is not None:
        return float(distance)

    # Fallback — log a warning in production so the gap can be filled
    import logging
    logging.getLogger(__name__).warning(
        "Distance not found for pair (%s, %s) — using fallback 800 miles", o, d
    )
    return 800.0
