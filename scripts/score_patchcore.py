"""Fit one PatchCore per LOCO category on train/good and write RAW anomaly scores for validation + test.

No label-fitted thresholding is used (post_processor/evaluator disabled). Model is anomalib defaults:
wide_resnet50_2, layers layer2+layer3, coreset ratio 0.1, 9 neighbors, resize 256x256, no center crop.
Output: results/patchcore_scores.csv and results/patchcore_run_meta.json
"""
import argparse, csv, json, time, random, platform
from pathlib import Path
import numpy as np, torch
from torchvision.io import read_image, ImageReadMode
import anomalib
from anomalib.models import Patchcore

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "MVTec_LOCO"
CATS = ["breakfast_box", "juice_bottle", "pushpins", "screw_bag", "splicing_connectors"]
TYPE_MAP = {"good": "good", "logical_anomalies": "logical", "structural_anomalies": "structural"}


def list_split(cat, split):
    """Yield (path, anomaly_type) for a split."""
    if split in ("train", "validation"):
        for p in sorted((DATA / cat / split / "good").glob("*.png")):
            yield p, "good"
    else:
        for t in ["good", "logical_anomalies", "structural_anomalies"]:
            for p in sorted((DATA / cat / "test" / t).glob("*.png")):
                yield p, TYPE_MAP[t]


def load_batch(paths, pre):
    imgs = [read_image(str(p), ImageReadMode.RGB).float() / 255.0 for p in paths]
    return torch.stack([pre(i) for i in imgs])


def batches(items, n):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--categories", nargs="*", default=CATS)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--out", default=str(ROOT / "results" / "patchcore_scores.csv"))
    a = ap.parse_args()
    dev = torch.device(a.device)
    rows, meta = [], {"seed": a.seed, "device": a.device, "anomalib": anomalib.__version__,
                      "torch": torch.__version__, "platform": platform.platform(),
                      "config": "anomalib Patchcore defaults (wide_resnet50_2, layer2+layer3, coreset 0.1, k=9), resize 256x256, no crop, no label-fitted threshold",
                      "categories": {}}
    for cat in a.categories:
        random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed)
        t0 = time.time()
        m = Patchcore(post_processor=False, evaluator=False, visualizer=False).to(dev)
        pre = Patchcore.configure_pre_processor()
        m.model.train()
        train = [p for p, _ in list_split(cat, "train")]
        for b in batches(train, a.batch):
            with torch.no_grad():
                m.model(load_batch(b, pre).to(dev))
        m.fit()
        m.model.eval()
        t_fit = time.time() - t0
        n = 0
        for split in ["validation", "test"]:
            items = list(list_split(cat, split))
            for b in batches(items, a.batch):
                with torch.no_grad():
                    out = m.model(load_batch([p for p, _ in b], pre).to(dev))
                for (p, typ), s in zip(b, out.pred_score.cpu().flatten().tolist()):
                    rows.append({"image_id": f"{cat}/{split}/{p.parent.name}/{p.name}", "category": cat, "split": split,
                                 "anomaly_type": typ, "ground_truth": "good" if typ == "good" else "defective",
                                 "raw_score": f"{s:.8f}"})
                    n += 1
        meta["categories"][cat] = {"train_images": len(train), "scored_images": n,
                                   "fit_seconds": round(t_fit, 1), "total_seconds": round(time.time() - t0, 1)}
        print(cat, meta["categories"][cat], flush=True)
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    Path(a.out).with_name("patchcore_run_meta.json").write_text(json.dumps(meta, indent=2))
    print("wrote", a.out, len(rows), "rows")


if __name__ == "__main__":
    main()
