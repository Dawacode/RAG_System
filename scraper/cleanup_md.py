import os
import glob

HEADER = [
    "Toggle navigation \u200c \u200c \u200c",
    "_\u2060_",
    "[lagen.nu](https://lagen.nu/)",
    "  * [Lagar](https://lagen.nu/dataset/sfs)",
    "  * [Rättsfall](https://lagen.nu/dataset/dv)",
    "  * [Förarbeten](https://lagen.nu/dataset/forarbeten)",
    "  * [Föreskrifter](https://lagen.nu/dataset/myndfs)",
    "  * [Praxis](https://lagen.nu/dataset/myndprax)",
    "  * [Begrepp](https://lagen.nu/dataset/keyword)",
    "  * [Nyheter](https://lagen.nu/dataset/sitenews)"
]

FOOTER = [
    "Ikraftträder",
    "    2025-01-01",
    "* [Om lagen.nu](https://lagen.nu/om/index)",
    "* [Ansvarsfriskrivning](https://lagen.nu/om/ansvarsfriskrivning)",
    "* [Kontaktinformation](https://lagen.nu/om/kontakt)",
    "* [Hostas av Lysator](https://www.lysator.liu.se/)"
]

def remove_section(lines, section, from_start=True):
    n = len(section)
    if from_start:
        for i in range(len(lines)):
            if lines[i:i+n] == section:
                return [line.strip('\u200c\u2060') for line in lines[i+n:] if line.strip()]
        return [line.strip('\u200c\u2060') for line in lines if line.strip()]
    else:
        for i in range(len(lines)-n, -1, -1):
            if lines[i:i+n] == section:
                return [line.strip('\u200c\u2060') for line in lines[:i] if line.strip()]
        return [line.strip('\u200c\u2060') for line in lines if line.strip()]

def remove_footer(lines):
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].startswith("Ikraftträder") or lines[i].startswith("Beskrivning saknas!"):
            return lines[:i]
    return lines

def clean_markdown_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = [line.rstrip('\r\n') for line in f]
    
    if not lines or all(not line.strip() for line in lines):
        print(f"Empty file: {filepath}")
        return
        
    orig_lines = lines[:]
    lines = remove_section(lines, HEADER, from_start=True)
    lines = remove_footer(lines)
    
    lines = [line.strip('\u200c\u2060\u200b') for line in lines if line.strip()]
    
    if lines and lines != orig_lines:
        with open(filepath, 'w', encoding='utf-8') as f:
            for line in lines:
                f.write(line + '\n')
        print(f"Cleaned: {filepath}")
    else:
        print(f"No change: {filepath}")

def main():
    md_files = glob.glob(os.path.join(os.path.dirname(__file__), 'output', '*.md'))
    for md_file in md_files:
        clean_markdown_file(md_file)

if __name__ == "__main__":
    main()