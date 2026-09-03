"""Central provider maturity and cache-first recheck planning."""
from __future__ import annotations
from datetime import datetime,timezone,timedelta
from pathlib import Path
import json

MATURITY_STATES=("LIVE","PRELIMINARY","COMPLETE_PENDING_CORRECTIONS","STABLE","FINALIZED")
RECHECK_AFTER={"whoscored":timedelta(hours=24),"understat":timedelta(hours=24)}

def due(maturity:str,retrieved_at:str|None,provider:str,*,now:datetime|None=None)->bool:
    if maturity=="STABLE":return False
    if maturity not in ("PRELIMINARY","COMPLETE_PENDING_CORRECTIONS"):return maturity not in ("FINALIZED",)
    if not retrieved_at:return True
    stamp=datetime.fromisoformat(str(retrieved_at).replace("Z","+00:00"));return (now or datetime.now(timezone.utc))-stamp>=RECHECK_AFTER.get(provider,timedelta())

def provider_plan(provider:str,metadata:list[dict],expected:int)->dict:
    present=len(metadata);preliminary=sum(str(x.get("maturity","PRELIMINARY")).upper()=="PRELIMINARY" for x in metadata);stable=sum(str(x.get("maturity","")).upper()=="STABLE" for x in metadata)
    return {"provider":provider,"expected":expected,"present":present,"missing":max(0,expected-present),"preliminary":preliminary,"stable":stable,"due_for_recheck":sum(due(str(x.get("maturity","PRELIMINARY")).upper(),x.get("retrieved_at"),provider) for x in metadata)}

def promote_if_valid(current:Path,new:Path,*,valid:bool)->str:
    """Promotion guard: failed candidates never replace accepted evidence."""
    if not valid:return "RETAINED_PREVIOUS"
    if current.exists() and new.exists() and current.read_bytes()==new.read_bytes():return "NO_CHANGE"
    return "CHANGED_VALIDATED"
