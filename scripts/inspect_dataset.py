"""Inspect MVTec LOCO AD on disk and write a machine-readable manifest (results/dataset_manifest.json)."""
import json, hashlib, collections
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / "data" / "MVTec_LOCO"
CATS = ["breakfast_box", "juice_bottle", "pushpins", "screw_bag", "splicing_connectors"]
out = {"root": str(ROOT), "categories": {}}
totals = collections.Counter()
for c in CATS:
    d = {}
    for split in ["train", "validation"]:
        files = sorted((ROOT / c / split / "good").glob("*.png"))
        d[split] = {"good": len(files)}
        totals[split] += len(files)
    d["test"] = {}
    for t in ["good", "logical_anomalies", "structural_anomalies"]:
        files = sorted((ROOT / c / "test" / t).glob("*.png"))
        d["test"][t] = len(files)
        totals["test_" + t] += len(files)
    # ground truth: ground_truth/<type>/<image_stem>/<mask>.png (may have several masks per image)
    gt = {}
    for t in ["logical_anomalies", "structural_anomalies"]:
        dirs = sorted(p for p in (ROOT / c / "ground_truth" / t).iterdir() if p.is_dir())
        masks = sorted((ROOT / c / "ground_truth" / t).rglob("*.png"))
        stems_test = {p.stem for p in (ROOT / c / "test" / t).glob("*.png")}
        gt[t] = {"images_with_gt_dir": len(dirs), "mask_files": len(masks),
                 "gt_dirs_match_test_images": {p.name for p in dirs} == stems_test}
    d["ground_truth"] = gt
    sample = next((ROOT / c / "train" / "good").glob("*.png"))
    d["image_size_wh"] = list(Image.open(sample).size)
    out["categories"][c] = d
out["totals"] = dict(totals)
out["total_png_images_train_val_test"] = sum(totals.values())
out["total_test"] = sum(v for k, v in totals.items() if k.startswith("test_"))
(Path(__file__).resolve().parents[1] / "results" / "dataset_manifest.json").write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
