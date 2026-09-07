from types import SimpleNamespace

import pytest

from integrations.whoscored.session_browser import BrowserSessionError, check_driver, create_reader


def fake_driver(*, code=None, listening=True, session="local"):
    service=SimpleNamespace(process=SimpleNamespace(poll=lambda:code),is_connectable=lambda:listening,
                            path="chromedriver.exe",port=12345)
    return SimpleNamespace(capabilities={},service=service,session_id=session,set_page_load_timeout=lambda n:None,
                           set_script_timeout=lambda n:None,execute_script=lambda text:1,quit=lambda:None)


@pytest.mark.parametrize("kwargs",[{"code":1},{"listening":False},{"session":None}])
def test_unhealthy_driver_fails_immediately(kwargs):
    with pytest.raises(BrowserSessionError):
        check_driver(fake_driver(**kwargs))


def test_owned_driver_health():
    check_driver(fake_driver())


@pytest.fixture
def stack(tmp_path,monkeypatch):
    import soccerdata as sd
    from selenium import webdriver
    from integrations.whoscored import session_browser
    binary=tmp_path/"chrome.exe";binary.write_text("fixture")
    def locate():
        if not binary.exists():raise BrowserSessionError("Install Chrome")
        return str(binary)
    monkeypatch.setattr(session_browser,"installed_chrome",locate)
    driver=fake_driver()
    class Base:
        def __init__(self,**kwargs):
            assert self.__class__.__name__=="WhoScored"
            assert kwargs["path_to_browser"]==str(binary)
            self.headers=None
            self._driver=self._init_webdriver()
            self.rate_limit=0
        def _init_webdriver(self):
            pytest.fail("soccerdata UC startup must not be called")
    monkeypatch.setattr(sd,"WhoScored",Base)
    calls=[]
    def chrome(*,options):
        assert options.binary_location==str(binary)
        assert options.arguments==[]
        calls.append(options)
        return driver
    monkeypatch.setattr(webdriver,"Chrome",chrome)
    return driver,calls,binary


def test_uses_standard_chrome_with_selenium_manager(stack,tmp_path):
    driver,calls,_=stack
    reader=create_reader(season="2627",data_dir=tmp_path)
    assert reader._driver is driver and len(calls)==1


def test_missing_browser_is_actionable(stack,tmp_path):
    _,_,binary=stack
    binary.unlink()
    with pytest.raises(BrowserSessionError,match="Install Chrome"):
        create_reader(season="2627",data_dir=tmp_path)


def test_startup_failure_closes_driver_and_is_not_swallowed(stack,tmp_path):
    driver,calls,_=stack;closed=[]
    driver.service.process.poll=lambda:1
    driver.quit=lambda:closed.append(True)
    with pytest.raises(BrowserSessionError,match="code=1"):
        create_reader(season="2627",data_dir=tmp_path)
    assert closed==[True] and len(calls)==1


def test_navigation_failure_is_not_retried_or_masked(stack,tmp_path):
    driver,_,_=stack;calls=[]
    def get(url):
        calls.append(url)
        raise ConnectionRefusedError("local driver refused connection")
    driver.get=get
    reader=create_reader(season="2627",data_dir=tmp_path)
    with pytest.raises(ConnectionRefusedError,match="local driver"):
        reader._download_and_save("http://localhost/fixture")
    assert calls==["http://localhost/fixture"]


@pytest.mark.parametrize("message,expected",[("WinError 10061",True),("ConnectionResetError(10054, 'closed')",True),("invalid session id",True),("disconnected: not connected to DevTools",True),("payload club identity mismatch",False),("Google Chrome is missing",False)])
def test_recovery_only_for_dead_sessions(message,expected):
    from integrations.whoscored.session_browser import dead_session_error
    assert dead_session_error(RuntimeError(message)) is expected


def test_controller_does_not_multiply_live_recovery(tmp_path):
    import pandas as pd
    from integrations.whoscored.controller import acquire
    calls=[]
    row={"whoscored_match_id":101,"canonical_match_id":"m1"}
    def worker(*args):
        calls.append(True)
        return dict(seconds=0,timed_out=False,returncode=1,stderr="dead session")
    result=acquire(pd.DataFrame([row]),root=tmp_path,manifest_path=tmp_path/"manifest.csv",season="2627",retries=99,worker=worker)
    assert len(calls)==1 and result.iloc[0].status=="FAILED"


@pytest.mark.parametrize("failures,expected",[(0,[101,102]),(1,[101,101,102]),(2,[101,101,102])])
def test_live_children_sequential_isolated_and_bounded(tmp_path,monkeypatch,failures,expected):
    import json
    import pandas as pd
    from integrations.whoscored import controller
    events=[];valid={100};attempts={};active=[]
    class Child:
        def __init__(self,command,**kwargs):
            assert not active, "previous child must exit before next launch"
            self.mid=int(command[command.index('--match-id')+1]);self.pid=len(events)+1000
            active.append(self);events.append(('start',self.mid));self.returncode=None
        def wait(self,timeout):
            attempts[self.mid]=attempts.get(self.mid,0)+1
            failed=self.mid==101 and attempts[self.mid]<=failures
            self.returncode=1 if failed else 0
            target=tmp_path/f'data/raw/whoscored/2627/poc/match_{self.mid}';target.mkdir(parents=True,exist_ok=True)
            (target/'metadata.json').write_text(json.dumps({'error_message':'WinError 10061'} if failed else {'status':'acquired'}))
            if not failed:valid.add(self.mid)
            events.append(('exit',self.mid));active.remove(self)
            return self.returncode
    monkeypatch.setattr(controller.subprocess,'Popen',Child)
    def checked(base,row):
        ok=row['whoscored_match_id'] in valid
        return dict(cache_valid=ok,error_type=None if ok else 'ConnectionRefusedError',error_message=None if ok else 'WinError 10061',payload_hash=None)
    monkeypatch.setattr(controller,'validate_cache',checked)
    rows=pd.DataFrame([{'whoscored_match_id':i} for i in (100,101,102)])
    result=controller.acquire(rows,root=tmp_path,manifest_path=tmp_path/'manifest.csv',season='2627',retries=99,retry_delay=0)
    assert events==[event for mid in expected for event in [('start',mid),('exit',mid)]]
    assert result.iloc[0].status=='CACHE_HIT'
    assert result.iloc[-1].status=='ACQUIRED'
    if failures==2:
        assert result.iloc[1].status=='FAILED'
        assert result.iloc[1].error_message=='WinError 10061'
        assert len(result.iloc[1].child_attempts)==2
    assert len(json.loads((tmp_path/'data/raw/whoscored/2627/poc/match_101/acquisition_attempts.json').read_text()))==min(failures+1,2)
