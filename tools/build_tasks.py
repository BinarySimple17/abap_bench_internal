#!/usr/bin/env python3
"""Build task files for the in-SAP LLM ABAP benchmark (syntax-only phase 1).

Reads tasks from the source dataset of the Python benchmark
(LLM-Benchmark-ABAP-Code-Generation) and emits one self-contained task file
per task into ../tasks/. Each task file is later imported into table ZLLBM_TASK
by report ZLLBM_IMPORT_TASKS.

Transformations applied (so the task is usable without creating any global
object in the SAP system):
  - canonical solution: class renamed z_humaneval_NNN -> lcl_solution
  - unit test: calls rewritten z_humaneval_NNN=>xxx( -> lcl_solution=>xxx(
    (TEST section is only consumed in phase 2; kept verbatim otherwise)

Usage:
  python build_tasks.py [--source <path>] [--out <path>]

Defaults: source = F:/JAVA/LLM-Benchmark-ABAP-Code-Generation-main
          out    = ../tasks (relative to this script)

To add more tasks: extend the SELECTED dict below (prompt index -> category)
and re-run. Categories follow the source dataset taxonomy:
  String Handling | List or Array Operation | Mathematical Calculation |
  Logical Condition | ABAP Database Operation
"""

import argparse
import re
from pathlib import Path

DEFAULT_SOURCE = Path("F:/JAVA/LLM-Benchmark-ABAP-Code-Generation-main")

# Starter set: 10 tasks, balanced across categories, no DDIC dependencies.
# key = prompt index in dataset/prompts/<N>.txt
SELECTED = {
    0:  "List or Array Operation",      # has_close_elements
    1:  "String Handling",              # separate_paren_groups
    2:  "Mathematical Calculation",     # truncate_number
    3:  "Logical Condition",            # below_zero
    4:  "Mathematical Calculation",     # mean_absolute_deviation
    5:  "List or Array Operation",      # intersperse
    7:  "String Handling",              # filter_by_substring
    9:  "List or Array Operation",      # rolling_max
    13: "Mathematical Calculation",     # greatest_common_divisor
    14: "String Handling",              # all_prefixes
}


def contract_from_unittest(test_src: str) -> tuple[str, str]:
    """Extract (class_name, method_name) from the first z_humaneval_x=>call()."""
    m = re.search(r"(z_humaneval_\w+)=>(\w+)", test_src)
    if not m:
        raise ValueError("no z_humaneval_*=>method( call found in unit test")
    return m.group(1), m.group(2)


def build_task_file(idx: int, category: str, src_root: Path) -> str:
    idx3 = f"{idx:03d}"
    prompt = (src_root / "dataset" / "prompts" / f"{idx}.txt").read_text(encoding="utf-8").strip()
    canonical_path = src_root / "dataset" / "abap_canonical_solution" / f"z_humaneval_{idx3}.abap"
    test_path = src_root / "dataset" / "abap_unittests" / f"z_humaneval_{idx3}_test.abap"
    canonical = canonical_path.read_text(encoding="utf-8").strip()
    test = test_path.read_text(encoding="utf-8").strip()

    klass, method = contract_from_unittest(test)

    # Rename the global class to the local contract class so both canonical
    # solution and unit test compile inside a plain program source.
    canonical = re.sub(rf"\b{klass}\b", "lcl_solution", canonical, flags=re.IGNORECASE)
    test = re.sub(rf"\b{klass}\b", "lcl_solution", test, flags=re.IGNORECASE)

    return (
        f"@id: humaneval_{idx3}\n"
        f"@source: LLM-Benchmark-ABAP-Code-Generation dataset/prompts/{idx}.txt (MIT)\n"
        f"@method: {method}\n"
        f"@category: {category}\n"
        f"@active: true\n"
        f"\n"
        f"---PROMPT---\n"
        f"{prompt}\n"
        f"\n"
        f"---CANONICAL---\n"
        f"{canonical}\n"
        f"\n"
        f"---TEST---\n"
        f"{test}\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent / "tasks")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    for idx, category in sorted(SELECTED.items()):
        task_id = f"humaneval_{idx:03d}"
        content = build_task_file(idx, category, args.source)
        out_file = args.out / f"{task_id}.task.txt"
        out_file.write_text(content, encoding="utf-8", newline="\n")
        print(f"wrote {out_file.name}")


if __name__ == "__main__":
    main()
