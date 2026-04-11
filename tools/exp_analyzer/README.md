# Experiment Analyzer

A standalone post-mortem analysis tool that ingests experiment logs of any format,
extracts discrete records, discovers recurring patterns across them, and produces a
verdict on what worked and what didn't — using an LLM.

Inspired by [CLEAR (IBM)](https://github.com/IBM/CLEAR)'s approach of surfacing
recurring shortcomings from LLM evaluation outputs.

---

## Use Case

When running iterative experiments — such as evolving routing algorithms, tuning
hyperparameters, or optimizing LLM prompts — you accumulate logs, scratchpads,
and metric files across many iterations. After the experiment ends, it is hard to
answer questions like:

- What decisions or strategies kept recurring across iterations?
- Which patterns led to improvement vs. regression?
- What did the optimizer or LLM keep getting stuck on?
- Which suggestions were ignored and what was the consequence?

The Experiment Analyzer reads all of your experiment files, uses an LLM to extract
discrete records (iterations, decisions, observations), synthesizes recurring patterns
in batches (to handle large record sets without timeouts), and generates a structured
verdict report.

### Example: vLLM routing algorithm evolution (EXP22)

A 51-iteration experiment evolving a vLLM request routing algorithm produced a 536KB
scratchpad file containing LLM reasoning, observations `[OBS]`, conclusions `[CON]`,
suggestions `[SUG]`, and counterfactual feedback `[CF]` per iteration.

Running the analyzer on that file produced:

- **964 records** extracted from the scratchpad
- **20 recurring patterns** discovered across 7 batches, e.g.:
  - `agent_code_generation_limitations` — 50+ occurrences
  - `session_cache_locality_tradeoff` — 20+ occurrences
  - `budget_aware_complexity` — 5 occurrences
- A **verdict** with 6 "what works" findings and 8 "what doesn't work" findings
- A full `report.md` (including model name and analysis time), `verdict.json`,
  `shortcoming_list.json`, `per_record_analysis.csv`, and `mapping_results.csv`

---

## Supported Input Formats

The tool accepts any combination of files or directories:

| Format | Extensions |
|--------|------------|
| Markdown | `.md` |
| Plain text / console logs | `.txt`, `.log` |
| Structured data | `.json`, `.csv` |
| Directory | walks all supported files recursively |

No assumptions are made about structure — the LLM interprets the content.

---

## Output Files

All written to `--output-dir` (default: `./exp_analysis_output/`):

| File | Description |
|------|-------------|
| `report.md` | Human-readable report: verdict, pattern taxonomy, per-record summary table. Includes model name and total analysis time. |
| `verdict.json` | Structured what-works / what-doesn't-work findings with evidence and confidence |
| `records.json` | All extracted records with id, summary, outcome, decisions, observations |
| `shortcoming_list.json` | All discovered patterns with name, description, occurrence count, and list of record IDs |
| `per_record_analysis.csv` | One row per record: id, source, summary, outcome, matched patterns |
| `mapping_results.csv` | Record × pattern matrix (0/1 columns) |

---

## Installation

No extra dependencies beyond what skydiscover already installs (`httpx` is included
as a base dependency).

```bash
cd /path/to/skydiscover
uv sync
```

Set `OPENAI_API_KEY` in your environment (or pass `--api-key`) for endpoints that
require authentication.

---

## Usage

Run from the skydiscover root directory:

```bash
python -m tools.exp_analyzer <path> [<path> ...] [options]
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--model`, `-m` | `gemini-2.5-flash` | LLM model name |
| `--endpoint-url` | `https://ete-litellm.ai-models.vpc-int.res.ibm.com` | LLM endpoint base URL (auto-appends `/v1`) |
| `--api-key` | `$OPENAI_API_KEY` | LLM API key |
| `--output-dir`, `-o` | `./exp_analysis_output` | Where to write output files |
| `--chunk-size` | `12000` | Max characters per chunk for large files |
| `--verbose`, `-v` | off | Enable debug logging |

---

## Examples

### Enterprise litellm proxy (default)

```bash
python -m tools.exp_analyzer experiment_scratchpad.md \
  --output-dir ./analysis_output/
```

### Explicit endpoint and model

```bash
python -m tools.exp_analyzer experiment_scratchpad.md \
  --model gemini-2.5-flash \
  --endpoint-url https://ete-litellm.ai-models.vpc-int.res.ibm.com \
  --output-dir ./analysis_output/
```

### Local Ollama

```bash
python -m tools.exp_analyzer experiment_scratchpad.md \
  --model qwen2.5:14b \
  --endpoint-url http://localhost:11434 \
  --output-dir ./analysis_output/
```

### Multiple files of different types

```bash
python -m tools.exp_analyzer run.log metrics.csv notes.md \
  --output-dir ./analysis_output/
```

### Entire experiment directory

```bash
python -m tools.exp_analyzer /path/to/experiment_outputs/ \
  --output-dir ./analysis_output/
```

---

## Pipeline

The tool runs in four stages:

```
INPUT FILES
    │
    ▼
[Stage 1: Ingest]
  Read all files, chunk large ones into ~12,000 char windows
    │
    ▼
[Stage 2: Extract Records]        — 1 LLM call per chunk
  LLM identifies discrete records: iterations, decisions, runs, observations
  Returns: id, summary, outcome, key_decisions, notable_observations
    │
    ▼
[Stage 3: Discover Patterns]      — 1 LLM call per batch + 1 consolidation call
  Records split into batches of 150 (~10-13k tokens each)
  LLM finds recurring patterns (≥2 occurrences) per batch
  Results merged by name, then a consolidation pass deduplicates near-synonyms
  Returns: name, description, list of record IDs — sorted by occurrence count
    │
    ▼
[Stage 4: Generate Verdict]       — 1 LLM call
  LLM synthesizes what worked and what didn't across all records and patterns
  Returns: overall_assessment, what_works[], what_doesnt_work[] with evidence
    │
    ▼
OUTPUT FILES
  report.md includes model name and total analysis time
```

---

## LLM Client

The tool uses a direct HTTP client (no SDK) that:
- Posts to `{endpoint_url}/v1/chat/completions`
- Auto-appends `/v1` if not already present in the endpoint URL
- Authenticates via `Authorization: Bearer <OPENAI_API_KEY>` when the key is set
- Works with any OpenAI-compatible endpoint (litellm proxy, Ollama, vLLM, etc.)

---

## Model Recommendations

| Model | Quality | Notes |
|-------|---------|-------|
| `gemini-2.5-flash` | High | Default; fast and strong JSON compliance |
| `qwen2.5:7b` (Ollama) | Medium | Works offline; patterns are generic |
| `qwen2.5:14b` (Ollama) | Good | Better pattern specificity; slower |
| `claude-sonnet-4-6` | Best | Most domain-specific patterns |

For large experiment files (>100KB), a stronger model will produce significantly
more actionable patterns.

---

## Tips

- **Large files**: The tool automatically chunks files that exceed `--chunk-size`.
  For a 536KB scratchpad, expect ~47 chunks and ~15 minutes with `gemini-2.5-flash`.
- **Batched synthesis**: Pattern discovery splits records into batches of 150 to
  avoid prompt-size timeouts on large experiments. Each batch is ~10k tokens.
- **Multiple experiments**: Pass multiple files or a directory to compare patterns
  across experiments.
- **Chunk size**: Reduce `--chunk-size` if the model struggles with long contexts;
  increase it to reduce the number of LLM calls on fast/large models.
- **Pattern quality**: If patterns are too generic, switch to a larger model or
  use `--verbose` to inspect what records were extracted.
