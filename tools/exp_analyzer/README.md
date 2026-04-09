# Experiment Analyzer

A standalone post-mortem analysis tool that ingests experiment logs of any format,
extracts discrete records, and discovers recurring patterns across them using an LLM.

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
discrete records (iterations, decisions, observations), then synthesizes all recurring
patterns with their occurrence counts — giving you a structured post-mortem report.

### Example: vLLM routing algorithm evolution (EXP22)

A 51-iteration experiment evolving a vLLM request routing algorithm produced a 536KB
scratchpad file containing LLM reasoning, observations `[OBS]`, conclusions `[CON]`,
suggestions `[SUG]`, and counterfactual feedback `[CF]` per iteration.

Running the analyzer on that file produced:

- **627 records** extracted from the scratchpad
- **8 recurring patterns** discovered, e.g.:
  - `Run iterations at specific trial counts` — 17 occurrences
  - `Set canary thresholds for specific metrics` — 4 occurrences
  - `Try different algorithm classes or structures` — 3 occurrences
- A full `report.md`, `shortcoming_list.json`, `per_record_analysis.csv`,
  and `mapping_results.csv`

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
| `records.json` | All extracted records with id, summary, outcome, decisions, observations |
| `shortcoming_list.json` | All discovered patterns with name, description, occurrence count, and list of record IDs |
| `per_record_analysis.csv` | One row per record: id, source, summary, outcome, matched patterns |
| `mapping_results.csv` | Record × pattern matrix (0/1 columns) |
| `report.md` | Human-readable report: pattern taxonomy + per-record summary table |

---

## Installation

No extra dependencies beyond what skydiscover already installs (`openai` is included).

```bash
cd /path/to/skydiscover
uv sync
```

---

## Usage

Run from the skydiscover root directory:

```bash
python -m tools.exp_analyzer <path> [<path> ...] [options]
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--model`, `-m` | `qwen2.5:7b` | LLM model name |
| `--api-base` | `http://localhost:11434/v1` | LLM API base URL |
| `--api-key` | `$OPENAI_API_KEY` or `dummy` | LLM API key |
| `--output-dir`, `-o` | `./exp_analysis_output` | Where to write output files |
| `--chunk-size` | `12000` | Max characters per chunk for large files |
| `--verbose`, `-v` | off | Enable debug logging |

---

## Examples

### Local Ollama (default)

```bash
python -m tools.exp_analyzer experiment_scratchpad.md \
  --output-dir ./analysis_output/
```

### Local Ollama with explicit model

```bash
python -m tools.exp_analyzer ./experiment_dir/ \
  --model qwen2.5:7b \
  --api-base http://localhost:11434/v1 \
  --output-dir ./analysis_output/
```

### Multiple files of different types

```bash
python -m tools.exp_analyzer run.log metrics.csv notes.md \
  --output-dir ./analysis_output/
```

### Claude API (best pattern quality)

```bash
python -m tools.exp_analyzer experiment_scratchpad.md \
  --model claude-sonnet-4-6 \
  --api-base https://api.anthropic.com/v1 \
  --api-key $ANTHROPIC_API_KEY \
  --output-dir ./analysis_output/
```

### Entire experiment directory

```bash
python -m tools.exp_analyzer /path/to/experiment_outputs/ \
  --model qwen2.5:14b \
  --api-base http://localhost:11434/v1 \
  --output-dir ./analysis_output/
```

---

## Pipeline

The tool runs in three stages:

```
INPUT FILES
    │
    ▼
[Stage 1: Ingest]
  Read all files, chunk large ones into ~12,000 char windows
    │
    ▼
[Stage 2: Extract Records]   — 1 LLM call per chunk
  LLM identifies discrete records: iterations, decisions, runs, observations
  Returns: id, summary, outcome, key_decisions, notable_observations
    │
    ▼
[Stage 3: Discover Patterns]  — 1 LLM call for all records
  LLM finds ALL recurring patterns (≥2 occurrences), names them in snake_case
  Returns: name, description, list of record IDs
  Sorted by occurrence count descending
    │
    ▼
OUTPUT FILES
```

---

## Model Recommendations

| Model | Quality | Speed | Notes |
|-------|---------|-------|-------|
| `qwen2.5:0.5b` | Low | Fast | Too small — poor JSON compliance |
| `qwen2.5:7b` | Medium | ~15 min for large files | Works, patterns are generic |
| `qwen2.5:14b` | Good | ~30 min for large files | Better pattern specificity |
| `claude-sonnet-4-6` | Best | Fast | Most domain-specific patterns |

For large experiment files (>100KB), a stronger model will produce significantly
more actionable patterns. The `qwen2.5:7b` model tends to discover surface-level
patterns; `claude-sonnet-4-6` will identify deeper strategic insights.

---

## Tips

- **Large files**: The tool automatically chunks files that exceed `--chunk-size`.
  For a 536KB scratchpad, expect ~47 chunks and ~15 minutes with `qwen2.5:7b`.
- **Multiple experiments**: Pass multiple files or a directory to compare patterns
  across experiments.
- **Chunk size**: Reduce `--chunk-size` if the model struggles with long contexts;
  increase it to reduce the number of LLM calls on fast/large models.
- **Pattern quality**: If patterns are too generic, switch to a larger model or
  add a `--verbose` flag to inspect what records were extracted.
