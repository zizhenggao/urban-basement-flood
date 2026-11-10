# Ward sewage-risk index (local)

The ranking is a small transparent score on the ward tables. A language model is not in that path. The three Basement Flooding Protection Program PDFs are searched with TF-IDF, which runs on CPU and does not download a model. A tiny local model (Ollama) is optional and only writes a paragraph from the pages that search already found.

## What the score is

For each of the 25 wards:

- **Sewage-failure risk** mixes older and combined pipe, foundation-drain density, tree roots over pipe, residential water use, and 311 sewer-backup / manhole-overflow rates per 1,000 eligible homes.
- **Flood reporting** is basement-flood service requests per 1,000 eligible homes, 2019–2022.
- The script prints four lists: highest failure pressure, lowest flood reporting, the overlap of those two top 10s, and subsidy participation. A single blended rank is also stored (`gap_rank` is the sum of the two ranks) so a ward that is only extreme on one side is not described as both.

Eligible homes are the PDF's "with device" plus "without device" counts (the subsidy universe: single-family, duplex, triplex).

The 2025 column uses the 2023 sewer snapshot, adds two years of pipe age, and gives a small credit to wards that installed more new pipe in 2019–2023. Complaint rates stay at the 2019–2021 average. It is a structural update, not a storm forecast.

## Run

```bash
python3 -m flood_rag.run
python3 -m flood_rag.run ask "Which wards should we outreach because sewer backups are high, few residents report basement floods, and few homes already have a subsidized device?"
```

Outputs land in `outputs/ward_index.csv`.

`ask` uses that index to choose the wards, then searches the PDFs for program rules and study-area pages for those wards. The printed list is the decision. Rank 1 is the strongest outreach case. A question that names a ward or a place such as Scarborough keeps those wards in the list. Saying "2025" uses the structural update for the sewage-failure side.

To let a local model narrate that list and the retrieved pages (about 1 GB, CPU):

```bash
# install from https://ollama.com then:
ollama pull qwen2.5:1.5b
python3 -m flood_rag.run ask "Why might Scarborough wards show low subsidy intake?" --model qwen2.5:1.5b
```

`llama3.2:1b` is the other cheap option. Do not send the ward tables to a paid API; the CSV already has the ranking.

## Data used

| Piece | File |
|---|---|
| Sewer features, 25 wards, 2019–2023 | `sewer/ward_sewer_features_panel_2019_2023.csv` |
| 311 sewage-related calls | `311 service request/2019_2022_25ward_311_service_request_info.txt` |
| Trees and distance to gravity mains | `trees_data/trees_by_ward25_2019_2022_with_sewer.xlsx` |
| Residential water use | `Water billing/Water_Consumption_2019.xlsx` … `2022` |
| Basement flood reports and subsidy approvals | `data/raw/basement-flooding-by-ward.xlsx` (Toronto Open Data) |
| Ward profile summaries, June 2025 subsidy stock | `policy data/Basement Flooding Protection Program Summary .pdf` |

The 44-ward sewer panel is not mixed into this score. Those polygons are a different geography.

## Not in this first cut

Ward-profile census fields (low-rise counts from the Open Data ward profiles) are not in the folder yet. The PDF eligible-home counts stand in for that denominator. Low-rise density from the ward-profile dataset would be a better exposure measure once that file is added.
