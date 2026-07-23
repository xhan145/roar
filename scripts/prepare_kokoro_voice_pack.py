"""Explicitly download and install ROAR's pinned offline Kokoro voice pack.

No application code calls this script. Network activity occurs only with the
explicit --download flag.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import paths
from tts import model_manager


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true",
                        help="explicitly fetch pinned files from Hugging Face")
    parser.add_argument("--source",
                        help="existing offline directory containing pinned files")
    parser.add_argument("--destination", default=paths.tts_model_dir())
    args = parser.parse_args()
    if bool(args.download) == bool(args.source):
        parser.error("choose exactly one of --download or --source")

    if args.source:
        source = os.path.abspath(args.source)
        result = model_manager.install_pack(source, args.destination)
    else:
        from huggingface_hub import hf_hub_download
        manifest = model_manager.canonical_manifest()
        parent = os.path.dirname(os.path.abspath(args.destination))
        os.makedirs(parent, exist_ok=True)
        stage = tempfile.mkdtemp(prefix=".kokoro-download-", dir=parent)
        try:
            for index, entry in enumerate(manifest["files"], 1):
                relative = entry["path"]
                print(f"[{index}/{len(manifest['files'])}] {relative}")
                cached = hf_hub_download(
                    repo_id=manifest["upstream"],
                    filename=relative,
                    revision=manifest["revision"],
                )
                target = os.path.join(stage, *relative.split("/"))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copyfile(cached, target)
            with open(os.path.join(stage, "manifest.json"), "w",
                      encoding="utf-8") as handle:
                json.dump(manifest, handle, indent=2)
            model_manager.verify_pack(stage, verify_hashes=True)
            result = model_manager.install_pack(stage, args.destination)
        finally:
            if os.path.isdir(stage):
                shutil.rmtree(stage)
    result.pop("path", None)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
