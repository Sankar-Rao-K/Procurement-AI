
import pandas as pd
from pathlib import Path

# Locate the data folder
DATA_DIR = Path(".")

print("=" * 50)
print("THE PROCUREMENT DESK - DATA INSPECTION")
print("=" * 50)

# Check whether the data folder exists
if not DATA_DIR.exists():
    print("ERROR: 'data' folder not found!")
    print("Please create a data folder and place your CSV files inside it.")
    raise SystemExit

# List available files
print("\nFiles found in data folder:")
for file in DATA_DIR.iterdir():
    print("-", file.name)

# Load the main dataset
threads_file = DATA_DIR / "threads.csv"

if not threads_file.exists():
    print("\nERROR: threads.csv not found inside data folder.")
    raise SystemExit

threads = pd.read_csv(threads_file)

print("\nMAIN DATASET OVERVIEW")
print("-" * 50)

print("Total negotiation threads:", len(threads))
print("Total columns:", len(threads.columns))

print("\nColumn names:")
print(threads.columns.tolist())

print("\nData types:")
print(threads.dtypes)

print("\nMissing values:")
print(threads.isnull().sum())

print("\nFirst 5 rows:")
print(threads.head().to_string())

print("\nDATA INSPECTION COMPLETE!")
