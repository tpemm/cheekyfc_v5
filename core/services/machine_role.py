"""Central one-writer policy for authoritative live-data operations."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

DENIAL_MESSAGE="Authoritative live-data acquisition is disabled on this machine. Run the commissioner refresh from the designated commissioner desktop."

class MachineRoleError(PermissionError):pass

@dataclass(frozen=True)
class MachineRole:
    role:str
    commissioner_refresh_enabled:bool

def _local_config() -> dict[str, str]:
    path = Path(__file__).parents[2] / "config" / "local_machine.env"
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    return values

def get_machine_role(env:dict[str,str]|None=None)->MachineRole:
    values = {**_local_config(), **os.environ} if env is None else env
    role=str(values.get("FANTRAX_MACHINE_ROLE","commissioner")).strip().lower()
    if role not in {"commissioner","client"}:raise ValueError("FANTRAX_MACHINE_ROLE must be commissioner or client")
    raw=str(values.get("COMMISSIONER_REFRESH_ENABLED","true" if role=="commissioner" else "false")).strip().lower()
    if raw not in {"1","0","true","false","yes","no","on","off"}:raise ValueError("COMMISSIONER_REFRESH_ENABLED must be boolean")
    return MachineRole(role,raw in {"1","true","yes","on"})

def commissioner_refresh_enabled(env:dict[str,str]|None=None)->bool:
    state=get_machine_role(env);return state.role=="commissioner" and state.commissioner_refresh_enabled

def require_commissioner_writer(operation_name:str,env:dict[str,str]|None=None)->None:
    if not commissioner_refresh_enabled(env):raise MachineRoleError(f"{DENIAL_MESSAGE} Operation: {operation_name}")

def describe_machine_role(env:dict[str,str]|None=None)->dict[str,object]:
    state=get_machine_role(env);return {"role":state.role,"commissioner_refresh_enabled":commissioner_refresh_enabled(env),"authoritative_writes_allowed":commissioner_refresh_enabled(env)}
