# Bursley Menu Data

A lightweight, machine-readable snapshot of the current **University of Michigan Bursley Dining Hall** menu, including dining stations, dietary tags, and per-item nutrition information when available.

The data is collected from the official Michigan Dining Bursley menu page and published to [`menu.json`](./menu.json) for easy use by scripts, assistants, dashboards, or other personal tools.

> **Official source:** https://dining.umich.edu/menus-locations/dining-halls/bursley/
>
> Menu offerings can change. Michigan Dining notes that in-hall signage is the most up-to-date source.

## Raw JSON endpoint

Use the latest published menu directly:

```text
https://raw.githubusercontent.com/MuERsese/bursley-menu/main/menu.json
```

Example:

```bash
curl -s https://raw.githubusercontent.com/MuERsese/bursley-menu/main/menu.json
```

Python:

```python
import requests

url = "https://raw.githubusercontent.com/MuERsese/bursley-menu/main/menu.json"
menu = requests.get(url, timeout=10).json()

print(menu["captured_at"])
print(menu["meals"].get("Dinner", {}))
```

## What is included

`menu.json` currently contains:

- Source URL and capture timestamp
- Breakfast / Brunch / Lunch / Dinner sections when offered
- Bursley dining-station assignment
- Dish name
- Dietary and sustainability tags such as:
  - Gluten Free
  - Halal
  - Vegetarian / Vegan
  - Nutrient Dense
  - Carbon Footprint
- Nutrition Facts when available:
  - Serving size
  - Calories
  - Total fat / saturated fat / trans fat
  - Cholesterol
  - Sodium
  - Total carbohydrate
  - Dietary fiber
  - Sugars
  - Protein
- Common allergen information extracted from the item detail panel
- Raw Nutrition Facts text for auditing/debugging

Nutrition values are approximations supplied by Michigan Dining and may change because of recipe substitutions, product formulation, or portion size.

## Bursley stations

Bursley describes itself as eight mini-restaurants:

| Station | Focus |
| --- | --- |
| `Signature` | Chef specials |
| `24 Carrots` | Vegan / vegetarian options |
| `Halal` | Composed Halal entrees |
| `Pizziti` | Pizza |
| `Wild Fire` | Grilled favorites |
| `Two Oceans` | Stir fry |
| `Deli` | Made-to-order sandwiches |
| `Finale` | Desserts |

## JSON structure

A simplified item looks like this:

```json
{
  "source": "https://dining.umich.edu/menus-locations/dining-halls/bursley/",
  "captured_at": "2026-08-29T17:02:35.323055-04:00",
  "meals": {
    "Dinner": {
      "Signature": [
        {
          "name": "Piri-Piri Chicken",
          "tags": [
            "Gluten Free",
            "Halal",
            "Nutrient Dense High",
            "Carbon Footprint Medium"
          ],
          "nutrition": {
            "serving_size": "3 oz Piece (92g)",
            "calories": 160,
            "total_fat_g": 11,
            "sodium_mg": 218,
            "total_carbohydrate_g": 2,
            "protein_g": 15,
            "allergens": ["Milk"]
          }
        }
      ]
    }
  }
}
```

The real file contains additional nutrition fields and a `_debug` section used to validate parsing and station assignment.

## How the data is produced

The current updater runs separately from this data-only repository:

```text
Michigan Dining Bursley page
        ↓
Playwright-based scraper
        ↓
meal + station classification
        ↓
Nutrition Facts / allergen parsing
        ↓
menu.json
        ↓
Git commit + push
```

The current deployment is scheduled to refresh automatically with a **systemd user timer**. The public repository intentionally keeps the consumer-facing artifact (`menu.json`) small and simple; the scraper/update scripts are currently maintained outside this repository.

The `captured_at` field is written in the `America/Detroit` timezone so consumers can determine how fresh the snapshot is.

## Station assignment notes

The Michigan Dining page does not expose every station in exactly the same DOM structure.

To avoid confidently assigning a dish to the wrong station, the parser uses direct station containers whenever possible and conservative fallbacks otherwise.

- `24 Carrots`, `Halal`, `Pizziti`, and `Deli` are generally mapped from explicit station containers.
- Some `Signature`, `Wild Fire`, `Two Oceans`, and `Finale` assignments may require position/keyword inference.
- Breakfast may contain an `Unresolved` group when the page does not expose enough station structure to assign those items safely.

## Nutrition handling

Nutrition data is parsed per dish from the Nutrition Facts panel embedded in the Michigan Dining page.

Special case:

```json
{
  "name": "Sandwiches Made to Order",
  "nutrition": null,
  "nutrition_note": "Nutrition varies by custom sandwich ingredients and portions."
}
```

A made-to-order sandwich does not have one meaningful fixed nutrition value because the result depends on the selected bread, protein, cheese, toppings, sauces, and portion sizes.

## Known limitations

- **Dining-hall signage wins.** The website itself states that offerings are subject to change.
- **Salad bar, fruit, beverages, and other self-serve staples are not guaranteed to appear in `menu.json`.** The file primarily reflects items exposed by the online menu.
- **Made-to-order items may not have fixed Nutrition Facts.**
- **Station inference is intentionally conservative.** Some dishes can remain `Unresolved` rather than being assigned incorrectly.
- **Nutrition is approximate.** Values come from Michigan Dining and may differ from the food actually served.
- This project is an unofficial personal data utility and is **not affiliated with or endorsed by the University of Michigan or Michigan Dining**.

## Typical use cases

This repository is useful for things like:

- Answering “What should I eat at Bursley tonight?” using the actual current menu
- Comparing entrees by calories, protein, carbs, or fat
- Building meal-planning or nutrition tools
- Filtering dishes by dietary tags or allergens
- Feeding a current Bursley menu into an AI assistant or personal automation

## License / data ownership

The repository contains a transformed snapshot of publicly presented Michigan Dining menu information. University of Michigan / Michigan Dining retain ownership of their underlying menu, branding, and nutrition information.
