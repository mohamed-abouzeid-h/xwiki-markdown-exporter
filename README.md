# XWiki Markdown Exporter

A Python tool that exports XWiki pages into clean, structured Markdown files.

This script:

- Fetches spaces and pages from an XWiki instance  
- Converts HTML content into Markdown  
- Groups pages by logical sections  
- Combines related pages into a single Markdown file  
- Creates a `_All` folder containing all generated files  
- Skips system spaces like `XWiki`, `Main`, `Help`, and `Sandbox`

---

## Features

### ✔ Export XWiki pages to Markdown  
HTML is cleaned and converted using `markdownify`.

### ✔ Automatic grouping  
Pages are grouped based on their hierarchical structure.

### ✔ `_All` folder  
All generated Markdown files are copied into a single folder for convenience.

### ✔ Logging  
The script prints detailed logs for every step:
- Processed pages  
- Skipped pages  
- Grouping decisions  
- File creation events  

---

## Requirements

- Python 3.8+
- XWiki instance with REST API enabled
- Python packages:
  - `requests`
  - `markdownify`
  - `beautifulsoup4`

Install dependencies:

```bash
pip install requests markdownify beautifulsoup4
