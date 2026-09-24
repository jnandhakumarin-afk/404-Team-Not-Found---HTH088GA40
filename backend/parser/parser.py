def parse_code(code: str):
    lines = code.splitlines()

    return {
        "total_lines": len(lines),
        "lines": [
            {
                "line_number": index + 1,
                "content": line
            }
            for index, line in enumerate(lines)
        ]
    }


def extract_changed_lines(diff: str):
    changed_lines = []

    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            changed_lines.append(line[1:])

    return changed_lines