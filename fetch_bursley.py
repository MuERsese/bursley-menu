#!/usr/bin/env python3
import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright

URL = "https://dining.umich.edu/menus-locations/dining-halls/bursley/"
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "menu.json"

MEALS = ["Breakfast", "Brunch", "Lunch", "Dinner"]
STATIONS = [
    "Signature", "24 Carrots", "Halal", "Pizziti",
    "Wild Fire", "Two Oceans", "Deli", "Finale"
]

# Nutrition markers used both to locate a hidden/visible facts panel and to
# decide whether a captured block is plausibly Nutrition Facts.
NUTRITION_MARKERS = [
    "Serving Size", "Calories", "Total Fat", "Saturated Fat",
    "Cholesterol", "Sodium", "Total Carbohydrate",
    "Dietary Fiber", "Total Sugars", "Protein"
]

EXTRACT_JS = r"""
({meals, stations, nutritionMarkers}) => {
  const norm = s => (s || "").replace(/\s+/g, " ").trim();

  const BADGE_MARKERS = [
    "Gluten Free", "Halal", "Vegetarian", "Vegan",
    "Nutrient Dense", "Carbon Footprint", "MHealthy"
  ];

  const WILD_FIRE_WORDS = [
    "burger", "french fries", "fries",
    "grilled", "grill", "hot dog", "garlic bread"
  ];

  const TWO_OCEANS_WORDS = [
    "stir fry", "stir-fry", "fried rice",
    "lo mein", "chow mein", "teriyaki",
    "wok", "sesame", "orange chicken",
    "beef and broccoli"
  ];

  const BREAKFAST_FINALE_WORDS = [
    "cookie", "cake", "pie", "cobbler", "crisp",
    "brownie", "blondie", "muffin", "donut", "doughnut"
  ];

  function label(el) {
    return norm(el.innerText || "");
  }

  function dishName(a) {
    let s = label(a);
    if (!s) return "";

    let cut = s.length;
    for (const marker of BADGE_MARKERS) {
      // Only cut a badge when it appears after at least one character of
      // the actual dish name. This preserves names beginning with "Halal".
      const needle = " " + marker;
      const i = s.indexOf(needle);
      if (i > 0 && i < cut) cut = i;
    }
    return s.slice(0, cut).trim();
  }

  function dietaryTags(a) {
    const s = label(a);
    const tags = [];

    for (const t of ["Gluten Free", "Halal", "Vegetarian", "Vegan", "MHealthy"]) {
      // Avoid interpreting the leading "Halal" in a dish name as a badge.
      const name = dishName(a);
      const tail = s.slice(name.length);
      if (tail.includes(t)) tags.push(t);
    }

    for (const prefix of ["Nutrient Dense", "Carbon Footprint"]) {
      const m = s.match(new RegExp(prefix + "\\s+(High|Medium|Low)", "i"));
      if (m) tags.push(prefix + " " + m[1][0].toUpperCase() + m[1].slice(1).toLowerCase());
    }

    return [...new Set(tags)];
  }

  function isMenuHref(a) {
    const raw = a.getAttribute("href") || "";
    const resolved = a.href || "";
    return raw === "#" ||
           resolved.endsWith("/bursley/#") ||
           resolved.includes("/menus-locations/dining-halls/bursley/#");
  }

  function isDish(a) {
    if (!a || a.tagName !== "A" || !isMenuHref(a)) return false;
    const d = dishName(a);
    if (!d || d.length < 2 || d.length > 180) return false;
    if (meals.includes(d) || stations.includes(d)) return false;
    if (["close", "CLEAR ALL", "Today’s Menu", "Today's Menu"].includes(d))
      return false;
    if (/^\d{1,2}$/.test(d)) return false;
    return true;
  }

  function nutritionScore(raw) {
    const s = raw || "";
    let score = 0;
    for (const marker of nutritionMarkers) {
      if (s.toLowerCase().includes(marker.toLowerCase())) score++;
    }
    return score;
  }

  function nearbyNutrition(a) {
    const dish = dishName(a);
    if (!dish) return null;

    const candidates = [];
    let p = a.parentElement;

    for (let depth = 1; p && depth <= 8; depth++, p = p.parentElement) {
      candidates.push({el: p, depth, kind: "ancestor"});
      if (p.nextElementSibling) {
        candidates.push({el: p.nextElementSibling, depth, kind: "sibling"});
      }
    }

    let best = null;

    for (const c of candidates) {
      const raw = c.el.textContent || c.el.innerText || "";
      const score = nutritionScore(raw);
      if (score < 2) continue;

      const normalized = norm(raw);
      if (!normalized) continue;

      const dishCount = [...c.el.querySelectorAll("a")].filter(isDish).length;
      const containsDish = normalized.includes(dish);

      // Strong preference for:
      //   - more nutrition labels
      //   - the dish name in the same block
      //   - fewer other dish anchors
      //   - smaller/closer containers
      const rank =
        score * 100 +
        (containsDish ? 40 : 0) -
        Math.min(dishCount, 10) * 10 -
        c.depth * 2 -
        Math.min(normalized.length / 1000, 20);

      if (!best || rank > best.rank) {
        best = {
          raw,
          score,
          rank,
          depth: c.depth,
          kind: c.kind
        };
      }
    }

    return best;
  }

  const anchors = [...document.querySelectorAll("a")];

  // ---------------- meal + dish extraction ----------------
  let activeMeal = null;
  const dishes = [];

  for (let anchorIndex = 0; anchorIndex < anchors.length; anchorIndex++) {
    const a = anchors[anchorIndex];
    const t = label(a);

    if (meals.includes(t) && isMenuHref(a)) {
      activeMeal = t;
      continue;
    }

    if (activeMeal && isDish(a)) {
      const nutrition = nearbyNutrition(a);

      dishes.push({
        meal: activeMeal,
        dish: dishName(a),
        tags: dietaryTags(a),
        anchor_index: anchorIndex,
        embedded_nutrition_raw: nutrition ? nutrition.raw : null,
        embedded_nutrition_score: nutrition ? nutrition.score : 0,
        el: a
      });
    }
  }

  // ---------------- explicit station headings ----------------
  activeMeal = null;
  const stationRecs = [];

  for (const el of document.querySelectorAll("a, h4")) {
    const t = label(el);

    if (el.tagName === "A" && meals.includes(t) && isMenuHref(el)) {
      activeMeal = t;
      continue;
    }

    if (el.tagName === "H4" && stations.includes(t) && activeMeal) {
      stationRecs.push({
        meal: activeMeal,
        station: t,
        el
      });
    }
  }

  // ---------------- explicit station containers ----------------
  const direct = new Map();
  const stationDebug = [];

  for (const s of stationRecs) {
    let p = s.el.parentElement;
    let selected = null;

    for (let depth = 1; p && depth <= 12; depth++, p = p.parentElement) {
      const heads = [...p.querySelectorAll("h4")]
        .map(h => label(h))
        .filter(x => stations.includes(x));

      const dishAnchors = [...p.querySelectorAll("a")].filter(isDish);

      if (heads.length === 1 && dishAnchors.length > 0) {
        selected = {depth, dishAnchors};
        break;
      }
    }

    stationDebug.push({
      meal: s.meal,
      station: s.station,
      direct_container_found: !!selected,
      depth: selected ? selected.depth : null,
      direct_dish_count: selected ? selected.dishAnchors.length : 0
    });

    if (selected) {
      for (const a of selected.dishAnchors) {
        direct.set(a, {meal: s.meal, station: s.station});
      }
    }
  }

  const rows = dishes.map(d => {
    const hit = direct.get(d.el);
    return {
      meal: d.meal,
      dish: d.dish,
      tags: d.tags,
      anchor_index: d.anchor_index,
      nutrition_raw: d.embedded_nutrition_raw,
      nutrition_source: d.embedded_nutrition_raw ? "embedded-dom" : null,
      station: hit && hit.meal === d.meal ? hit.station : "Unresolved",
      method: hit && hit.meal === d.meal ? "container" : "unresolved"
    };
  });

  // ---------------- conservative Bursley station fallbacks ----------------
  for (const meal of meals) {
    const idxs = [];
    for (let i = 0; i < rows.length; i++) {
      if (rows[i].meal === meal) idxs.push(i);
    }
    if (!idxs.length) continue;

    const explicit = idxs.filter(i => rows[i].station !== "Unresolved");

    if (!explicit.length) {
      for (const i of idxs) {
        const dl = rows[i].dish.toLowerCase();
        if (BREAKFAST_FINALE_WORDS.some(k => dl.includes(k))) {
          rows[i].station = "Finale";
          rows[i].method = "fallback-dessert";
        }
      }
      continue;
    }

    const firstExplicit = Math.min(...explicit);
    const deliIdxs = idxs.filter(i => rows[i].station === "Deli");
    const pizzitiIdxs = idxs.filter(i => rows[i].station === "Pizziti");

    const lastDeli = deliIdxs.length ? Math.max(...deliIdxs) : null;
    const lastPizziti = pizzitiIdxs.length ? Math.max(...pizzitiIdxs) : null;

    for (const i of idxs) {
      if (rows[i].station !== "Unresolved") continue;
      const dl = rows[i].dish.toLowerCase();

      if (i < firstExplicit) {
        rows[i].station = "Signature";
        rows[i].method = "fallback-position";
        continue;
      }

      if (lastDeli !== null && i > lastDeli) {
        rows[i].station = "Finale";
        rows[i].method = "fallback-position";
        continue;
      }

      if (lastPizziti !== null && lastDeli !== null &&
          i > lastPizziti && i < lastDeli) {
        if (WILD_FIRE_WORDS.some(k => dl.includes(k))) {
          rows[i].station = "Wild Fire";
          rows[i].method = "fallback-keyword";
          continue;
        }

        if (TWO_OCEANS_WORDS.some(k => dl.includes(k))) {
          rows[i].station = "Two Oceans";
          rows[i].method = "fallback-keyword";
          continue;
        }
      }
    }
  }

  // Element handles cannot be returned from page.evaluate.
  for (const r of rows) delete r.el;

  return {
    rows,
    counts: {
      anchors_total: anchors.length,
      stations: stationRecs.length,
      dishes: dishes.length,
      embedded_nutrition: rows.filter(r => !!r.nutrition_raw).length
    },
    stations: stationDebug
  };
}
"""

VISIBLE_NUTRITION_JS = r"""
({dish, nutritionMarkers}) => {
  const norm = s => (s || "").replace(/\s+/g, " ").trim();

  function visible(el) {
    if (!el || !(el instanceof Element)) return false;
    const st = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return st.display !== "none" &&
           st.visibility !== "hidden" &&
           r.width > 0 && r.height > 0;
  }

  function score(raw) {
    const low = (raw || "").toLowerCase();
    let n = 0;
    for (const marker of nutritionMarkers) {
      if (low.includes(marker.toLowerCase())) n++;
    }
    return n;
  }

  let best = null;

  for (const el of document.querySelectorAll(
      "div, section, article, aside, li, table, tbody, form")) {
    if (!visible(el)) continue;

    const raw = el.innerText || "";
    const s = score(raw);
    if (s < 2) continue;

    const n = norm(raw);
    if (!n) continue;

    const containsDish = n.includes(dish);
    const rank =
      s * 100 +
      (containsDish ? 50 : 0) -
      Math.min(n.length / 1000, 30);

    if (!best || rank > best.rank ||
        (rank === best.rank && n.length < best.length)) {
      best = {raw, score: s, rank, length: n.length};
    }
  }

  return best ? best.raw : null;
}
"""

CLOSE_VISIBLE_JS = r"""
() => {
  const norm = s => (s || "").replace(/\s+/g, " ").trim().toLowerCase();

  function visible(el) {
    if (!el || !(el instanceof Element)) return false;
    const st = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return st.display !== "none" &&
           st.visibility !== "hidden" &&
           r.width > 0 && r.height > 0;
  }

  for (const el of document.querySelectorAll("a, button")) {
    if (visible(el) && norm(el.innerText) === "close") {
      el.click();
      return true;
    }
  }
  return false;
}
"""

ACTIVATE_MEAL_JS = r"""
(meal) => {
  const norm = s => (s || "").replace(/\s+/g, " ").trim();
  for (const a of document.querySelectorAll("a")) {
    if (norm(a.innerText) === meal) {
      const raw = a.getAttribute("href") || "";
      if (raw === "#" || (a.href || "").endsWith("/bursley/#")) {
        a.click();
        return true;
      }
    }
  }
  return false;
}
"""


def _number(raw, label, unit=None):
    if not raw:
        return None
    unit_pat = rf"\s*{re.escape(unit)}" if unit else ""
    m = re.search(
        rf"\b{label}\b\s*:?\s*([0-9]+(?:\.[0-9]+)?){unit_pat}\b",
        raw,
        flags=re.I,
    )
    if not m:
        return None
    v = float(m.group(1))
    return int(v) if v.is_integer() else v


def _serving_size(raw):
    if not raw:
        return None

    patterns = [
        r"Serving Size\s*:?\s*([^\r\n]+)",
        r"Serving Size\s*:?\s*(.+?)(?=\s+Calories\b)",
    ]

    for pat in patterns:
        m = re.search(pat, raw, flags=re.I | re.S)
        if m:
            value = re.sub(r"\s+", " ", m.group(1)).strip(" :-")
            if value and len(value) <= 120:
                return value
    return None


def _isolate_item_raw(raw, dish):
    """Slice a shared DOM nutrition block down to this dish's own panel."""
    if not raw or not dish:
        return raw

    low = raw.lower()
    needle = dish.lower()

    positions = [m.start() for m in re.finditer(re.escape(needle), low)]
    if not positions:
        return raw

    chosen = None
    for pos in positions:
        if "nutrition facts" in low[pos:]:
            chosen = pos

    if chosen is None:
        chosen = positions[-1]

    segment = raw[chosen:]
    seg_low = segment.lower()

    first_nf = seg_low.find("nutrition facts")
    if first_nf >= 0:
        second_nf = seg_low.find(
            "nutrition facts",
            first_nf + len("nutrition facts"),
        )
        if second_nf >= 0:
            segment = segment[:second_nf]

    return segment


def _allergens(raw):
    if not raw:
        return []

    known = [
        ("eggs", "Eggs"),
        ("egg", "Eggs"),
        ("fish", "Fish"),
        ("milk", "Milk"),
        ("peanuts", "Peanuts"),
        ("peanut", "Peanuts"),
        ("sesame", "Sesame"),
        ("shellfish", "Shellfish"),
        ("soy", "Soy"),
        ("tree nuts", "Tree Nuts"),
        ("tree nut", "Tree Nuts"),
        ("wheat", "Wheat"),
        ("barley", "Barley"),
        ("rye", "Rye"),
        ("oats", "Oats"),
        ("oat", "Oats"),
    ]

    m = re.search(
        r"\bContains\b\s*:?\s*(.*?)(?=\bNutrition Facts\b|$)",
        raw,
        flags=re.I | re.S,
    )

    area = m.group(1) if m else ""
    if not area:
        return []

    low = area.lower()
    out = []

    for needle, canonical in known:
        if re.search(rf"\b{re.escape(needle)}\b", low):
            if canonical not in out:
                out.append(canonical)

    return out


def parse_nutrition(raw, dish=None):
    if not raw:
        return None

    raw = _isolate_item_raw(raw, dish)

    result = {
        "serving_size": _serving_size(raw),
        "calories": _number(raw, r"Calories"),
        "total_fat_g": _number(raw, r"Total\s+Fat", "g"),
        "saturated_fat_g": _number(raw, r"Saturated\s+Fat", "g"),
        "trans_fat_g": _number(raw, r"Trans\s+Fat", "g"),
        "cholesterol_mg": _number(raw, r"Cholesterol", "mg"),
        "sodium_mg": _number(raw, r"Sodium", "mg"),
        "total_carbohydrate_g": _number(raw, r"Total\s+Carbohydrate", "g"),
        "dietary_fiber_g": _number(raw, r"Dietary\s+Fiber", "g"),
        "total_sugars_g": _number(raw, r"(?:Total\s+)?Sugars?", "g"),
        "added_sugars_g": _number(raw, r"Added\s+Sugars?", "g"),
        "protein_g": _number(raw, r"Protein", "g"),
        "allergens": _allergens(raw),
        "raw": re.sub(r"\n{3,}", "\n\n", raw).strip(),
    }

    useful = sum(
        result.get(k) is not None
        for k in [
            "calories", "total_fat_g", "sodium_mg",
            "total_carbohydrate_g", "protein_g"
        ]
    )
    return result if useful >= 1 else None


def is_variable_item(dish):
    """Items whose nutrition depends on the user's custom build."""
    d = (dish or "").lower()
    return "made to order" in d or "made-to-order" in d


async def capture_interactive_nutrition(page, row):
    """Fallback for nutrition panels that only appear after interaction."""
    meal = row["meal"]
    dish = row["dish"]
    anchor_index = row["anchor_index"]

    # Activate the meal first so its dish panel is not hidden by a tab.
    try:
        await page.evaluate(ACTIVATE_MEAL_JS, meal)
        await page.wait_for_timeout(120)
    except Exception:
        pass

    anchor = page.locator("a").nth(anchor_index)

    # First try hover because MyNutrition describes single-item nutrition as a
    # mouse-over interaction.
    try:
        await anchor.hover(force=True, timeout=1500)
        await page.wait_for_timeout(180)
        raw = await page.evaluate(
            VISIBLE_NUTRITION_JS,
            {"dish": dish, "nutritionMarkers": NUTRITION_MARKERS},
        )
        if raw:
            await page.mouse.move(2, 2)
            return raw, "hover"
    except Exception:
        pass

    # Then try the MDining item click/popup.
    try:
        await anchor.evaluate("(el) => el.click()")
        await page.wait_for_timeout(220)
        raw = await page.evaluate(
            VISIBLE_NUTRITION_JS,
            {"dish": dish, "nutritionMarkers": NUTRITION_MARKERS},
        )
        if raw:
            await page.evaluate(CLOSE_VISIBLE_JS)
            await page.keyboard.press("Escape")
            return raw, "click"
    except Exception:
        pass

    try:
        await page.evaluate(CLOSE_VISIBLE_JS)
        await page.keyboard.press("Escape")
    except Exception:
        pass

    return None, None


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        page = await browser.new_page(
            viewport={"width": 1440, "height": 1400},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/151.0.0.0 Safari/537.36"
            ),
        )

        print(f"Opening {URL}")
        await page.goto(URL, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(8000)

        height = await page.evaluate("document.body.scrollHeight")
        for y in range(0, int(height) + 1000, 700):
            await page.evaluate(f"window.scrollTo(0,{y})")
            await page.wait_for_timeout(160)

        await page.wait_for_timeout(900)

        data = await page.evaluate(
            EXTRACT_JS,
            {
                "meals": MEALS,
                "stations": STATIONS,
                "nutritionMarkers": NUTRITION_MARKERS,
            },
        )

        title = await page.title()

        # Parse any nutrition already present in hidden DOM.
        for row in data["rows"]:
            if is_variable_item(row["dish"]):
                row["nutrition"] = None
                row["nutrition_source"] = "variable-item"
            else:
                row["nutrition"] = parse_nutrition(
                    row.get("nutrition_raw"), row["dish"]
                )

        embedded_parsed = sum(1 for r in data["rows"] if r["nutrition"])
        print(
            f"Embedded nutrition parsed: "
            f"{embedded_parsed}/{data['counts']['dishes']}"
        )

        # Fallback: interact only with dishes still missing Nutrition Facts.
        missing = [
            r for r in data["rows"]
            if not r["nutrition"] and not is_variable_item(r["dish"])
        ]

        for idx, row in enumerate(missing, 1):
            raw, source = await capture_interactive_nutrition(page, row)
            nutrition = parse_nutrition(raw, row["dish"])

            if nutrition:
                row["nutrition_raw"] = raw
                row["nutrition_source"] = source
                row["nutrition"] = nutrition

            if idx % 10 == 0 or idx == len(missing):
                found_now = sum(1 for r in data["rows"] if r["nutrition"])
                print(
                    f"Nutrition progress: {found_now}/"
                    f"{data['counts']['dishes']}"
                )

        await browser.close()

    meals_out = {}
    assignments = []
    seen = set()

    for r in data["rows"]:
        meal = r["meal"]
        station = r["station"]
        dish = re.sub(r"\s+", " ", r["dish"]).strip()

        key = (meal, station, dish)
        if key in seen:
            continue
        seen.add(key)

        item = {
            "name": dish,
            "tags": r.get("tags", []),
            "nutrition": r.get("nutrition"),
        }

        if is_variable_item(dish):
            item["nutrition_note"] = (
                "Nutrition varies by custom sandwich ingredients and portions."
            )

        meals_out.setdefault(meal, {}).setdefault(station, []).append(item)

        assignments.append({
            "meal": meal,
            "dish": dish,
            "station": station,
            "method": r["method"],
            "nutrition_source": r.get("nutrition_source"),
            "nutrition_found": bool(r.get("nutrition")),
        })

    nutrition_found = sum(
        1
        for meal_map in meals_out.values()
        for items in meal_map.values()
        for item in items
        if item.get("nutrition")
    )

    payload = {
        "source": URL,
        "title": title,
        "captured_at": datetime.now(
            ZoneInfo("America/Detroit")
        ).isoformat(),
        "stations": STATIONS,
        "nutrition_note": (
            "Michigan Dining nutrition values are approximations and can "
            "change with recipes, substitutions, and portion size."
        ),
        "meals": meals_out,
        "_debug": {
            "counts": {
                **data["counts"],
                "nutrition_found": nutrition_found,
            },
            "stations": data["stations"],
            "assignments": assignments,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Wrote {OUT}")
    print(f"Dish anchors found: {data['counts']['dishes']}")
    print(
        f"Nutrition Facts found: "
        f"{nutrition_found}/{data['counts']['dishes']}"
    )

    for meal, station_map in meals_out.items():
        print(meal)
        for station, items in station_map.items():
            nutrition_count = sum(1 for x in items if x.get("nutrition"))
            print(
                f"  {station}: {len(items)} dishes, "
                f"{nutrition_count} with nutrition"
            )
            for item in items[:3]:
                n = item.get("nutrition")
                if n:
                    print(
                        f"    - {item['name']}: "
                        f"{n.get('calories')} kcal, "
                        f"{n.get('protein_g')}g protein"
                    )
                else:
                    print(f"    - {item['name']}: nutrition unavailable")

    if data["counts"]["dishes"] == 0:
        raise SystemExit("ERROR: no dishes parsed.")

if __name__ == "__main__":
    asyncio.run(main())
