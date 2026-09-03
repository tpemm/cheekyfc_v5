#!/usr/bin/env python3
"""Sanitized local diagnostic for the authenticated Fantrax weekly export UI."""
from __future__ import annotations
import argparse,json,os,sys
from uuid import uuid4
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fantrax.live.config import load_live_season_config
from fantrax.live.weekly_acquisition import _auth_path

def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--period',type=int,default=1);p.add_argument('--headed',action='store_true');p.add_argument('--download',action='store_true');p.add_argument('--team-id');a=p.parse_args()
    from playwright.sync_api import sync_playwright
    config=load_live_season_config();league=config.require_league_id();auth=_auth_path(ROOT)
    if not auth.exists():print('Fantrax authentication required');return 2
    executable=os.environ.get('FANTRAX_BROWSER_EXECUTABLE') or r'C:\Program Files\Google\Chrome\Application\chrome.exe';seen=[]
    with sync_playwright() as pw:
        download_dir=ROOT/'data/raw/fantrax/2627/diagnostic_downloads'/uuid4().hex[:8];download_dir.mkdir(parents=True,exist_ok=True)
        browser=pw.chromium.launch(headless=not a.headed,executable_path=executable,downloads_path=str(download_dir));context=browser.new_context(storage_state=str(auth),accept_downloads=True);page=context.new_page()
        def observed(response):
            split=urlsplit(response.url)
            if split.hostname and 'fantrax.com' in split.hostname:seen.append({'method':response.request.method,'status':response.status,'resource_type':response.request.resource_type,'url':f'{split.scheme}://{split.netloc}{split.path}'})
        from fantrax.live.weekly_acquisition import all_player_url,roster_url,sha256_bytes
        page.on('response',observed);url=roster_url(league,a.period,a.team_id) if a.team_id else all_player_url(league,a.period);page.goto(url,wait_until='domcontentloaded',timeout=60000);page.wait_for_timeout(5000)
        controls=page.locator('button,[role=button],a').evaluate_all("""els => els.map((e,i)=>({i,tag:e.tagName,text:(e.innerText||'').trim().slice(0,120),title:e.getAttribute('title'),aria:e.getAttribute('aria-label'),describedby:e.getAttribute('aria-describedby'),testid:e.getAttribute('data-testid'),classes:(e.className||'').toString().slice(0,180),html:e.outerHTML.slice(0,500)})).filter(x=>{const r=els[x.i].getBoundingClientRect();return r.width>0&&r.height>0})""")
        icon_controls=[x for x in controls if any(token in json.dumps(x).lower() for token in ('download','csv','export','file_download','arrow_downward','save_alt'))]
        screenshot=ROOT/f"data/quality/season_2627/fantrax_{'team' if a.team_id else 'players'}_controls.png";page.screenshot(path=str(screenshot),full_page=True)
        result={'authenticated':page.get_by_text('Login',exact=True).count()==0,'title':page.title(),'final_path':urlsplit(page.url).path,'download_controls':icon_controls,'visible_controls':controls,'screenshot':str(screenshot.relative_to(ROOT)),'fantrax_requests':list({json.dumps(x,sort_keys=True):x for x in seen}.values())}
        if a.download:
            downloads=[];page.on('download',lambda item:downloads.append(item))
            dismiss=page.get_by_role('button',name='Never',exact=True)
            if dismiss.count():dismiss.click();page.wait_for_timeout(500)
            page.evaluate("""() => { window.__fantraxDiag={anchors:[],blobs:[]}; const ac=HTMLAnchorElement.prototype.click; HTMLAnchorElement.prototype.click=function(){window.__fantraxDiag.anchors.push({download:this.download,href:(this.href||'').slice(0,160)});return ac.call(this)}; const co=URL.createObjectURL; URL.createObjectURL=function(blob){window.__fantraxDiag.blobs.push(blob);return co.call(URL,blob)} }""")
            trigger=page.locator('button[mattooltip="Download all as CSV"]').first;trigger.click();page.wait_for_timeout(10000)
            result['post_click_controls']=page.locator('[role=menu],[role=menuitem],button').evaluate_all("els=>els.map(e=>({text:(e.innerText||'').trim().slice(0,120),role:e.getAttribute('role'),title:e.getAttribute('title'),aria:e.getAttribute('aria-label'),tooltip:e.getAttribute('mattooltip')})).filter(x=>JSON.stringify(x).toLowerCase().match(/download|export|csv/))")
            result['fantrax_requests_after_click']=list({json.dumps(x,sort_keys=True):x for x in seen}.values())
            client=page.evaluate("""async()=>({anchors:window.__fantraxDiag.anchors,blobs:await Promise.all(window.__fantraxDiag.blobs.map(async b=>({type:b.type||typeof b,size:b.size||null,kind:b?.constructor?.name,bytes:b instanceof Blob?Array.from(new Uint8Array(await new Response(b).arrayBuffer())):[]})))})""");result['client_export']={'anchors':client['anchors'],'blobs':[{'type':b['type'],'size':b['size'],'kind':b['kind']} for b in client['blobs']]}
            disk_files=[p for p in download_dir.glob('*') if p.is_file() and not p.name.endswith('.crdownload')]
            if downloads:
                item=downloads[0];content=Path(item.path()).read_bytes();canary=ROOT/f"data/raw/fantrax/2627/canary/{'team_'+a.team_id if a.team_id else 'all_players'}_gw{a.period}.csv";canary.parent.mkdir(parents=True,exist_ok=True);canary.write_bytes(content)
                result['download']={'suggested_filename':item.suggested_filename,'bytes':len(content),'sha256':sha256_bytes(content),'path':str(canary.relative_to(ROOT))}
            elif disk_files:
                content=disk_files[0].read_bytes();canary=ROOT/f"data/raw/fantrax/2627/canary/{'team_'+a.team_id if a.team_id else 'all_players'}_gw{a.period}.csv";canary.parent.mkdir(parents=True,exist_ok=True);canary.write_bytes(content)
                result['download']={'mechanism':'CONTROLLED_BROWSER_DIRECTORY','suggested_filename':disk_files[0].name,'bytes':len(content),'sha256':sha256_bytes(content),'path':str(canary.relative_to(ROOT))}
            elif client['blobs'] and client['blobs'][0]['bytes']:
                content=bytes(client['blobs'][0]['bytes']);canary=ROOT/f"data/raw/fantrax/2627/canary/{'team_'+a.team_id if a.team_id else 'all_players'}_gw{a.period}.csv";canary.parent.mkdir(parents=True,exist_ok=True);canary.write_bytes(content)
                result['download']={'mechanism':'CLIENT_BLOB','bytes':len(content),'sha256':sha256_bytes(content),'path':str(canary.relative_to(ROOT))}
            else:result['download']={'status':'NO_BROWSER_DOWNLOAD_EVENT'}
        out=ROOT/'data/quality/season_2627/fantrax_weekly_export_diagnostic.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));context.close();browser.close();return 0 if result['authenticated'] else 2
if __name__=='__main__':raise SystemExit(main())
