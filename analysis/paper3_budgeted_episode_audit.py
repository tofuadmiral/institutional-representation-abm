"""Read-only raw-request replay and controller accounting for budgeted episode."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper3.audit_runtime import digest
from experiments.paper3_bonsai_budgeted_episode import (
    CAP, THINKING, MAX_CALLS, fixtures, request_for, private_score, run_episode,
    EpisodeBackend, BoundaryRecorder, render,
)


def expected_boundary(tokens, start_id, end_id, newline_id, finish):
    # Independently reproduce the frozen installed counter's control decisions.
    count, in_thinking, exceeded, index = 0, True, False, 0
    schedules = []
    for position, token in enumerate(tokens):
        if token == start_id:
            in_thinking = True
            continue
        if token == end_id:
            in_thinking, exceeded, index = False, False, 0
            continue
        if in_thinking:
            count += 1
            exceeded = exceeded or count > THINKING
        if exceeded and index < 2:
            forced = (newline_id, end_id)[index]
            index += 1
            # EOS is processed internally, but only the terminal chunk is seen.
            if not (position == len(tokens) - 1 and finish == "stop"):
                schedules.append(dict(position=position + 1, token_id=forced, counter=count))
    b = BoundaryRecorder()
    b.tokens, b.schedules = tokens, schedules
    return b.summary(end_id)


def verify_tokenization(row, tokenizer, base, eos_ids):
    prompt, ids = render(tokenizer, base, row["request"]["messages"])
    if prompt != row["rendered_prompt"] or ids != row["prompt_token_ids"]:
        raise ValueError("rendered prompt/token replay mismatch")
    tokens = row["generated_token_ids"]
    choice = row["response"]["choices"][0]
    if choice["finish_reason"] == "stop":
        if not tokens or tokens[-1] not in eos_ids:
            raise ValueError("normal termination without recorded EOS")
        tokens = tokens[:-1]  # Stream counts but does not detokenize the EOS.
    decoded = tokenizer.decode(tokens, skip_special_tokens=False, clean_up_tokenization_spaces=False)
    if decoded != choice["message"]["content"]:
        raise ValueError("raw response differs from recorded output tokens")


class Replay:
    def __init__(self, protocol, records, expected_keys):
        self.protocol, self.records, self.expected_keys = protocol, records, expected_keys
        self.position = 0

    def call(self, messages, seed, base):
        if self.position >= len(self.expected_keys):
            raise ValueError("raw replay exhausted")
        key = self.expected_keys[self.position]
        self.position += 1
        row = self.records[key]
        if row["request"] != request_for(self.protocol["model"], messages, seed):
            raise ValueError("raw request replay mismatch")
        return key, row


def audit(root):
    manifest = json.loads((root / "manifest.json").read_text())
    protocol, errors = manifest["protocol"], []
    if protocol["name"] == "bonsai-message-reporting-feasibility-v1":
        from experiments import paper3_bonsai_message_reporting as study
    elif protocol["name"] == "bonsai-budgeted-episode-feasibility-v1":
        from experiments import paper3_bonsai_budgeted_episode as study
    else:
        raise ValueError("unsupported frozen study")
    ph = digest(manifest)
    snapshots = json.loads((root / "sources.json").read_text())
    for name, expected in manifest["sources"].items():
        relative = str(Path(name).relative_to(ROOT))
        if hashlib.sha256(snapshots[relative].encode()).hexdigest() != expected:
            errors.append("source snapshot mismatch: " + name)
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise ValueError("cannot replay using changed frozen source: " + name)
    # Token IDs come from the frozen artifact, without importing MLX or a model.
    tokenfile = Path(protocol["model"]) / "tokenizer.json"
    if hashlib.sha256(tokenfile.read_bytes()).hexdigest() != protocol["model_file_sha256"]["tokenizer.json"]:
        errors.append("tokenizer artifact mismatch")
    tokenizer = json.loads(tokenfile.read_text())
    specials = {t["content"]: t["id"] for t in tokenizer["added_tokens"]}
    newline_id = tokenizer["model"]["vocab"]["Ċ"]
    records = {p.stem: json.loads(p.read_text()) for p in (root / "calls").glob("*.json")}
    sessions = {p.stem: json.loads(p.read_text()) for p in (root / "sessions").glob("*.json")}
    for key, row in records.items():
        try:
            assert row["protocol_hash"] == ph
            assert key == digest(dict(request=row["request"], protocol=ph))
            assert row["request"] == request_for(protocol["model"], row["request"]["messages"], row["request"]["seed"])
            usage = row["response"]["usage"]
            assert len(row["prompt_token_ids"]) == usage["prompt_tokens"] <= 8192
            assert len(row["generated_token_ids"]) == usage["completion_tokens"] <= CAP
            assert row["cached_tokens"] == 0
            if not row.get("generation_error"):
                assert row["boundary"] == expected_boundary(row["generated_token_ids"], specials["<think>"],
                    specials["</think>"], newline_id, row["response"]["choices"][0]["finish_reason"])
        except (AssertionError, ValueError, KeyError) as exc:
            errors.append("raw record mismatch: " + key + " " + str(exc))
    cases, p = study.fixtures()
    for case in cases:
        saved = sessions.get(case["name"])
        if saved is None:
            errors.append("missing private session " + case["name"])
            continue
        key = saved["call_keys"][0]
        try:
            assert records[key]["request"] == request_for(protocol["model"], case["messages"], case["seed"])
            expected = dict(private_score(records[key], case), case=case["name"], expected=case["expected"],
                            call_keys=[key], protocol_hash=ph)
            assert saved == expected
        except (AssertionError, KeyError) as exc:
            errors.append("private replay mismatch " + case["name"] + str(exc))
    episode = sessions.get("episode")
    if episode:
        gate = all(sessions.get(c["name"], {}).get("exact", False) for c in cases)
        if gate:
            replay = Replay(protocol, records, episode["call_keys"])
            expected = dict(study.run_episode(study.EpisodeBackend(replay, None), p), protocol_hash=ph)
            if json.loads(json.dumps(expected)) != episode or replay.position != len(episode["call_keys"]):
                errors.append("episode replay mismatch")
        elif episode != dict(status="not_run", reason="private exact gate failed", call_keys=[], protocol_hash=ph):
            errors.append("episode ran despite private gate failure")
    else:
        errors.append("missing episode terminal record")
    references = [key for row in sessions.values() for key in row["call_keys"]]
    if len(references) != len(set(references)) or set(references) != set(records):
        errors.append("duplicate/missing/unattached raw calls")
    total = sum(row.get("response", {}).get("usage", {}).get("completion_tokens", 0) for row in records.values())
    if len(records) > MAX_CALLS or total > MAX_CALLS * CAP:
        errors.append("batch cap exceeded")
    return dict(protocol_hash=ph, integrity_errors=errors, calls=len(records), generated_tokens=total,
        forced_tokens=sum(r.get("boundary", {}).get("forced_output_tokens", 0) for r in records.values()),
        elapsed_generation_seconds=sum(r.get("elapsed_seconds", 0) for r in records.values()),
        private_exact=sum(sessions.get(c["name"], {}).get("exact", False) for c in cases),
        episode=episode)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--check-tokenization", action="store_true")
    args = parser.parse_args()
    report = audit(args.root)
    if args.check_tokenization:
        from transformers import AutoTokenizer
        protocol = json.loads((args.root / "manifest.json").read_text())["protocol"]
        tokenizer = AutoTokenizer.from_pretrained(protocol["model"], local_files_only=True)
        base = AutoTokenizer.from_pretrained(protocol["base_tokenizer"], local_files_only=True)
        config = json.loads((Path(protocol["model"]) / "generation_config.json").read_text())
        eos = config.get("eos_token_id", tokenizer.eos_token_id)
        eos = set(eos if isinstance(eos, list) else [eos])
        checked = 0
        for path in sorted((args.root / "calls").glob("*.json")):
            try:
                verify_tokenization(json.loads(path.read_text()), tokenizer, base, eos)
                checked += 1
            except (ValueError, KeyError) as exc:
                report["integrity_errors"].append(path.name + ": " + str(exc))
        report["tokenization_records_verified"] = checked
    print(json.dumps(report, indent=2))
    sys.exit(bool(report["integrity_errors"]))
