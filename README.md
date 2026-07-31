# doc-translator

Translates a Japanese folder (subfolders, file names, and file contents) into English — preserving the original folder structure and file formats.

Supports: **PDF, Excel (.xlsx), Word (.docx), CSV, TXT, Markdown**

---

## What It Does

Given a folder of Japanese documents, it produces a mirror English folder:

```
日本語文書/                          →    日本語文書_english/
├── 人事部/                               ├── HR_Department/
│   └── 採用資料/                         │   └── Recruitment_Materials/
│       └── 求人票.txt                    │       └── Job_Posting.txt
├── 製品情報/                              ├── Product_Information/
│   └── 製品概要.txt                      │   └── Product_Overview.txt
└── 報告書.pdf                            └── Report.pdf
```

- Folder names → translated to English
- File names → translated to English
- File contents → translated to English (formatting preserved)
- Cost is estimated before any API calls are made — you confirm before spending
- All file types use batch translation with structured output — strings are deduplicated, chunked, validated, and retried automatically

---

## How Translation Works

All content handlers (pdf, docx, csv, txt, xlsx) use the same `batch_translate()` pipeline:

1. **Collect** — extract all unique Japanese strings from the file
2. **Chunk** — split into groups sized by output token budget (≤6000 tokens, ≤80 strings per chunk)
3. **Translate** — send each chunk to Claude with a structured output schema (`{index, translation}` pairs)
4. **Validate** — verify every index is returned; retry missing entries up to 3 times
5. **Fall back** — if a chunk still has gaps, retry missing strings individually
6. **Apply** — map translations back to the original document structure

Index-based structured output (`{index, translation}`) avoids Unicode normalization mismatches that break key-matching approaches.

---

## Project Structure

```
doc-translator/
├── main.py                  ← entry point (run this)
├── requirements.txt
├── .env                     ← your AWS credentials (not committed)
├── .env.example             ← template
│
└── translator/
    ├── client.py            ← AnthropicBedrock SDK client + token tracking
    ├── common.py            ← batch_translate(), chunking, structured output, helpers
    ├── estimator.py         ← cost estimation (no API calls)
    ├── pipeline.py          ← folder walking + file routing
    └── handlers/
        ├── txt.py           ← .txt, .md, .csv
        ├── docx.py          ← .docx
        ├── xlsx.py          ← .xlsx
        └── pdf.py           ← .pdf (text replaced in-place, layout preserved)
```

---

## Requirements

- Python 3.10+
- AWS account with Bedrock access (Claude enabled in `us-east-1`)

---

## Setup

### 1. Clone / download the project

```bash
git clone <repo-url>
cd doc-translator
```

### 2. Create a virtual environment

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure AWS credentials

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Open `.env` and fill in your credentials:

```env
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-6
```

> If you already have AWS configured via `aws configure`, leave the key fields blank — the tool will use your AWS profile automatically.

---

## Usage

```bash
# Windows (always use -X utf8 for Japanese paths)
python -X utf8 main.py "D:\Documents\japanese_docs"

# macOS / Linux
python main.py "/Users/rayhan/Desktop/japanese_docs"
```

Output is created **next to the input**, named `<folder>_english`:
```
D:\Documents\japanese_docs  →  D:\Documents\japanese_docs_english
```

### Single file mode

```bash
python -X utf8 main.py "D:\Documents\report.xlsx"
```

### Options

| Flag | Description |
|------|-------------|
| `--pages N` | Only translate first N pages of each PDF (useful for testing) |

---

## Cost Estimation

Before any translation starts, the tool scans all files and shows a cost estimate:

```
  File                          Type    JP chars
  ----------------------------- ------  --------
  業務フロー.xlsx               .xlsx     21,029

  Total Japanese characters :     21,029
  Name translation calls    :         18
  Est. input tokens         :     29,441
  Est. output tokens        :     14,300

  Input cost  ($3.00/M tokens) : $0.0883
  Output cost ($15.00/M tokens) : $0.2145
  ─────────────────────────────────────────
  Estimated total cost      :  $0.3028  (~$0.3937 with overhead)

  Proceed with translation? (y/n):
```

Actual cost is printed at the end for comparison. Estimates are typically within ±15% of actual.

---

## Supported File Types

| Format | What gets translated |
|--------|---------------------|
| `.xlsx` | Cell text, drawing shapes, sheet tab names |
| `.pdf` | All text, replaced in-place (layout preserved) |
| `.docx` | Paragraphs and table cells |
| `.csv` | All cell values |
| `.txt` | Full file content (line by line) |
| `.md` | Full file content (line by line) |
| Other | Copied as-is |

---

## AWS Bedrock Setup (First Time)

1. Log in to [AWS Console](https://console.aws.amazon.com)
2. Go to **Amazon Bedrock** → **Model access**
3. Enable **Anthropic Claude** models
4. Create an IAM user with `AmazonBedrockFullAccess` policy
5. Generate Access Key + Secret Key and paste into `.env`

---

## Troubleshooting

**`UnrecognizedClientException`**
→ AWS credentials in `.env` are incorrect or expired.

**`ModuleNotFoundError`**
→ Run `pip install -r requirements.txt` inside your virtual environment.

**PDF pages come out blank**
→ The PDF may be image-only (scanned). Only text-based PDFs are supported.

**Excel opens with repair warning**
→ Close the file in Excel before re-running. If it persists, check for the `.tmp.xlsx` leftover and delete it.

---

## Security

- **Never commit `.env`** — it contains your AWS credentials. Already in `.gitignore`.
- Share `.env.example` instead.
