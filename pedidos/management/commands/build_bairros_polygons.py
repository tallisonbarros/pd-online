import json
import re
import time
from html import unescape
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand

CITY_PAGE = "https://cepbrasil.org/goias/rio-verde/"
PHOTON_BASE_URL = "https://photon.komoot.io/api/"
USER_AGENT = "PRATO-DELIVERY/1.0"


def fetch_text(url):
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=15) as resp:
        return unescape(resp.read().decode("utf-8", errors="ignore"))


def extract_bairro_links(city_html):
    # City page uses links like href="anhanguera" inside <a class="box">...</a>
    blocks = re.findall(
        r'<a[^>]*class="box"[^>]*href="([^"]+)"[^>]*>\s*<h4[^>]*>(.*?)</h4>',
        city_html,
        flags=re.I | re.S,
    )
    seen = set()
    out = []
    for href, raw_name in blocks:
        name = re.sub(r"<[^>]+>", "", raw_name)
        bairro = re.sub(r"\s+", " ", name).strip()
        if not bairro or bairro.lower().startswith("cep "):
            continue
        key = bairro.lower()
        if key in seen:
            continue
        seen.add(key)
        slug = href.strip().strip("/")
        if not slug:
            continue
        out.append((f"https://cepbrasil.org/goias/rio-verde/{slug}/", bairro))
    return out


def extract_streets(bairro_html):
    streets = re.findall(r"CEP\s*\d{5}-\d{3}\s*-\s*([^<]+)", bairro_html, flags=re.I)
    cleaned = []
    seen = set()
    for raw in streets:
        street = re.sub(r"\s+", " ", raw).strip(" -\n\r\t")
        if not street:
            continue
        key = street.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(street)
    return cleaned


def _geocode_query(query):
    attempts = [
        {
            "q": query,
            "countrycode": "BR",
            "limit": "8",
            "lat": "-17.7923",
            "lon": "-50.9192",
            "zoom": "12",
            "location_bias_scale": "0.2",
            "bbox": "-51.0500,-17.9500,-50.7500,-17.6500",
        },
        {
            "q": query,
            "countrycode": "BR",
            "limit": "8",
            "lat": "-17.7923",
            "lon": "-50.9192",
            "bbox": "-51.0500,-17.9500,-50.7500,-17.6500",
        },
        {"q": query, "countrycode": "BR", "limit": "8"},
        {"q": query, "limit": "8"},
    ]
    for params in attempts:
        try:
            req = Request(f"{PHOTON_BASE_URL}?{urlencode(params)}", headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=8) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception:
            continue

        for feature in payload.get("features", []):
            props = feature.get("properties") or {}
            geom = feature.get("geometry") or {}
            coords = geom.get("coordinates") or []
            if len(coords) < 2:
                continue
            city = (props.get("city") or props.get("town") or props.get("village") or "").strip().lower()
            state = (props.get("state") or "").strip().lower()
            if city and city != "rio verde":
                continue
            if state and ("goias" not in state and "goiás" not in state and state != "go"):
                continue
            return float(coords[0]), float(coords[1])  # lng, lat
    return None


def geocode_street(street, bairro):
    variants = [
        f"{street}, {bairro}, Rio Verde, GO, Brasil",
        f"{street}, Rio Verde, GO, Brasil",
    ]
    for query in variants:
        try:
            point = _geocode_query(query)
        except Exception:
            point = None
        if point:
            return point
    return None


def convex_hull(points):
    # Andrew monotone chain. points are (lng, lat)
    pts = sorted(set(points))
    if len(pts) <= 1:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


class Command(BaseCommand):
    help = "Gera polígonos aproximados de bairros de Rio Verde com base nas ruas/CEPs (convex hull)."

    def handle(self, *args, **options):
        city_html = fetch_text(CITY_PAGE)
        bairro_links = extract_bairro_links(city_html)
        self.stdout.write(f"Bairros encontrados na fonte: {len(bairro_links)}")

        features = []
        for idx, (url, bairro) in enumerate(bairro_links, start=1):
            try:
                html = fetch_text(url)
            except Exception:
                self.stdout.write(f"[{idx}] {bairro}: falha ao baixar página")
                continue

            streets = extract_streets(html)
            points = []
            total_streets = min(len(streets), 80)
            self.stdout.write(f"[{idx}] {bairro}: ruas encontradas {len(streets)} | processando {total_streets}")
            for sidx, street in enumerate(streets[:80], start=1):
                point = geocode_street(street, bairro)
                if point:
                    points.append(point)
                    self.stdout.write(f"  - ({sidx}/{total_streets}) OK: {street}")
                else:
                    self.stdout.write(f"  - ({sidx}/{total_streets}) SEM PONTO: {street}")
                time.sleep(0.03)

            if len(points) < 3:
                self.stdout.write(f"[{idx}] {bairro}: poucos pontos ({len(points)})")
                continue

            hull = convex_hull(points)
            if len(hull) < 3:
                self.stdout.write(f"[{idx}] {bairro}: hull insuficiente ({len(hull)})")
                continue

            ring = [[lng, lat] for (lng, lat) in hull]
            if ring[0] != ring[-1]:
                ring.append(ring[0])

            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                    "properties": {"bairro": bairro, "source": "ceps_hull", "points_used": len(points)},
                }
            )
            self.stdout.write(f"[{idx}] {bairro}: ok ({len(points)} pts, hull {len(hull)})")

        output = {"type": "FeatureCollection", "features": features}
        out_path = Path("pedidos/data/bairros_polygons_generated.geojson")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"Arquivo gerado: {out_path} | polígonos: {len(features)}"))
