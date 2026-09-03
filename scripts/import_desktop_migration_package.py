from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).parents[1];sys.path.insert(0,str(ROOT))
from fantrax.migration.package import import_package
def main():
    p=argparse.ArgumentParser();p.add_argument("package",type=Path);p.add_argument("--check",action="store_true");p.add_argument("--project-root",type=Path,default=ROOT);a=p.parse_args();print(json.dumps(import_package(a.package,a.project_root,check=a.check),indent=2))
if __name__=="__main__":main()
