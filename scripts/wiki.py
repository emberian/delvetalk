#!/usr/bin/env python3
"""Read-only Agentwiki edit preparation. A cache digest is NOT an atomic commit."""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlsplit


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_snapshot(snapshot):
    if snapshot.get("format") != "delvetalk-wiki-observation-v1":
        raise ValueError("unknown snapshot format")
    if digest(snapshot["markdown"]) != snapshot["observedSha256"]:
        raise ValueError("snapshot bytes do not match recorded digest")
    return snapshot


def section_body(markdown, section):
    matches = list(re.finditer(r"^## ([^\r\n]+)\r?$", markdown, re.M))
    selected = [i for i, m in enumerate(matches) if m.group(1) == section]
    if len(selected) != 1:
        raise ValueError("section must exist exactly once, with an exact name")
    i = selected[0]
    end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
    # Preserve exact observed bytes, including surrounding newlines.
    return markdown[matches[i].end():end]


def prepare(snapshot, section, replacement):
    snapshot = validate_snapshot(snapshot)
    title_match = re.match(r"^# ([^\r\n]+)\r?\n", snapshot["markdown"])
    if not title_match:
        raise ValueError("snapshot has no page title")
    if "\n" in section or "\r" in section or "›" in section:
        raise ValueError("invalid section identifier")
    if re.search(r"^#{1,2} ", replacement, re.M):
        raise ValueError("replacement must be one section body, not a page/section heading")
    before = section_body(snapshot["markdown"], section)
    return {
        "format": "delvetalk-wiki-proposal-v1",
        "source": snapshot["source"], "page": title_match.group(1),
        "section": section, "observedSha256": snapshot["observedSha256"],
        "sectionBefore": before, "sectionBeforeSha256": digest(before),
        "replacement": replacement,
        "postDraft": f"edit: {title_match.group(1)} › {section}\n{replacement}",
        "authority": "none: observation-only; receiver must atomically check its current root",
    }


def check(proposal, current):
    current = validate_snapshot(current)
    if proposal.get("format") != "delvetalk-wiki-proposal-v1":
        raise ValueError("unknown proposal format")
    if digest(proposal["sectionBefore"]) != proposal["sectionBeforeSha256"]:
        raise ValueError("proposal preimage digest mismatch")
    if proposal["source"] != current["source"]:
        raise ValueError("snapshot is from a different source")
    same = proposal["observedSha256"] == current["observedSha256"]
    same_section = proposal["sectionBefore"] == section_body(current["markdown"], proposal["section"])
    return {"status": "observed-unchanged" if same and same_section else "stale-observation",
            "canCommit": False,
            "reason": "A cached read cannot establish freshness at the authoritative writer."}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    # Do not silently overwrite a previous observation/proposal.
    with open(path, "x", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("url"); snap.add_argument("output")
    prep = sub.add_parser("prepare")
    prep.add_argument("snapshot"); prep.add_argument("section")
    prep.add_argument("replacement"); prep.add_argument("output")
    chk = sub.add_parser("check")
    chk.add_argument("proposal"); chk.add_argument("current")
    args = parser.parse_args()
    if args.command == "snapshot":
        url = urlsplit(args.url)
        if url.scheme != "https" or url.netloc != "agentwiki.elsyian.moe" or not url.path.endswith(".md"):
            raise ValueError("use an HTTPS Agentwiki .md URL")
        request = Request(args.url, headers={"User-Agent": "delvetalk/0.1 (+https://github.com/emberian/delvetalk)"})
        with urlopen(request, timeout=30) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("page exceeds 2MB observation limit")
        markdown = raw.decode("utf-8")
        save(args.output, {"format": "delvetalk-wiki-observation-v1", "source": args.url,
             "observedAt": datetime.now(timezone.utc).isoformat(),
             "observedSha256": digest(markdown), "markdown": markdown})
    elif args.command == "prepare":
        save(args.output, prepare(read(args.snapshot), args.section,
                                 Path(args.replacement).read_text(encoding="utf-8")))
    else:
        verdict = check(read(args.proposal), read(args.current))
        print(json.dumps(verdict))
        return 0 if verdict["status"] == "observed-unchanged" else 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError, OSError) as error:
        print(f"wiki: {error}", file=sys.stderr)
        sys.exit(2)
