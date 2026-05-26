import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python read_file_example.py <file-path>", file=sys.stderr)
        return 1

    file_path = Path(sys.argv[1])

    try:
        with file_path.open("r", encoding="utf-8") as file:
            for line in file:
                print(line, end="")
    except OSError as error:
        print(f"Could not read file: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
