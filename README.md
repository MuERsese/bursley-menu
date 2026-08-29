# Bursley Menu Scraper

A small scraper and data mirror for the **University of Michigan Bursley Dining Hall** menu.

It uses Playwright/Chromium to read the official Michigan Dining page, classifies dishes by Bursley station, extracts per-item Nutrition Facts and allergens when available, writes the result to [`menu.json`](./menu.json), and can automatically commit/push refreshed data back to this repository.

> Official source: https://dining.umich.edu/menus-locations/dining-halls/bursley/
>
> Michigan Dining notes that menu offerings can change and in-hall signage is the most up-to-date source.

## Repository layout

```text
.
├── README.md
├── fetch_bursley.py
├── install.sh
├── menu.json
├── requirements.txt
├── sync_menu.sh
└── systemd/
    ├── bursley-menu.service.example
    └── bursley-menu.timer
```

### Files

- `fetch_bursley.py` — opens the Bursley menu page, parses dishes/stations/tags/Nutrition Facts, and writes `menu.json`.
- `menu.json` — latest published machine-readable menu snapshot.
- `sync_menu.sh` — runs the scraper, commits `menu.json`, and pushes the update to the current Git branch.
- `install.sh` — installs Python/Playwright/Chromium dependencies and installs the user-level systemd service/timer.
- `requirements.txt` — Python dependency list.
- `systemd/bursley-menu.timer` — automatic refresh schedule.
- `systemd/bursley-menu.service.example` — example service definition; `install.sh` generates a service with the clone's real absolute path.

## Raw JSON endpoint

The latest data can be consumed directly from:

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

## What is captured

`menu.json` includes, when exposed by Michigan Dining:

- capture timestamp in the `America/Detroit` timezone
- Breakfast / Brunch / Lunch / Dinner sections
- Bursley station assignment
- dish name
- dietary and sustainability tags
- serving size
- calories
- total / saturated / trans fat
- cholesterol
- sodium
- carbohydrates
- dietary fiber
- sugars
- protein
- common allergens
- raw Nutrition Facts text for debugging/auditing

The file also includes a `_debug` section with parser counts and station-assignment metadata.

## Bursley stations

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

## Setup on Ubuntu/Linux

Clone the repository:

```bash
git clone https://github.com/MuERsese/bursley-menu.git
cd bursley-menu
```

Install dependencies:

```bash
chmod +x install.sh sync_menu.sh fetch_bursley.py
./install.sh
```

`install.sh` installs:

- `python3-venv`
- `git`
- GitHub CLI (`gh`)
- Playwright
- Chromium and its required system dependencies

Authenticate GitHub so automatic pushes can work:

```bash
gh auth login
```

Choose GitHub.com and authenticate the clone/remote in the way you normally use Git.

## Run manually

Run only the scraper:

```bash
.venv/bin/python fetch_bursley.py
```

This updates:

```text
menu.json
```

Run the complete scrape + commit + push flow:

```bash
./sync_menu.sh
```

## Automatic updates with systemd

`install.sh` installs a user service and timer under:

```text
~/.config/systemd/user/
```

Enable the timer:

```bash
systemctl --user enable --now bursley-menu.timer
```

The supplied timer runs hourly at approximately `:05`, from 07:00 through 20:00, with up to 120 seconds of randomized delay.

Check the timer:

```bash
systemctl --user list-timers bursley-menu.timer
```

Check the service:

```bash
systemctl --user status bursley-menu.service
```

View recent logs:

```bash
journalctl --user -u bursley-menu.service -n 100 --no-pager
```

To allow the user timer to continue running after logout, if desired:

```bash
sudo loginctl enable-linger "$USER"
```

## JSON example

A simplified item looks like:

```json
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
    "total_sugars_g": 1,
    "protein_g": 15,
    "allergens": ["Milk"]
  }
}
```

## Nutrition handling

The scraper first looks for Nutrition Facts already embedded in the item's nearby DOM. If that is not sufficient, it can fall back to interacting with the dish entry and reading the visible nutrition panel.

Some Michigan Dining containers include multiple adjacent dishes, so the parser isolates the current dish's Nutrition Facts panel before parsing values. This prevents an adjacent dish's calories/macros from being assigned to the wrong menu item.

Made-to-order Deli sandwiches are treated specially:

```json
{
  "name": "Sandwiches Made to Order",
  "nutrition": null,
  "nutrition_note": "Nutrition varies by custom sandwich ingredients and portions."
}
```

A custom sandwich does not have a meaningful single fixed nutrition value because it depends on the selected bread, protein, cheese, toppings, sauces, and portions.

## Station assignment

The Michigan Dining page does not expose all eight Bursley stations in exactly the same DOM structure.

The parser therefore uses:

1. direct station containers whenever they are available;
2. conservative positional inference for some sections;
3. limited station-specific keyword inference for `Wild Fire` and `Two Oceans`;
4. `Unresolved` instead of guessing when there is not enough evidence.

`24 Carrots`, `Halal`, `Pizziti`, and `Deli` are generally available as explicit station containers. Some `Signature`, `Wild Fire`, `Two Oceans`, and `Finale` assignments rely on conservative fallbacks.

## Known limitations

- **Dining-hall signage wins.** Online offerings can change.
- **Salad bar, fruit, beverages, and other self-serve staples are not guaranteed to appear in `menu.json`.**
- **Made-to-order items may not have fixed nutrition values.**
- **Station assignment is intentionally conservative.** Some items can remain `Unresolved` rather than being assigned incorrectly.
- **Nutrition values are approximate.** Michigan Dining notes that recipes, substitutions, product formulations, and actual portion size can change the values.
- The scraper depends on the current Michigan Dining page/DOM and may require updates if the site changes.
- This is an unofficial personal utility and is not affiliated with or endorsed by the University of Michigan or Michigan Dining.

## Data flow

```text
Michigan Dining Bursley page
        ↓
Playwright + Chromium
        ↓
meal / dish extraction
        ↓
station classification
        ↓
Nutrition Facts + allergens
        ↓
menu.json
        ↓
sync_menu.sh
        ↓
Git commit + push
```
