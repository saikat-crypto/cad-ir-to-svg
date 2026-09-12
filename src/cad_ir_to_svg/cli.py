"""
Command-Line Interface (CLI) for cad-ir-to-svg.
Provides human-friendly conversion and agentic introspection commands.
"""

import argparse
import sys
import json
from pathlib import Path

from .compiler import compile_ir_to_svg, get_svg_bounds, list_svg_layers
from .config import PRESETS, DEFAULT_PRESET


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="cad-ir-to-svg",
        description="High-Fidelity Vector CAD to SVG Compiler (La Vinci Hub-and-Spoke Ecosystem).",
    )
    parser.add_argument("input", help="Path to input LAVINCI_CAD_IR_V3 JSON file.")
    parser.add_argument(
        "-o", "--output",
        help="Path to output SVG file. Default: <input_stem>.svg",
    )
    parser.add_argument(
        "--preset",
        choices=list(PRESETS.keys()),
        default="web-interactive-light",
        help="Styling and layout preset (default: web-interactive-light).",
    )
    parser.add_argument(
        "--inspect-bounds",
        action="store_true",
        help="Inspect drawing spatial extents and exit without generating SVG.",
    )
    parser.add_argument(
        "--list-layers",
        action="store_true",
        help="List all layers present in drawing and exit.",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        return 1

    # Introspection commands
    if args.inspect_bounds:
        bounds = get_svg_bounds(input_path)
        print(json.dumps(bounds, indent=2))
        return 0

    if args.list_layers:
        layers = list_svg_layers(input_path)
        print("\n".join(layers))
        return 0

    # Compilation
    output_path = Path(args.output) if args.output else input_path.with_suffix(".svg")

    try:
        out = compile_ir_to_svg(input_path, output_path, preset=args.preset)
        print(f"[SUCCESS] Compiled {input_path.name} -> {out} (Preset: {args.preset})")
        return 0
    except Exception as e:
        print(f"[ERROR] Compilation failed: {str(e)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
