"""The flooding-request summary the web page draws its charts from.

Two parts: the counting function on a tiny frame, and the JSON saved in
web/public against the numbers in the 311 dashboard notebook.
"""

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "311 service request" / "Dashboard"
JSON_PATH = ROOT / "web" / "public" / "flood_requests.json"


@pytest.fixture(scope="module")
def builder():
    spec = importlib.util.spec_from_file_location(
        "build_flood_requests_json", DASHBOARD / "build_flood_requests_json.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def payload():
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


def _request(date, ward, kind, season):
    return {
        "Creation Date": date,
        "Ward": ward,
        "Service Request Type": kind,
        "season": season,
    }


def test_counts_land_in_the_right_ward_year_season_and_type(builder):
    types = ["Sewer main-Backup", "Road Water Ponding"]
    frame = pd.DataFrame(
        [
            _request("2019-01-10 08:00:00", "Etobicoke North (01)", types[0], "Winter"),
            _request("2019-01-11 08:00:00", "Etobicoke North (01)", types[0], "Winter"),
            _request("2020-07-02 08:00:00", "Etobicoke North (01)", types[1], "Summer"),
            _request("2020-07-03 08:00:00", "Etobicoke Centre (02)", types[1], "Summer"),
        ]
    )
    result = builder.build_payload(frame, types)
    assert result["years"] == [2019, 2020]
    assert result["total"] == 4
    ward_1 = result["wards"]["1"]
    assert ward_1[0][0] == [2, 0]  # 2019, winter
    assert ward_1[1][2] == [0, 1]  # 2020, summer
    assert result["wards"]["2"][1][2] == [0, 1]


def test_check_rejects_a_missing_ward(builder):
    types = ["Sewer main-Backup"]
    frame = pd.DataFrame([_request("2019-01-10 08:00:00", "Etobicoke North (01)", types[0], "Winter")])
    with pytest.raises(SystemExit, match="wards 1 to 25"):
        builder.check(builder.build_payload(frame, types))


def test_json_has_the_expected_shape(payload):
    assert payload["years"] == list(range(2019, 2027))
    assert payload["seasons"] == ["Winter", "Spring", "Summer", "Fall"]
    assert len(payload["types"]) == 6
    assert sorted(int(key) for key in payload["wards"]) == list(range(1, 26))
    for table in payload["wards"].values():
        assert len(table) == 8
        for year in table:
            assert len(year) == 4
            for season in year:
                assert len(season) == 6
                assert all(isinstance(n, int) and n >= 0 for n in season)


def test_json_total_matches_the_notebook(payload):
    counted = sum(n for table in payload["wards"].values() for year in table for season in year for n in season)
    assert counted == payload["total"] == 81783


def test_ward_1_matches_the_notebook_chart(payload):
    table = payload["wards"]["1"]
    by_season = [sum(sum(year[s]) for year in table) for s in range(4)]
    by_year = [sum(sum(season) for season in year) for year in table]
    assert by_season == [604, 579, 688, 462]
    assert by_year == [436, 296, 249, 277, 256, 302, 241, 276]
