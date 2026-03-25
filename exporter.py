import os
import re
import json
import requests
from markdownify import markdownify as md
from bs4 import BeautifulSoup

# ---------------------------------------------------------
# LOGGING HELPERS
# ---------------------------------------------------------
def log(msg):
    print(f"[LOG] {msg}")

def log_skip(msg):
    print(f"[SKIP] {msg}")

def log_group(msg):
    print(f"[GROUP] {msg}")

def log_file(msg):
    print(f"[FILE] {msg}")


# ---------------------------------------------------------
# CONFIG (safe for public use)
# ---------------------------------------------------------
AUTH = ("username", "password")  # Replace with your XWiki credentials
ROOT_URL = "http://your-xwiki-domain/rest/wikis/xwiki/spaces"
INPUT_JSON = "xwiki_export.json"
OUTPUT_DIR = "xwiki_markdown_export"

SYSTEM_SPACE_DENYLIST = {"XWiki", "Main", "Help", "Sandbox"}

session = requests.Session()
session.auth = AUTH
session.headers.update({"Accept": "application/json"})


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------
def sanitize_filename(name):
    return re.sub(r"[\\/:*?\"<>|]+", "_", name).strip() or "Untitled"

def extract_main_content(html):
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("div", id="xwikicontent")
    return str(main) if main else html

def html_to_markdown(html):
    clean_html = extract_main_content(html)
    return md(clean_html, heading_style="ATX")

def fetch_html(url):
    r = session.get(url)
    r.raise_for_status()
    return r.text

def space_path(full_name):
    if ":" not in full_name:
        return []
    _, rest = full_name.split(":", 1)

    parts = []
    current = []
    i = 0
    while i < len(rest):
        if rest[i] == "\\" and i + 1 < len(rest) and rest[i+1] == ".": 
            current.append(".")
            i += 2
        elif rest[i] == ".":
            parts.append("".join(current))
            current = []
            i += 1
        else:
            current.append(rest[i])
            i += 1

    if current:
        parts.append("".join(current))
    return parts


# ---------------------------------------------------------
# GROUPING LOGIC (Special Case)
# ---------------------------------------------------------
def find_section_key(parts):

    # Special case if found
    if parts[0] == "<Special folder>":
        if len(parts) >= 2:
            version = "<Special folder>"
            section = parts[1]
            return (version, section)

    # Normal logic
    if len(parts) >= 3:
        return (parts[1], parts[2])

    if len(parts) == 2:
        return (parts[0], parts[1])

    return None


# ---------------------------------------------------------
# FETCH ROOT SPACES
# ---------------------------------------------------------
def fetch_root_spaces():
    r = session.get(ROOT_URL)
    r.raise_for_status()
    return r.json()

def is_system_space(space_obj):
    name = (space_obj.get("name") or "").strip()
    return name in SYSTEM_SPACE_DENYLIST

def extract_pages(space_obj):
    pages_link = next(
        (l["href"] for l in space_obj.get("links", [])
         if isinstance(l.get("rel"), str) and "pages" in l["rel"]),
        None
    )
    if not pages_link:
        return []
    r = session.get(pages_link)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    data = r.json()
    return data.get("pages", [])


# ---------------------------------------------------------
# EXPORT TO TXT (spaces only)
# ---------------------------------------------------------
def build_filtered_export():
    root = fetch_root_spaces()
    spaces = root.get("spaces", [])
    result = []

    for s in spaces:
        if is_system_space(s):
            continue

        pages = extract_pages(s)

        result.append({
            "id": s.get("id"),
            "name": s.get("name"),
            "home": s.get("home"),
            "viewUrl": s.get("xwikiAbsoluteUrl"),
            "pages": pages
        })

    return result

def export_to_txt(path=INPUT_JSON):
    data = build_filtered_export()

    # Sort pages inside each space
    for space in data:
        pages = space.get("pages", [])
        if not pages:
            continue

        def page_depth(p):
            full = p.get("fullName", "").replace("\\.", ".")
            return len(full.split("."))

        def has_children(p):
            return bool(p.get("hasChildren"))

        pages.sort(key=lambda p: (has_children(p), page_depth(p), p.get("name", "").lower()))

    data.sort(key=lambda x: x.get("name", "").lower())

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Export complete! Data saved to {path} ({len(data)} spaces)")


# ---------------------------------------------------------
# EXPORT ALL (Markdown)
# ---------------------------------------------------------
def export_all():

    log("Loading flat JSON page list...")
    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        pages = json.load(f)

    log(f"Loaded {len(pages)} page entries")

    all_fullnames = [p["id"] for p in pages if "id" in p]
    log(f"Collected {len(all_fullnames)} fullNames for parent detection")

    def is_parent(full_name):
        prefix = full_name + "."
        return any(other.startswith(prefix) for other in all_fullnames)

    grouped = {}

    log("Starting leaf-page filtering and grouping...")

    for page in pages:
        full_name = page.get("id")
        view_url = page.get("viewUrl")

        if not full_name or not view_url:
            log_skip(f"Missing id or viewUrl → {page}")
            continue

        if full_name.startswith("xwiki:Help."):
            log_skip(f"Help namespace → {full_name}")
            continue

        if is_parent(full_name):
            log_skip(f"Parent page → {full_name}")
            continue

        parts = space_path(full_name)
        if len(parts) < 2:
            log_skip(f"Invalid path structure → {full_name}")
            continue

        key = find_section_key(parts)
        if not key:
            key = (parts[0], parts[-1])

        full_path = " - ".join(parts)
        grouped.setdefault(key, []).append((full_path, view_url, full_name))

        log_group(f"Grouped under {key}: {full_path}")

    log(f"Grouping complete. {len(grouped)} groups created.")

    # ---------------------------------------------------------
    # EXPORT MARKDOWN FILES
    # ---------------------------------------------------------
    for (version, section), items in grouped.items():

        folder_path = os.path.join(OUTPUT_DIR, sanitize_filename(version))
        os.makedirs(folder_path, exist_ok=True)
        log(f"Created/using folder: {folder_path}")

        if section.lower() == "<Special folder>":
            combined_filename = f"<Special folder> - {sanitize_filename(version)}.md"
        else:
            combined_filename = f"{sanitize_filename(section)} - {sanitize_filename(version)}.md"

        combined_filepath = os.path.join(folder_path, combined_filename)
        log_file(f"Creating combined Markdown file: {combined_filename}")

        # TOC
        toc = "## Table of Contents\n\n"
        for full_path, _, _ in items:
            anchor = re.sub(r'[^a-zA-Z0-9]+', '-', full_path).strip('-').lower()
            toc += f"- [{full_path}](#{anchor})\n"
        toc += "\n---\n\n"

        with open(combined_filepath, "w", encoding="utf-8") as f:
            f.write(toc)

        # CONTENT
        for full_path, view_url, full_name in items:
            log(f"Fetching HTML for: {full_name} → {view_url}")
            html = fetch_html(view_url)
            md_text = html_to_markdown(html)

            if len(md_text.strip()) < 30:
                log_skip(f"Content too short → {full_name}")
                continue

            anchor = re.sub(r'[^a-zA-Z0-9]+', '-', full_path).strip('-').lower()

            section_md = (
                f"## {full_path}\n"
                f"<a id=\"{anchor}\"></a>\n\n"
                f"{md_text}\n\n"
                f"---\n\n"
            )

            with open(combined_filepath, "a", encoding="utf-8") as f:
                f.write(section_md)

            log_file(f"Added section for: {full_path}")

    # ---------------------------------------------------------
    # CREATE _All FOLDER
    # ---------------------------------------------------------
    all_folder = os.path.join(OUTPUT_DIR, "_All")
    log("Preparing _All folder...")

    if os.path.exists(all_folder):
        for root, dirs, files in os.walk(all_folder):
            for file in files:
                if file.endswith(".md"):
                    os.remove(os.path.join(root, file))
                    log_file(f"Deleted old file from _All: {file}")
    else:
        os.makedirs(all_folder, exist_ok=True)
        log("Created _All folder")

    copied = set()

    for root, dirs, files in os.walk(OUTPUT_DIR):
        if root == all_folder:
            continue
        for file in files:
            if file.endswith(".md"):
                if file in copied:
                    log_skip(f"Duplicate skipped in _All: {file}")
                    continue
                src = os.path.join(root, file)
                dst = os.path.join(all_folder, file)
                with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
                    fdst.write(fsrc.read())
                copied.add(file)
                log_file(f"Copied to _All: {file}")

    log("📦 All files collected into _All")
    log("Markdown export complete!")


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
if __name__ == "__main__":
    export_to_txt()
    export_all()
