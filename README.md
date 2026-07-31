# doc-translator

Translates a Japanese folder (subfolders, file names, and file contents) into English, preserving the original folder structure and file formats.

Supports: **PDF, Excel (.xlsx), Word (.docx), CSV, TXT, Markdown**

---

## What It Does

Given a folder of Japanese documents, it produces a mirror English folder:

```
日本語文書/                          ->   日本語文書_english/
├── 人事部/                               ├── HR_Department/
│   └── 採用資料/                         │   └── Recruitment_Materials/
│       └── 求人票.txt                    │       └── Job_Posting.txt
├── 製品情報/                              ├── Product_Information/
│   └── 製品概要.txt                      │   └── Product_Overview.txt
└── 報告書.pdf                            └── Report.pdf
```

- Folder names: translated to English
- File names: translated to English
- File contents: translated to English (formatting preserved)
- Cost is estimated before any API calls are made, you confirm before spending

---

## How Translation Works

All Japanese strings are batched and sent to Claude via AWS Bedrock using **structured output** (Pydantic schema enforced JSON). Each API call returns a guaranteed-valid JSON array of `{index, translation}` pairs with no parsing fragility.

- **Dynamic chunk sizing**: chunks are sized by estimated output token budget (6000 tokens), not a fixed string count. Short strings pack more per chunk; long strings get fewer. Hard cap of 80 strings per chunk for reliability.
- **Index-based matching**: Claude returns a numbered index for each translation, mapped back to the original string by position. No key matching or character normalization needed, works correctly regardless of Unicode variants.
- **Automatic retry**: if any index is missing from a chunk response after 3 attempts, those strings are retried individually. No string is ever left untranslated.
- **Deduplication**: identical strings across a file are translated once and reused everywhere.

---

## Project Structure

```
doc-translator/
├── main.py                  <- entry point (run this)
├── requirements.txt
├── notes.md                 <- implementation notes and TODOs
├── .env                     <- your AWS credentials (not committed)
├── .env.example             <- template
│
└── translator/
    ├── client.py            <- AnthropicBedrock SDK client, token tracking, structured output
    ├── common.py            <- batch translation, chunk sizing, Japanese detection, XML helpers
    ├── estimator.py         <- cost estimation (no API calls)
    ├── pipeline.py          <- folder walking + file routing
    └── handlers/
        ├── txt.py           <- .txt, .md, .csv
        ├── docx.py          <- .docx
        ├── xlsx.py          <- .xlsx (cells, drawings, sheet tabs)
        └── pdf.py           <- .pdf
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

> If you already have AWS configured via `aws configure`, leave the key lines blank. The tool will use your AWS profile automatically.

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
D:\Documents\japanese_docs  ->  D:\Documents\japanese_docs_english
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
  Est. input tokens         :     45,355
  Est. output tokens        :     21,929

  Estimated total cost      :  $0.4650  (~$0.6045 with overhead)

  Proceed with translation? (y/n):
```

Actual cost is printed at the end. Estimates are typically within 15% of actual.

Multipliers calibrated from real runs:
- Input: `1.9 x JP chars` (includes prompt overhead, numbered list format)
- Output: `1.0 x JP chars` (English translation only, no JP keys repeated)

---

## Supported File Types

| Format | What gets translated |
|--------|---------------------|
| `.xlsx` | Cell text, drawing shapes, sheet tab names |
| `.pdf` | All text, replaced in-place (layout preserved) |
| `.docx` | Paragraphs and table cells |
| `.csv` | All cell values |
| `.txt` | Full file content |
| `.md` | Full file content |
| Other | Copied as-is |

---

## AWS Bedrock Setup (First Time)

1. Log in to [AWS Console](https://console.aws.amazon.com)
2. Go to **Amazon Bedrock** > **Model access**
3. Enable **Anthropic Claude** models
4. Create an IAM user with `AmazonBedrockFullAccess` policy
5. Generate Access Key + Secret Key and paste into `.env`

---

## Troubleshooting

**`UnrecognizedClientException`**
AWS credentials in `.env` are incorrect or expired.

**`ModuleNotFoundError`**
Run `pip install -r requirements.txt` inside your virtual environment.

**PDF pages come out blank**
The PDF may be image-only (scanned). Only text-based PDFs are supported.

**Excel opens with repair warning**
Close the file in Excel before re-running. If it persists, check for the `.tmp.xlsx` leftover and delete it.

---

## Security

- **Never commit `.env`** - it contains your AWS credentials. Already in `.gitignore`.
- Share `.env.example` instead.
