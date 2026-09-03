from __future__ import annotations
from datetime import datetime,timezone
from hashlib import sha256
import json,subprocess,zipfile
from pathlib import Path,PurePosixPath

PACKAGE_VERSION=1
SECRET_PARTS={".git",".venv","__pycache__","auth","playwright","cookies","tokens"}
SECRET_NAMES={".env","secrets.toml","storage_state.json"}
MIGRATION_ROOTS=("data/models/season_2526","data/models/season_2627","data/quality/season_2526","data/quality/season_2627","data/reference","data/seasons/2526","data/raw/fantrax","data/raw/whoscored","data/raw/understat","data/raw/soccerdata")
CLIENT_ROOTS=("data/models/season_2526","data/models/season_2627","data/quality/season_2627","data/reference","data/seasons/2526")

def sensitive(path:PurePosixPath)->bool:
    lowered={part.lower() for part in path.parts};return path.name.lower() in SECRET_NAMES or bool(lowered&SECRET_PARTS) or any("secret" in part or "credential" in part for part in lowered)
def category(path:PurePosixPath)->str:
    text=path.as_posix();return "PROVIDER_CACHE" if text.startswith("data/raw/") else "DERIVED_MODELS" if text.startswith("data/models/") else "QUALITY_AND_MANIFESTS" if text.startswith("data/quality/") else "ARCHIVAL_NON_RUNTIME" if text.startswith("data/seasons/") else "REFERENCE_DATA"
def git_commit(root:Path)->str|None:
    result=subprocess.run(["git","rev-parse","HEAD"],cwd=root,capture_output=True,text=True,check=False);return result.stdout.strip() or None
def collect(root:Path,package_type:str)->list[Path]:
    roots=MIGRATION_ROOTS if package_type=="migration" else CLIENT_ROOTS;files=[]
    for relative in roots:
        base=root/relative
        if base.is_file():files.append(base)
        elif base.exists():files.extend(x for x in base.rglob("*") if x.is_file())
    output=[]
    for path in sorted(set(files),key=lambda x:x.relative_to(root).as_posix()):
        rel=PurePosixPath(path.relative_to(root).as_posix())
        if sensitive(rel):continue
        output.append(path)
    return output
def build_package(root:Path,target:Path,*,package_type:str="migration",checkpoint:str="data/quality/season_2627/gw2_laptop_migration_checkpoint_repaired.json")->dict:
    root=root.resolve();target=target.resolve();files=collect(root,package_type)
    if not (root/checkpoint).exists():raise FileNotFoundError(checkpoint)
    records=[]
    for path in files:
        rel=PurePosixPath(path.relative_to(root).as_posix());records.append({"relative_path":rel.as_posix(),"category":category(rel),"size":path.stat().st_size,"sha256":sha256(path.read_bytes()).hexdigest(),"required_or_optional":"required" if rel.as_posix()==checkpoint or rel.as_posix().startswith("data/models/") else "optional","reason":"Runtime state or incremental provider cache","source_checkpoint":checkpoint})
    checkpoint_mtime=(root/checkpoint).stat().st_mtime
    manifest={"package_type":package_type,"package_version":PACKAGE_VERSION,"created_at":datetime.fromtimestamp(checkpoint_mtime,timezone.utc).isoformat(),"season":"2627","current_period":2,"source_machine_role":"commissioner","source_checkpoint":checkpoint,"git_commit":git_commit(root),"schema_compatibility":{"minimum_package_version":1,"maximum_package_version":1},"methodology_versions":{"team_tactical":"team_tactical_v1"},"files":records}
    target.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(target,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path,record in zip(files,records):
            info=zipfile.ZipInfo(record["relative_path"],(2026,9,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(info,path.read_bytes())
        info=zipfile.ZipInfo("desktop_migration_manifest.json",(2026,9,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(info,json.dumps(manifest,indent=2).encode())
    validate_package(target)
    (target.parent/f"{target.stem}_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    return manifest
def validate_package(package:Path)->dict:
    with zipfile.ZipFile(package) as archive:
        manifest=json.loads(archive.read("desktop_migration_manifest.json"));names=set(archive.namelist())
        if manifest.get("package_version")!=PACKAGE_VERSION:raise ValueError("Unsupported package version")
        for record in manifest["files"]:
            rel=PurePosixPath(record["relative_path"])
            if rel.is_absolute() or ".." in rel.parts or sensitive(rel):raise ValueError(f"Unsafe package path: {rel}")
            if rel.as_posix() not in names:raise FileNotFoundError(rel.as_posix())
            if sha256(archive.read(rel.as_posix())).hexdigest()!=record["sha256"]:raise ValueError(f"Hash mismatch: {rel}")
        return manifest
def import_package(package:Path,root:Path,*,check:bool=False)->dict:
    manifest=validate_package(package);warnings=[];commit=git_commit(root)
    if commit and manifest.get("git_commit") and commit!=manifest["git_commit"]:warnings.append("Package source commit differs from desktop code commit")
    overwritten=[]
    with zipfile.ZipFile(package) as archive:
        for record in manifest["files"]:
            rel=PurePosixPath(record["relative_path"]);destination=(root/Path(*rel.parts)).resolve()
            if not destination.is_relative_to(root.resolve()):raise ValueError(f"Path traversal rejected: {rel}")
            if destination.exists():overwritten.append(rel.as_posix())
            if not check:destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(archive.read(rel.as_posix()))
    label="would_overwrite" if check else "overwritten"
    return {"status":"VALID" if check else "IMPORTED","files":len(manifest["files"]),f"{label}_count":len(overwritten),f"{label}_sample":overwritten[:20],"warnings":warnings}
