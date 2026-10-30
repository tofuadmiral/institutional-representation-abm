"""Post-freeze offline packaging for Pivot B; no changes to frozen research.

Export only a terminal, unlocked run. Replay trusted bundled source under Python
-I -S without network, site packages, credentials, or the original checkout.
This is a reproducibility check, not a sandbox for arbitrary downloaded Python.
"""
from __future__ import annotations

import argparse
from collections import Counter
import fcntl
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FORMAT = "paper3-pivot-b-portable-v1"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe(root, relative):
    rel=PurePosixPath(relative)
    require(bool(rel.parts) and not rel.is_absolute() and ".." not in rel.parts
            and "\\" not in relative,"unsafe bundle path")
    target=Path(root).joinpath(*rel.parts)
    require(target.resolve().is_relative_to(Path(root).resolve()),"path escapes bundle")
    require(not any(p.is_symlink() for p in (target,*target.parents)),"symlink in bundle path")
    return target


def credentials(data, secret=None):
    require(not secret or secret.encode() not in data,"credential found; export refused")
    require(not re.search(rb"sk-or-v1-[A-Za-z0-9_-]{24,}",data),"possible API credential")
    require(not re.search(rb"Bearer\s+[A-Za-z0-9_-]{24,}",data),"possible bearer credential")


def verify_bundle(root, expected_protocol=None):
    root=Path(root).resolve()
    metadata=json.loads((root/"bundle.json").read_text())
    require(metadata["format"]==FORMAT,"unknown archive format")
    require(expected_protocol is None or metadata["protocol"]==expected_protocol,"unexpected protocol")
    actual={str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and p != root/"bundle.json"}
    require(actual==set(metadata["files"]),"bundle inventory mismatch")
    for rel,want in metadata["files"].items():
        require(sha(safe(root,rel).read_bytes())==want,"bundle hash mismatch: "+rel)
    return metadata


def failure_summary(run_root):
    """Post-hoc interface diagnostics, never repaired or executed policy actions."""
    sys.path.insert(0,str(ROOT))
    from paper3 import coalition_contracts as game
    stats={}; failures=[]; usage=Counter(); unknown=Counter()
    for path in sorted((Path(run_root)/"calls").glob("*.json")):
        row=json.loads(path.read_text())
        summary=row.get("assessment",{}).get("stream",{})
        tokens=summary.get("usage") or {}
        details=tokens.get("completion_tokens_details") or {}
        for key,value in (("prompt",tokens.get("prompt_tokens")),("completion",tokens.get("completion_tokens")),
                          ("reasoning",details.get("reasoning_tokens"))):
            if type(value) is int and value>=0:usage[key]+=value
            else:unknown[key]+=1
        if row["id"].startswith("gate-"):continue
        index=int(row["id"].rsplit("-",1)[-1])
        stage=("draft" if index==0 else "response" if index<=7 else "final" if index==8
               else "consent" if index<=15 else "first_vote" if index<=22 else "second_vote")
        arm=row["id"].split("-",2)[2].rsplit("-",1)[0]
        cell=stats.setdefault(arm,{})
        counts=cell.setdefault(stage,Counter())
        counts["attempts"]+=1
        raw=row.get("final_content")
        if not row.get("assessment",{}).get("passed") or not isinstance(raw,str):
            counts["technical_or_unavailable"]+=1;continue
        counts["technical_pass"]+=1
        try:
            value=game.parse_action(raw,stage)
            counts["valid_action"]+=1
            if stage in ("draft","response","final"):
                counts["empty_coalition" if not value["coalition"] else "four_member_coalition"]+=1
        except json.JSONDecodeError as exc:
            counts["invalid_json"]+=1
            failures.append(dict(id=row["id"],stage=stage,kind="invalid_json",offset=exc.pos,
                                 line=exc.lineno,column=exc.colno,final_content_sha256=sha(raw.encode())))
        except (ValueError,TypeError,KeyError) as exc:
            counts["invalid_action_schema"]+=1
            failures.append(dict(id=row["id"],stage=stage,kind="invalid_action_schema",
                                 error_type=type(exc).__name__,final_content_sha256=sha(raw.encode())))
    return dict(post_freeze_diagnostic=True,stage_by_arm=stats,failures=failures,
                known_token_totals={k:usage[k] for k in ("prompt","completion","reasoning")},
                attempts_with_unknown_tokens={k:unknown[k] for k in ("prompt","completion","reasoning")},
                caveat="Descriptive interface coverage, not independent samples or a causal mechanism. Invalid outputs are not executed, repaired or assigned a policy outcome. Empty versus nonempty coalition frequencies are conditional on valid observed actions.")


def build(run_root, ledger_root, target, secret=None):
    sys.path.insert(0,str(ROOT))
    from experiments import paper3_coalition_contracts as runner
    from paper3.pivot_b_budget import Ledger
    run_root,ledger_root,target=map(lambda p:Path(p).resolve(),(run_root,ledger_root,target))
    require((run_root/"sessions/terminal.json").is_file(),"not terminal; do not export a live run")
    require(not target.exists(),"destination exists; never overwrite")
    require(not list(run_root.rglob("*.partial")),"partial writes remain")
    with (run_root/"writer.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        ledger=Ledger(ledger_root)
        with ledger.locked():
            report=runner.audit(run_root,ledger_root)
            manifest,protocol=runner.verify(run_root)
            snapshots=json.loads((run_root/"sources.json").read_text())
            content={"code/"+p:text.encode() for p,text in snapshots.items()}
            for prefix,directory in (("run",run_root),("ledger",ledger_root)):
                for p in directory.rglob("*"):
                    require(not p.is_symlink(),"symlink in source data")
                    if p.is_file() and p.suffix==".json":
                        content[prefix+"/"+str(p.relative_to(directory))]=p.read_bytes()
            content["expected_report.json"]=(json.dumps(report,sort_keys=True,indent=2)+"\n").encode()
            content["postfreeze_failure_summary.json"]=(json.dumps(failure_summary(run_root),sort_keys=True,indent=2)+"\n").encode()
            content["code/analysis/paper3_contracts_archive.py"]=Path(__file__).read_bytes()
            content["tools/test_paper3_contracts_archive.py"]=(ROOT/"tests/test_paper3_contracts_archive.py").read_bytes()
    content["README.md"]=(
        "# Pivot B: coalition commitments — offline evidence replay\n\n"
        "Nine selected-fixture discovery episodes, not nine independent population samples. "
        "All assigned arms, failed prefixes, missingness bounds and per-principal outcomes remain. "
        "Automatic vote enforcement is mechanical, not voluntary model compliance.\n\n"
        "Python 3.11+ on macOS/Linux, standard library only. No key, weights, network, "
        "original checkout or site packages required. From this directory run:\n\n"
        "`python3 -I -S code/analysis/paper3_contracts_archive.py . --replay --expected-protocol "+protocol+"`\n\n"
        "The command verifies the inventory and frozen source, replays requests, actions, "
        "billing and outcomes using the original auditor, and compares every report field "
        "with the saved local report. It makes no new inference. Hashes establish consistency, "
        "not model/provider authenticity, fresh-sample reproducibility, or scientific success.\n\n"
        "The archive helper and its tests are post-freeze tools. No experiment, parser, "
        "scoring or original audit source is changed. The frozen source closure is under code/; "
        "the shared ledger is a terminal archival snapshot, not a current account balance. "
        "Prior non-B spending is separate from this new $10 allowance.\n\n"
        "This executes trusted bundled research code and blocks network/child-process audit events. "
        "It is not an arbitrary-code security sandbox; inspect untrusted source before executing.\n"
    ).encode()
    for name,data in content.items():
        safe(target,name);credentials(data,secret)
    metadata=dict(format=FORMAT,protocol=protocol,
                  frozen_source_count=len(manifest["sources"]),
                  post_freeze_tools=["code/analysis/paper3_contracts_archive.py","tools/test_paper3_contracts_archive.py"],
                  files={name:sha(data) for name,data in sorted(content.items())})
    target.mkdir(parents=True,exist_ok=False)
    for name,data in content.items():
        p=safe(target,name);p.parent.mkdir(parents=True,exist_ok=True)
        with p.open("xb") as f:f.write(data)
    with (target/"bundle.json").open("x") as f:json.dump(metadata,f,sort_keys=True,indent=2)
    return metadata


def archive(target,destination):
    target,destination=Path(target).resolve(),Path(destination).absolute()
    metadata=verify_bundle(target)
    require(not destination.exists(),"archive exists; never overwrite")
    require(not destination.is_relative_to(target),"archive cannot be inside bundle")
    with zipfile.ZipFile(destination,"x",compression=zipfile.ZIP_DEFLATED) as z:
        for relative in sorted([*metadata["files"],"bundle.json"]):z.write(safe(target,relative),relative)
    with zipfile.ZipFile(destination) as z:
        require(z.testzip() is None,"ZIP checksum failure")
        require(set(z.namelist())==set(metadata["files"])|{"bundle.json"},"ZIP inventory mismatch")
    return sha(destination.read_bytes())


def offline_guard(event,args):
    if event.startswith(("socket.","urllib.","subprocess.")) or event in ("os.system","os.exec","os.posix_spawn"):
        raise RuntimeError("offline replay forbids network and child processes")


def replay(root,expected_protocol):
    root=Path(root).resolve()
    metadata=verify_bundle(root,expected_protocol)
    sys.dont_write_bytecode=True
    sys.addaudithook(offline_guard)
    sys.path.insert(0,str(root/"code"))
    from experiments import paper3_coalition_contracts as runner
    require(Path(runner.__file__).resolve()==root/"code/experiments/paper3_coalition_contracts.py",
            "replay must run in fresh isolated Python using bundled source")
    require(runner.verify(root/"run")[1]==metadata["protocol"],"frozen coordinator mismatch")
    report=runner.audit(root/"run",root/"ledger")
    expected=json.loads((root/"expected_report.json").read_text())
    require(report==expected,"replay differs from original local report")
    require(failure_summary(root/"run")==json.loads((root/"postfreeze_failure_summary.json").read_text()),
            "post-freeze failure summary differs")
    report["portable_replay"]=dict(protocol=metadata["protocol"],exact_report_match=True,
                                   post_freeze_tools=metadata["post_freeze_tools"])
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root",type=Path)
    parser.add_argument("--ledger",type=Path)
    parser.add_argument("--target",type=Path)
    parser.add_argument("--archive",type=Path)
    parser.add_argument("--replay",action="store_true")
    parser.add_argument("--expected-protocol")
    args=parser.parse_args()
    if args.replay:
        require(args.expected_protocol,"expected protocol required")
        print(json.dumps(replay(args.root,args.expected_protocol),indent=2));return
    require(args.ledger and args.target,"ledger and fresh target required")
    sys.path.insert(0,str(ROOT))
    from experiments import paper3_transport_diagnostic as t
    secret=t.read_key() if (ROOT/".env.local").is_file() else None
    metadata=build(args.root,args.ledger,args.target,secret)
    digest=archive(args.target,args.archive) if args.archive else None
    print(json.dumps(dict(protocol=metadata["protocol"],files=len(metadata["files"]),sha256=digest)))


if __name__=="__main__":main()
