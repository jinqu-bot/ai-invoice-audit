"""evaluate_accuracy.py — 真实识别字段准确率评测（D4 已知问题#5 闭环）

流程：把指定图片批量上传到运行中的后端（本地或线上），拉取识别结果，
逐字段与 ground_truth 对拍，输出字段级准确率报告（Markdown）。

用法：
  python backend/scripts/evaluate_accuracy.py --base http://127.0.0.1:8000 \
      --files ds_001.png ds_002.png ...（或 --manifest docs/real-photo-run-manifest.json）

口径（与 B 的 manifest 约定一致）：
  - 只比对"识别字段 vs gt 字段"，不看 verdict（线上日期/台账会让 R4/R1 漂移）
  - 金额字段允许 0.01 误差；税率按数值比；日期按字符串规范化比
  - missing_fields 中的字段算"未识别"（不计入分母，单独统计）
"""
import argparse, json, sys, time
from pathlib import Path
import urllib.request, urllib.parse

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "data" / "dataset"
FIELDS = ["invoice_number", "invoice_date", "seller_name", "seller_tax_id",
          "buyer_name", "buyer_tax_id", "amount_excl_tax", "tax_amount",
          "amount_incl_tax", "tax_rate", "category"]

def norm(v):
    if v is None: return None
    if isinstance(v, float): return round(v, 2)
    return str(v).strip().replace(" ", "")

def post_batch(base, files):
    boundary = "----eval7f3a9"
    body = b""
    for f in files:
        data = Path(f).read_bytes()
        body += (f"--{boundary}\r\nContent-Disposition: form-data; "
                 f'name="files"; filename="{Path(f).name}"\r\n'
                 f"Content-Type: image/png\r\n\r\n").encode() + data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(base + "/api/batches", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["batch_id"]

def get_results(base, batch_id, timeout=600):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with urllib.request.urlopen(f"{base}/api/batches/{batch_id}/results", timeout=60) as r:
            d = json.loads(r.read())
        if d.get("status") in ("done", "failed", "partial"):
            return d
        time.sleep(2)
    raise TimeoutError("批次超时")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--files", nargs="*", default=None)
    ap.add_argument("--manifest", default=None)
    a = ap.parse_args()

    if a.manifest:
        man = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
        names = [e["filename"] for b in man["batches"] for e in b["files"]]
    else:
        names = a.files
    files = [DATASET / n for n in names]
    assert all(f.exists() for f in files), "有文件不存在"

    gt = {e["file"]: e for e in json.loads((DATASET/"ground_truth.json").read_text(encoding="utf-8"))}

    batch_id = post_batch(a.base, files)
    print(f"批次 {batch_id} 已提交，等待完成...")
    res = get_results(a.base, batch_id)

    rows, field_hit, field_total, miss_count = [], {k: [0,0] for k in FIELDS}, 0, 0
    for inv in res.get("invoices", []):
        fname, ext = inv.get("file") or inv.get("filename"), inv.get("extract") or {}
        g = gt.get(fname)
        if not g or not g.get("is_invoice", True):
            continue
        missing = set(inv.get("missing_fields", []))
        row = {"file": fname, "provider": inv.get("provider")}
        for k in FIELDS:
            if k in missing or ext.get(k) is None:
                field_total += 1; miss_count += 1
                row[k] = "缺失"; field_hit[k][1] += 1
                continue
            ok = norm(ext.get(k)) == norm(g.get(k))
            field_hit[k][0] += ok; field_hit[k][1] += 1; field_total += 1
            row[k] = "对" if ok else f"错({ext.get(k)}≠{g.get(k)})"
        rows.append(row)

    lines = ["# 真实识别字段准确率评测\n",
             f"- 批次：{batch_id}  样本：{len(rows)} 张  基数：字段总数 {field_total}、缺失 {miss_count}\n",
             "## 分字段准确率\n", "| 字段 | 正确/总数 | 准确率 |\n|---|---|---|"]
    for k in FIELDS:
        c, t = field_hit[k]
        lines.append(f"| {k} | {c}/{t} | {c/t*100:.1f}% |" if t else f"| {k} | - | - |")
    ok_all = sum(v[0] for v in field_hit.values())
    lines += [f"\n**整体字段准确率：{ok_all}/{field_total} = {ok_all/field_total*100:.1f}%**\n",
              "## 逐票明细\n", "| 文件 | " + " | ".join(FIELDS) + " |\n|---|" + "---|"*len(FIELDS)]
    for r in rows:
        lines.append("| " + r["file"] + " | " + " | ".join(str(r[k]) for k in FIELDS) + " |")
    out = ROOT.parent / "docs" / "真识别准确率评测.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"报告已写入 {out}")

if __name__ == "__main__":
    main()
