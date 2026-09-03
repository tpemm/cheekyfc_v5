"""Bounded direct-match diagnostic capture using soccerdata's working driver."""
from __future__ import annotations
import hashlib,json,time
from datetime import datetime,timezone
from pathlib import Path

def capture_direct_match(match_id:int,target_dir:Path,page_timeout:int=30)->dict:
    import soccerdata as sd
    target_dir.mkdir(parents=True,exist_ok=True)
    url=f"https://www.whoscored.com/Matches/{match_id}/Live"
    reader=sd.WhoScored(leagues="ENG-Premier League",seasons="2526",no_cache=False,
                        data_dir=target_dir.parent.parent/"_direct_adapter",headless=False)
    driver=reader._driver
    result={"whoscored_match_id":match_id,"url":url,"captured_at":datetime.now(timezone.utc).isoformat()}
    try:
        driver.set_page_load_timeout(page_timeout); driver.set_script_timeout(10); driver.get(url)
        result.update({"final_url":driver.current_url,"page_title":driver.title,
                       "document_ready_state":driver.execute_script("return document.readyState"),
                       "javascript_available":driver.execute_script("return 6*7")==42})
        source=driver.page_source or ""; result["html_available"]=bool(source)
        result["whoscored_content_present"]="matchCentreData" in source or "match-centre" in source.casefold()
        if source:
            encoded=source.encode("utf-8"); (target_dir/"page.html").write_bytes(encoded)
            result["page_checksum"]=hashlib.sha256(encoded).hexdigest()
        payload=driver.execute_script("return require.config.params['args'].matchCentreData")
        result["embedded_json_available"]=isinstance(payload,dict) and bool(payload.get("events"))
        if result["embedded_json_available"]:
            encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2).encode("utf-8")
            (target_dir/"embedded_payload.json").write_bytes(encoded)
            result["embedded_checksum"]=hashlib.sha256(encoded).hexdigest(); result["event_count"]=len(payload["events"])
    except Exception as exc:
        result["error"]=f"{type(exc).__name__}: {exc}"
    finally:
        try: driver.quit()
        except Exception: pass
    (target_dir/"browser_diagnostic.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result

def capture_direct_matches(matches:list[dict],base_dir:Path,page_timeout:int=30)->list[dict]:
    """Capture known provider IDs in one browser session; isolate each failure."""
    import soccerdata as sd
    reader=sd.WhoScored(leagues="ENG-Premier League",seasons="2526",no_cache=False,
                        data_dir=base_dir/"_direct_adapter",headless=False)
    driver=reader._driver; driver.set_page_load_timeout(page_timeout); driver.set_script_timeout(10)
    results=[]
    try:
        for item in matches:
            started=time.perf_counter(); canonical=int(item["understat_match_id"]); match_id=int(item["whoscored_match_id"])
            target=base_dir/f"match_{canonical}"; target.mkdir(parents=True,exist_ok=True)
            url=f"https://www.whoscored.com/Matches/{match_id}/Live"
            result={**item,"url":url,"captured_at":datetime.now(timezone.utc).isoformat()}
            try:
                driver.get(url); source=driver.page_source or ""
                payload=driver.execute_script("return require.config.params['args'].matchCentreData")
                if not isinstance(payload,dict) or not payload.get("events"): raise ValueError("missing matchCentreData events")
                encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2).encode("utf-8")
                from analytics.advanced_match_poc import safe_write_raw
                checksum=safe_write_raw(payload,target/"raw_match.json")
                for name,data in (("embedded_payload.json",encoded),("page.html",source.encode("utf-8"))):
                    path=target/name
                    if not path.exists():
                        temp=path.with_suffix(path.suffix+".tmp"); temp.write_bytes(data); temp.replace(path)
                native=base_dir/"_soccerdata_native"/"events"/"ENG-Premier League_2526"/f"{match_id}.json"
                native.parent.mkdir(parents=True,exist_ok=True)
                if not native.exists():
                    temp=native.with_suffix(".json.tmp"); temp.write_bytes(encoded); temp.replace(native)
                result.update({"status":"acquired","final_url":driver.current_url,"page_title":driver.title,
                  "document_ready_state":driver.execute_script("return document.readyState"),"event_count":len(payload["events"]),
                  "player_count":len(payload.get("playerIdNameDictionary",{})),"checksum":checksum,
                  "page_checksum":hashlib.sha256(source.encode()).hexdigest()})
            except Exception as exc: result.update({"status":"error","error":f"{type(exc).__name__}: {exc}"})
            result["elapsed_seconds"]=round(time.perf_counter()-started,3)
            (target/"metadata.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
            (target/"browser_diagnostic.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
            results.append(result)
    finally:
        try: driver.quit()
        except Exception: pass
    return results
