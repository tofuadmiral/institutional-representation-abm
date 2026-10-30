"""No-inference comparison with the pinned base tokenizer on every frozen prompt."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper3.audit_runtime import digest
from experiments.paper3_bonsai_validation import stages, REVISION

BASE_REVISION = "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0"


def audit(model, base):
    from transformers import AutoTokenizer
    if model.name != REVISION or base.name != BASE_REVISION:
        raise ValueError("requires pinned snapshots")
    actual = AutoTokenizer.from_pretrained(str(model), local_files_only=True)
    reference = AutoTokenizer.from_pretrained(str(base), local_files_only=True)
    rows = []
    for stage, cases in stages().items():
        for case in cases:
            prompt = actual.apply_chat_template(case["messages"], tokenize=False,
                add_generation_prompt=True, enable_thinking=True, reasoning_effort="medium")
            ids = actual.encode(prompt, add_special_tokens=True)
            ref_ids = reference.encode(prompt, add_special_tokens=True)
            rows.append(dict(stage=stage, case=case["name"], equal=ids == ref_ids,
                             prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                             actual_ids_hash=digest(ids), reference_ids_hash=digest(ref_ids)))
    return dict(model_revision=REVISION, base_revision=BASE_REVISION,
        tokenizer_files_equal=(model / "tokenizer.json").read_bytes() == (base / "tokenizer.json").read_bytes(),
        tokenizer_config_files_equal=(model / "tokenizer_config.json").read_bytes() == (base / "tokenizer_config.json").read_bytes(),
        tokenizer_sha256=hashlib.sha256((model / "tokenizer.json").read_bytes()).hexdigest(),
        loaded_classes=[type(actual).__name__, type(reference).__name__],
        loaded_pretokenizers_equal=actual.backend_tokenizer.pre_tokenizer.__getstate__() == reference.backend_tokenizer.pre_tokenizer.__getstate__(),
        all_frozen_prompt_ids_equal=all(r["equal"] for r in rows), cases=rows,
        limitation="Only these 41 rendered prompts; different loaded regexes are not generally equivalent. No Mistral regex patch applied.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--base", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.model, args.base), indent=2))
