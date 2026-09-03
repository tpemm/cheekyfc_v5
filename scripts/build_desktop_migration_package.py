from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).parents[1];sys.path.insert(0,str(ROOT))
from fantrax.migration.package import build_package
def main():
    p=argparse.ArgumentParser();p.add_argument("--type",choices=("migration","client"),default="migration");p.add_argument("--output",type=Path);a=p.parse_args();name="fantrax_data_v5_gw2_desktop_migration.zip" if a.type=="migration" else "fantrax_data_v5_client_data.zip";target=a.output or ROOT/"migration_exports"/name;manifest=build_package(ROOT,target,package_type=a.type);print(json.dumps({"package":str(target),"files":len(manifest["files"]),"bytes":target.stat().st_size},indent=2))
if __name__=="__main__":main()
