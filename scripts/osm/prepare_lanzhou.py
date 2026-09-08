import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.osm.download_osm import download_all
from scripts.osm.export_sample import export_sample
from scripts.osm.import_postgis import import_all
from scripts.osm.preprocess_osm import preprocess_all


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download, clean, and import the CityScope Lanzhou OSM dataset."
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="transactionally rebuild the CityScope OSM and routing tables",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    downloaded = download_all()
    processed = preprocess_all(downloaded)
    counts = import_all(processed, replace=args.replace)
    sample_path = export_sample()
    result = {
        "counts": counts,
        "cleaning": processed["stats"],
        "sample": str(sample_path),
        "source": downloaded["metadata"],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
