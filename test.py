import pandas as pd
from pathlib import Path

# Path to your menu CSV
MENU_CSV = Path("menu_examples/la_impact_menu.csv")

# Load CSV
try:
    df = pd.read_csv(MENU_CSV, parse_dates=["date"])
except FileNotFoundError:
    print("CSV file not found!")
    exit()
except ValueError:
    print("Check column names in CSV! Make sure 'date' exists.")
    exit()

# Show first few rows to check
print("=== CSV HEAD ===")
print(df.head(), "\n")

# Show columns
print("=== COLUMNS ===")
print(df.columns.tolist(), "\n")

# Show non-empty meals for each day
for idx, row in df.iterrows():
    print(f"Date: {row['date'].date() if not pd.isna(row['date']) else 'N/A'}")
    for meal in ["breakfast", "lunch", "snack1", "dinner", "snack2"]:
        val = row.get(meal, "")
        if pd.isna(val) or val == "":
            val = "[no data]"
        print(f"  {meal}: {val}")
    print("---")
