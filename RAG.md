# RAG components

`ask` is five separate pieces. Each one has its own file. A change in one piece does not rewrite the others.

```text
1. Sources        score.py ranks  +  policy.py PDF pages
2. Documents      score.py passages  +  policy.py load_chunks
3. Retriever      policy.py PolicyIndex.search
4. Prompt         policy.py ollama_answer
5. Model          run.py --model   (eval judge is a second model)
```

Evaluation sits beside the loop. It calls pieces 3, 4, and 5 again, then scores them.

```text
ward tables + PDFs
    -> 1. Sources
    -> 2. Documents
    -> 3. Retriever
    -> 4. Prompt
    -> 5. Model
    -> outputs/ask_answer.txt
    -> evaluate.py scores that same path
```

## 1. Sources

The numbers the answer is allowed to use. This piece does not write prose.

| Source | File | What it contributes |
|---|---|---|
| Ward score | `flood_rag/score.py`, `build_scores` line 180 | Sewage-failure rank, flood-report rank, outreach rank, gap rank, device counts |
| Policy PDFs | `policy data/*.pdf`, read by `load_chunks` | Program rules, eligibility, study areas |

`build_scores` is arithmetic. Edit it only when rank 1 itself should change. A wording change does not belong here.

## 2. Documents

Text the retriever can match. Two writers, one index.

| Document | File | Function | Line |
|---|---|---|---|
| One plain-language passage per ward | `flood_rag/score.py` | `_ward_text` | 295 |
| Thresholds for "high", "middle", and "low" | `flood_rag/score.py` | `if failure <= 5` inside `_ward_text` | 304 |
| Outreach, sewage-failure, flood-reporting, and gap lists | `flood_rag/score.py` | `ward_passages` | 414 |
| How many wards are on a list | `flood_rag/score.py` | `limit` in `_ranking_passage` | 406 |
| One chunk per PDF page | `flood_rag/policy.py` | `load_chunks` | 130 |

Search matches words. If a question says "outreach" and the outreach list does not contain that word, the list will not come back. Put the planner's words in the gloss inside `ward_passages`. `load_chunks` drops a PDF page shorter than 80 characters.

`prepare_index` in `flood_rag/run.py` line 74 is the only place the two document sets are joined. Ward passages are appended onto the PDF chunks there.

## 3. Retriever

**File:** `flood_rag/policy.py`  
**Function:** `PolicyIndex.search`, line 150

One TF-IDF index (unigrams and bigrams, English stop words). The search then splits results so each source keeps its own top k.

| Knob | Where | Current value |
|---|---|---|
| How many hits from each source | `-k` in `flood_rag/run.py` line 111 | 4 policy pages and 4 ward passages |
| Boost when the question says `Ward 22` | `scores[i] += 1.0` in `search`, line 166 | +1.0 on that ward's passage and its PDF page |
| Keep both sources in the result | lines 167–169 | Policy rows and ward-index rows are ranked separately, then merged |

## 4. Prompt

**File to open:** `flood_rag/policy.py`  
**Function:** `ollama_answer`, the string that starts at line 219

The prompt is only the instruction. Retrieved excerpts and the question are appended after it. The model name is not in this string.

| Sentence in the prompt | What it controls |
|---|---|
| `You advise a Toronto city planner...` | Role and tone |
| `If a ward index ranking excerpt is present, name the wards in that order.` | Follow the retrieved ranking. Do not pick other wards |
| `Use individual ward excerpts only to explain the wards already named` | Ward passages explain the list. They do not replace it |
| `Use policy excerpts for what the program offers...` | PDF pages are for eligibility, subsidy rules, and study areas |
| `If an excerpt says residents rarely report basement floods, do not call those reports high.` | Do not flip a low rank into a high one |
| `If a number is not in the excerpts, say it is not in the excerpts.` | No invented counts |
| `Write in plain language.` | Planner wording |

Packing the excerpts is the lines just above the prompt:

- Line 213, `hit.text[:1600]`: characters kept from each hit.
- Lines 215–218: ranking lists first, then ward passages, then PDF pages.

There is no temperature on this call. The JSON body at line 232 sends `model`, `prompt`, and `stream` to local Ollama.

```bash
python3 -m flood_rag.run ask "Which wards should we outreach because sewer backups are high, few residents report basement floods, and few homes already have a subsidized device?"
```

## 5. Model

**File:** `flood_rag/run.py`  
The writer and the judge are different flags. `ollama_answer` only receives the name.

| Role | Flag | Line | Current default |
|---|---|---|---|
| Writes the `ask` paragraph | `--model` | 110 | `qwen2.5:1.5b` |
| Writes the answers `eval` scores | `--model` | 113 | `qwen2.5:1.5b` |
| Scores those answers | `--judge` | 114 | same as `--model` when omitted |

```bash
ollama pull llama3.2:1b
python3 -m flood_rag.run ask "Which wards should we outreach first?" --model llama3.2:1b
python3 -m flood_rag.run eval --model qwen2.5:1.5b --judge llama3.2:1b
```

`qwen2.5:1.5b` is the small CPU model already on this machine (about 1 GB). `llama3.2:1b` is the other cheap local option. A 1B–1.5B writer will follow a short prompt and still drop a rank. Pass a larger pulled model the same way when the paragraph ignores the retrieved list.

The judge settings are in `flood_rag/evaluate.py` line 118: `ChatOllama(model=judge, temperature=0, num_predict=1024)`. Temperature 0 keeps a score stable. Context recall was blank on `qwen2.5:1.5b` because that model did not return JSON RAGAS could read.

The call stays at `http://127.0.0.1:11434` in `policy.py` line 234. Do not point that URL at a paid API.

## Evaluation

**File:** `flood_rag/evaluate.py`  
This piece does not retrieve or write. It runs components 3–5 on three questions, then scores them.

| What you want different | Function | Line |
|---|---|---|
| Questions and reference answers | `eval_cases` | 47 |
| How much retrieved text the judge sees | `hit.text[:1600]` in `_samples` | 98 |
| Which scores run | `metrics=[...]` in `evaluate_rag` | 113 |

References are built from `low_intake_rank`, `failure_rank`, and `gap_rank`. Change the rank formula in component 1 and these references follow. Change only the prompt and run `python3 -m flood_rag.run eval` again. The table is `outputs/ragas_eval.csv`.

- **Context recall** — do the retrieved excerpts cover the reference?
- **Faithfulness** — does the answer stay inside those excerpts?
- **Factual correctness** — does the answer match the reference ranks?
