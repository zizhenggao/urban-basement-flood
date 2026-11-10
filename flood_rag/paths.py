from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "raw"
OUTPUT = ROOT / "outputs"

SEWER = ROOT / "sewer" / "ward_sewer_features_panel_2019_2023.csv"
REQUESTS_311 = (
    ROOT
    / "311 service request"
    / "2019_2022_25ward_311_service_request_info.txt"
)
TREES = ROOT / "trees_data" / "trees_by_ward25_2019_2022_with_sewer.xlsx"
WATER_DIR = ROOT / "Water billing"
FLOODS = DATA / "basement-flooding-by-ward.xlsx"
POLICY_DIR = ROOT / "policy data"
SUMMARY_PDF_NAME = "Basement Flooding Protection Program Summary .pdf"
