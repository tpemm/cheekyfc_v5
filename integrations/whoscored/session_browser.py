"""Owned, health-checked soccerdata/standard Selenium browser sessions."""
from __future__ import annotations

import os
import shutil
import io
import json
import time
from pathlib import Path


class BrowserSessionError(RuntimeError):
    pass


def dead_session_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(token in message for token in (
        "winerror 10061", "connection refused", "actively refused", "invalid session id",
        "connectionreseterror(10054", "connection reset by peer",
        "disconnected", "chrome not reachable", "chromedriver process exited",
        "chromedriver is not listening", "did not create a browser session",
    ))


def session_evidence(reader) -> dict:
    # Do not query a dead WebDriver endpoint while collecting diagnostics.
    driver = getattr(reader, "_driver", None)
    service = getattr(driver, "service", None)
    process = getattr(service, "process", None)
    evidence = dict(getattr(reader, "browser_evidence", {}))
    evidence.update(session_id=getattr(driver, "session_id", None),
                    driver_pid=getattr(process, "pid", None),
                    driver_returncode=process.poll() if process else None)
    try:
        import psutil
        pid = getattr(driver, "browser_pid", None)
        evidence.update(chrome_pid=pid, chrome_running=psutil.pid_exists(pid) if pid else None)
    except Exception:
        evidence["chrome_running"] = None
    return evidence


def dispose_reader(reader) -> None:
    if reader is not None:
        try:
            reader._driver.quit()
        except Exception:
            pass


def read_events_once(factory, *, match_id: int, live: bool, attempts: list) -> None:
    reader = None
    record = {"attempt": 1, "recovery_count": 0, "match_id": match_id}
    attempts.append(record)
    try:
        reader = factory()
        check_driver(reader._driver)
        record["browser"] = getattr(reader, "browser_startup", {})
        reader.read_events(match_id=match_id, output_fmt=None, force_cache=True,
                           on_error="raise", live=live)
        record["status"] = "DOWNLOADED"
    except Exception as exc:
        record.update(status="FAILED", error_type=type(exc).__name__,
                      error_message=str(exc), evidence=session_evidence(reader))
        raise
    finally:
        dispose_reader(reader)


def check_driver(driver) -> None:
    service = driver.service
    code = service.process.poll()
    if code is not None:
        raise BrowserSessionError(f"ChromeDriver process exited: code={code}, executable={service.path}")
    if not service.is_connectable():
        raise BrowserSessionError(f"ChromeDriver is not listening on its owned port {service.port}")
    if not driver.session_id:
        raise BrowserSessionError("ChromeDriver did not create a browser session")


def installed_chrome() -> str:
    candidates = [Path(os.environ.get(key, "")) / "Google/Chrome/Application/chrome.exe"
                  for key in ("PROGRAMFILES", "LOCALAPPDATA", "PROGRAMFILES(X86)")]
    found = shutil.which("chrome")
    if found:
        candidates.append(Path(found))
    for path in candidates:
        if path.is_file():
            return str(path)
    raise BrowserSessionError("Google Chrome is missing. Install Chrome, then rerun the desktop command from the project .venv.")


def create_reader(*, season: str, data_dir: Path):
    import soccerdata as sd
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    binary = installed_chrome()

    # soccerdata uses the concrete class name as its provider registry key.
    class WhoScored(sd.WhoScored):
        def _init_webdriver(self):
            driver = None
            try:
                options = Options()
                options.binary_location = binary
                driver = webdriver.Chrome(options=options)
                if self.headers:
                    driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {"headers": self.headers})
                self.browser_startup = {"driver_path": driver.service.path,
                                        "browser_version": driver.capabilities.get("browserVersion"),
                                        "driver_version": driver.capabilities.get("chrome", {}).get("chromedriverVersion")}
                driver.browser_pid = driver.capabilities.get("goog:processID")
                check_driver(driver)
                driver.set_page_load_timeout(30)
                driver.set_script_timeout(10)
                driver.execute_script("return 1")
                return driver
            except Exception as exc:
                if driver is not None:
                    try: driver.quit()
                    except Exception: pass
                # soccerdata suppresses WebDriverException during construction.
                # Use an explicit error it cannot swallow.
                raise BrowserSessionError(f"WhoScored browser startup failed: {type(exc).__name__}: {exc}") from exc

        def _download_and_save(self, url, filepath=None, var=None):
            # The match worker owns recovery. Do not spend five SDK retries on a
            # dead local service or hide its original exception until timeout.
            self.browser_evidence = {"requested_url": url, "phase": "pre_navigation"}
            check_driver(self._driver)
            self.browser_evidence["phase"] = "navigation"
            self._driver.get(url)
            self.browser_evidence.update(last_successful_command="get", phase="page_wait")
            check_driver(self._driver)
            time.sleep(self.rate_limit)
            self.browser_evidence["phase"] = "page_source"
            page = self._validate_page(url)
            self.browser_evidence.update(last_successful_command="page_source", phase="payload_script")
            if var is None:
                response = page.encode("utf-8")
            elif isinstance(var, str):
                response = json.dumps(self._driver.execute_script("return " + var)).encode("utf-8")
            else:
                raise NotImplementedError("Only a single payload variable is supported")
            if not self.no_store and filepath is not None:
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_bytes(response)
            return io.BytesIO(response)

    return WhoScored(leagues="ENG-Premier League", seasons=season, no_cache=False,
                         data_dir=data_dir, path_to_browser=str(binary), headless=False)
