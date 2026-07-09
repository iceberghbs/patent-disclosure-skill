#!/usr/bin/env python3
"""
One-step: render mermaid (B/W) & convert .md -> .docx with OMML math.

Pipeline: mmdc -t neutral -b white -e png -> pandoc --mathml

Usage:
  python3 tools/build_docx.py -i draft.md -o "交底书名_YYYYMMDDHHmmss.md"
  python3 tools/build_docx.py -i draft.md -o out/定稿.md --no-docx
  python3 tools/build_docx.py -i draft.md -o out/定稿.md --assets-dir figures/mermaid

Dependencies:
  - Node.js + mmdc (mermaid CLI): npm install -g @mermaid-js/mermaid-cli
  - pandoc: apt-get install pandoc
"""
import subprocess
import sys
import argparse
import shutil
from pathlib import Path


def find_mmdc():
    """Find mmdc binary: local node_modules -> PATH -> npx fallback."""
    # 1. Local node_modules
    skill_dir = Path(__file__).resolve().parent
    local_mmdc = skill_dir / "node_modules" / ".bin" / "mmdc"
    if local_mmdc.exists():
        return str(local_mmdc)
    # 2. PATH
    path_mmdc = shutil.which("mmdc")
    if path_mmdc:
        return path_mmdc
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Build .docx from .md with B/W mermaid + OMML math"
    )
    parser.add_argument("-i", "--input", required=True, help="Input .md file")
    parser.add_argument("-o", "--output", help="Output .md file (default: overwrite input)")
    parser.add_argument("--no-docx", action="store_true", help="Skip .docx generation")
    parser.add_argument(
        "--assets-dir",
        default="artefacts",
        help="Mermaid PNG output dir (default: artefacts)",
    )
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"[build_docx] ERROR: input not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_md = Path(args.output).resolve() if args.output else input_path
    output_dir = output_md.parent
    assets_dir = output_dir / args.assets_dir
    assets_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: mmdc - render mermaid to B/W PNG
    mmdc = find_mmdc()
    if not mmdc:
        print(
            "[build_docx] ERROR: mmdc not found. "
            "Install: npm install -g @mermaid-js/mermaid-cli",
            file=sys.stderr,
        )
        sys.exit(1)

    mmdc_cmd = [
        mmdc,
        "-i", str(input_path),
        "-o", str(output_md),
        "-t", "neutral",
        "-b", "white",
        "-e", "png",
        "-a", str(assets_dir),
    ]
    result = subprocess.run(mmdc_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[build_docx] mmdc failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    if result.stdout:
        print(result.stdout, file=sys.stderr)

    # Step 2: pandoc - convert to .docx with OMML math
    if not args.no_docx:
        docx_path = output_md.with_suffix(".docx")
        pandoc = shutil.which("pandoc")
        if not pandoc:
            print(
                "[build_docx] ERROR: pandoc not found. "
                "Install: apt-get install pandoc",
                file=sys.stderr,
            )
            sys.exit(1)

        pandoc_cmd = [
            pandoc,
            str(output_md),
            "-o", str(docx_path),
            "--mathml",
            f"--resource-path={output_dir}",
        ]
        try:
            subprocess.run(pandoc_cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print(
                f"[build_docx] pandoc failed:\n{e.stderr}",
                file=sys.stderr,
            )
            # Fallback: try md_to_docx.py if pandoc fails
            md_to_docx = Path(__file__).resolve().parent / "md_to_docx.py"
            if md_to_docx.exists():
                print(
                    f"[build_docx] Fallback: trying md_to_docx.py "
                    f"(formulas will be PNG, not OMML)",
                    file=sys.stderr,
                )
                fallback_cmd = [
                    sys.executable,
                    str(md_to_docx),
                    "-i", str(output_md),
                    "-o", str(docx_path),
                    "--base-dir", str(output_dir),
                ]
                subprocess.run(fallback_cmd, check=False)
            else:
                sys.exit(1)

    print(f"[build_docx] Markdown: {output_md}", file=sys.stderr)
    if not args.no_docx:
        print(f"[build_docx] Word: {docx_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
