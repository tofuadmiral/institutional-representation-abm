"""Post-freeze, terminal-only archive/replay for B's format instrument."""
import argparse
import fcntl
import json
from pathlib import Path
import sys

# Disable bytecode before loading the helper, not merely before the runner.
# Otherwise an isolated first replay would itself change the bundle inventory.
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]


def helpers():
    sys.path.insert(0,str(ROOT))
    # Namespace import avoids the unrelated analysis package initializer.
    import importlib.util
    spec=importlib.util.spec_from_file_location("b_archive_helpers",ROOT/"analysis/paper3_contracts_archive.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def build(run,ledger,target,secret=None):
    h=helpers()
    from experiments import paper3_contracts_format as r
    run,ledger,target=map(lambda p:Path(p).resolve(),(run,ledger,target))
    h.require((run/"sessions/terminal.json").is_file(),"not terminal")
    h.require(not target.exists(),"destination exists")
    h.require(not list(run.rglob("*.partial")),"partial write")
    with (run/"writer.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with r.Ledger(ledger).locked():
            report=r.audit(run,ledger);manifest,protocol=r.verify(run)
            snapshots=r.load(run/"sources.json")
            content={"code/"+p:v.encode() for p,v in snapshots.items()}
            for prefix,directory in (("run",run),("ledger",ledger)):
                for p in directory.rglob("*"):
                    h.require(not p.is_symlink(),"symlink in source")
                    if p.is_file() and p.suffix==".json":content[prefix+"/"+str(p.relative_to(directory))]=p.read_bytes()
            content["expected_report.json"]=(json.dumps(report,sort_keys=True,indent=2)+"\n").encode()
    postfreeze=["analysis/paper3_contracts_format_archive.py","analysis/paper3_contracts_archive.py"]
    for p in postfreeze:content["code/"+p]=(ROOT/p).read_bytes()
    content["tools/test_paper3_contracts_format_archive.py"]=(ROOT/"tests/test_paper3_contracts_format_archive.py").read_bytes()
    content["README.md"]=("# B compound-action format diagnostic\n\n"
        "All sixteen fixed assignments, failures and unresolved cost reservations are retained. "
        "No historical answer is repaired/replaced; this is engineering feasibility, not an institutional effect.\n\n"
        "Extract into a fresh directory and run (Python3.11+, macOS/Linux standard library):\n\n"
        "`python3 -I -S code/analysis/paper3_contracts_format_archive.py . --replay --expected-protocol "+protocol+"`\n\n"
        "Exact original audit replay, no network/key/weights/original checkout. Review trusted code first; "
        "hashes prove consistency, not provider authenticity. The two archive helpers and packaging test "
        "are explicitly post-freeze. Shared ledger is an archival snapshot, not current account balance.\n").encode()
    for rel,data in content.items():h.safe(target,rel);h.credentials(data,secret)
    metadata=dict(format=h.FORMAT,experiment_family="b_compound_format",protocol=protocol,
        frozen_source_count=len(manifest["sources"]),post_freeze_tools=["code/"+p for p in postfreeze],
        files={rel:h.sha(data) for rel,data in sorted(content.items())})
    target.mkdir(parents=True,exist_ok=False)
    for rel,data in content.items():
        p=h.safe(target,rel);p.parent.mkdir(parents=True,exist_ok=True)
        with p.open("xb") as f:f.write(data)
    with (target/"bundle.json").open("x") as f:json.dump(metadata,f,sort_keys=True,indent=2)
    return metadata


def replay(root,expected):
    h=helpers();root=Path(root).resolve();metadata=h.verify_bundle(root,expected)
    h.require(metadata["experiment_family"]=="b_compound_format","wrong experiment")
    sys.dont_write_bytecode=True;sys.addaudithook(h.offline_guard)
    sys.path.insert(0,str(root/"code"))
    from experiments import paper3_contracts_format as r
    h.require(Path(r.__file__).resolve()==root/"code/experiments/paper3_contracts_format.py","isolated bundled runner required")
    h.require(r.verify(root/"run")[1]==expected,"protocol changed")
    report=r.audit(root/"run",root/"ledger")
    h.require(report==json.loads((root/"expected_report.json").read_text()),"original audit differs")
    report["portable_replay"]=dict(exact_report_match=True,protocol=expected,post_freeze_tools=metadata["post_freeze_tools"])
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("root",type=Path)
    parser.add_argument("--ledger",type=Path);parser.add_argument("--target",type=Path)
    parser.add_argument("--archive",type=Path);parser.add_argument("--replay",action="store_true")
    parser.add_argument("--expected-protocol");args=parser.parse_args();h=helpers()
    if args.replay:
        h.require(args.expected_protocol,"expected protocol required")
        print(json.dumps(replay(args.root,args.expected_protocol),indent=2));return
    h.require(args.ledger and args.target and args.archive,"export paths required")
    from experiments import paper3_transport_diagnostic as t
    secret=t.read_key() if (ROOT/".env.local").is_file() else None
    m=build(args.root,args.ledger,args.target,secret)
    digest=h.archive(args.target,args.archive)
    print(json.dumps(dict(protocol=m["protocol"],files=len(m["files"]),sha256=digest)))


if __name__=="__main__":main()
