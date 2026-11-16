"""Preserve raw compiled-module legal material; never issue a legal verdict."""

import argparse
import hashlib
import json
from pathlib import Path
import re


def objects(text):
    decoder = json.JSONDecoder()
    while text.strip():
        value, end = decoder.raw_decode(text.lstrip())
        yield value
        text = text.lstrip()[end:]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def collect(packages, source, goroot, output):
    # go list -deps describes packages actually compiled, not every module in
    # the much larger go.mod graph. Replacements retain both identities.
    output.mkdir(parents=True, exist_ok=False)
    modules = {}
    for package in objects(packages):
        if package.get("Error") or package.get("DepsErrors"):
            raise ValueError("go list reported an unresolved package")
        module = package.get("Module")
        if module:
            key = (module["Path"], module.get("Version", ""))
            if key in modules and modules[key] != module:
                raise ValueError("Conflicting module source identities")
            modules[key] = module
    if not modules:
        raise ValueError("No compiled-module evidence")

    files = {}

    def capture(directory, prefix, recursive=False):
        found = []
        candidates = directory.rglob("*") if recursive else directory.glob("*")
        for path in sorted(candidates):
            if not re.match(r"^(licen[cs]e|copying|notice|copyright|patents)([._-].*)?$", path.name, re.I):
                continue
            # Never dereference a source symlink into an unrelated file.
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(directory)
            if any(parent.is_symlink() for parent in path.parents if parent != directory):
                continue
            name = str(Path(prefix) / relative)
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
            files[name] = digest(target)
            found.append(name)
        return found

    source_files = capture(source, "upstream")
    go_files = capture(goroot, "go-toolchain")
    if "upstream/LICENSE" not in source_files or "go-toolchain/LICENSE" not in go_files:
        raise ValueError("Upstream or Go toolchain license absent")
    rows = []
    for (name, version), module in sorted(modules.items()):
        effective = module.get("Replace", module)
        directory = Path(effective["Dir"]) if effective.get("Dir") else None
        key = hashlib.sha256((name + "@" + version).encode()).hexdigest()
        found = capture(directory, "modules/" + key, recursive=True) if directory else []
        rows.append({
            "path": name, "version": version,
            "replacement": {k: effective[k] for k in ("Path", "Version", "Sum") if k in effective} if "Replace" in module else None,
            "sum": module.get("Sum"), "files": found,
            "status": "MATERIAL_COLLECTED_NOT_REVIEWED" if found else "MISSING_LEGAL_MATERIAL",
        })
    report = {
        "schema": 1, "status": "PENDING_ACCOUNTABLE_REVIEW", "reviewer": None,
        "scope": "Raw source legal material for compiled Go dependencies, upstream release and Go toolchain",
        "limitations": "Not an exhaustive license determination, source offer, NOTICE approval or redistribution permission. Missing and inherited notices require independent review.",
        "modules": rows, "missing_modules": [r["path"] for r in rows if not r["files"]],
        "sha256": files, "release_eligible": False,
    }
    (output / "inventory.json").write_text(json.dumps(report, indent=2) + "\n")
    files["inventory.json"] = digest(output / "inventory.json")
    (output / "SHA256SUMS").write_text("".join(f"{sha}  {name}\n" for name, sha in sorted(files.items())))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("packages", "source", "goroot", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = collect(args.packages.read_text(), args.source, args.goroot, args.output)
    print(json.dumps({"status": result["status"], "modules": len(result["modules"]),
                      "missing_modules": len(result["missing_modules"]), "release_eligible": False}))
