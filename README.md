# doc-translator

Translates a Japanese folder (subfolders, file names, and file contents) into English — preserving the original folder structure and file formats.

Supports: **PDF, Excel (.xlsx), Word (.docx), CSV, TXT, Markdown**

---

## What It Does

Given a folder of Japanese documents, it produces a mirror English folder:

```
日本語文書/                          →    日本語文書_english/             (created next to input)
├── 人事部/                               ├── HR_Department/
│   └── 採用資料/                         │   └── Recruitment_Materials/
│       └── 求人票.txt                    │       └── Job_Posting.txt        ← content translated
├── 製品情報/                              ├── Product_Information/
│   └── 製品概要.txt                      │   └── Product_Overview.txt       ← content translated
└── 報告書.pdf                            └── Report.pdf                     ← text replaced in-place
```

- Folder names → translated to English
- File names → translated to English
- File contents → translated to English (formatting preserved)
- PDF text is replaced in-place (layout, images, colors preserved)

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

Copy the example env file:

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Open `.env` and fill in your AWS credentials:

```env
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-6
```

> **Note:** If you already have AWS configured via `aws configure` (credentials in `~/.aws/credentials`), you can leave the key lines commented out — the tool will use your AWS profile automatically.

---

## Usage

```bash
python translate.py <input_folder>
```

The output folder is created automatically **next to the input folder** (same parent directory), named `<folder>_english`. No need to specify an output path.

**Windows:**
```bash
python translate.py "D:\Documents\japanese_docs"
# → output: D:\Documents\japanese_docs_english
```

**macOS / Linux:**
```bash
python translate.py "/Users/rayhan/Desktop/japanese_docs"
# → output: /Users/rayhan/Desktop/japanese_docs_english
```

The source folder name can be in Japanese:
```bash
python translate.py "/Users/rayhan/Desktop/日本語文書"
# → output: /Users/rayhan/Desktop/日本語文書_english
```

> **Windows tip:** If your folder name contains Japanese characters, run with `python -X utf8 translate.py ...` or set `PYTHONUTF8=1` in your environment.

### Options

| Flag | Description |
|---|---|
| `--pages N` | Only translate the first N pages of each PDF (useful for testing) |

**Example — test with 2 PDF pages only:**
```bash
python translate.py "D:\input\japanese_docs" --pages 2
```

---

## Supported File Types

| Format | What gets translated |
|---|---|
| `.pdf` | All text, replaced in-place (layout preserved) |
| `.xlsx` | All cell values |
| `.docx` | Paragraphs and table cells |
| `.csv` | All cell values |
| `.txt` | Full file content |
| `.md` | Full file content |
| Other | Copied as-is (no translation) |

---

## AWS Bedrock Setup (First Time)

1. Log in to [AWS Console](https://console.aws.amazon.com)
2. Go to **Amazon Bedrock** → **Model access**
3. Enable **Anthropic Claude** models
4. Create an IAM user with `AmazonBedrockFullAccess` policy
5. Generate an Access Key and Secret Key for that user
6. Paste them into your `.env` file

---

## Security

- **Never commit `.env`** — it contains your AWS credentials. It is already in `.gitignore`.
- Share `.env.example` instead (no real credentials).
- Translated output folders are also excluded from git by default.

---

## Troubleshooting

**`UnrecognizedClientException: The security token included in the request is invalid`**
→ Your AWS credentials in `.env` are incorrect or expired. Double-check `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.

**`ModuleNotFoundError`**
→ Run `pip install -r requirements.txt` inside your virtual environment.

**PDF pages come out blank**
→ The PDF may be image-only (scanned). This tool only translates text-based PDFs — scanned documents are not supported yet.

**Text in PDF looks small or cut off**
→ English text is typically longer than Japanese. The tool auto-shrinks text to fit. For very tight layouts this is expected behavior.
