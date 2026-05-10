#!/usr/bin/env python3
import ast
import os
import sys

def build():
    # We must preserve the module dependency order:
    # config -> tracker -> parser -> ui -> main
    modules = ["config.py", "tracker.py", "parser.py", "ui.py", "main.py"]
    src_dir = "src"

    all_imports = set()
    combined_code = []

    for mod_name in modules:
        filepath = os.path.join(src_dir, mod_name)
        with open(filepath, "r") as f:
            code = f.read()

        tree = ast.parse(code)

        # Extract imports and standard code blocks
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    all_imports.add(f"import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and not node.module.startswith("src"):
                    # Only standard library import froms
                    for alias in node.names:
                        as_clause = f" as {alias.asname}" if alias.asname else ""
                        all_imports.add(f"from {node.module} import {alias.name}{as_clause}")
            else:
                # Get the source segment for this AST node
                segment = ast.get_source_segment(code, node)
                if segment:
                    combined_code.append(segment)

    # Output file
    out_file = "rustdesk-monitor.py"

    with open(out_file, "w") as f:
        f.write("#!/usr/bin/env python3\n")
        f.write('"""\nRustDesk Connection Monitor v4.0\n')
        f.write('Generated from modular src/ files using build.py.\n')
        f.write('"""\n\n')

        # One module import per line, alphabetized
        for imp in sorted(list(all_imports)):
            f.write(imp + "\n")
        f.write("\n")

        for block in combined_code:
            f.write(block + "\n\n")

        f.write('if __name__ == "__main__":\n')
        f.write('    main()\n')

    print(f"Successfully built {out_file}")

if __name__ == "__main__":
    build()
