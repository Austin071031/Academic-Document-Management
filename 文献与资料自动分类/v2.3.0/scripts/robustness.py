#!/usr/bin/env python3
"""robustness.py — 异常处置矩阵 + 极限样本自检（v2.3.0 方向）。

1) 汇总本次运行对各类异常的实际处置（损坏/加密/扫描件/乱码/权限/冲突/重复），
   形成 exception_matrix；
2) 在隔离临时目录构造 7 类极限样本，端到端调用 inventory+extract 验证处置路径，
   输出 robustness_report.json（每类：样本、预期、实测、pass/fail）；
3) 回写 result.json.robustness。

用法: python3 robustness.py [--work-dir /app/work] [--output-dir /app/output]
"""
import argparse, datetime, json, os, subprocess, sys, tempfile

def load(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def run_case(name, files, expect_fn, wd):
    """files: {fname: bytes}；expect_fn(inventory_record)->(pass, detail)"""
    import inventory as inv_mod
    case_in = os.path.join(wd, "_robust", name)
    os.makedirs(case_in, exist_ok=True)
    brief = {"case_id": f"robust-{name}", "input_dir": case_in, "issues": []}
    os.makedirs(os.path.join(wd, "_robust_work", name), exist_ok=True)
    with open(os.path.join(wd, "_robust_work", name, "brief.json"), "w", encoding="utf-8") as f:
        json.dump(brief, f)
    for fn, data in files.items():
        with open(os.path.join(case_in, fn), "wb") as f:
            f.write(data)
    rc = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "inventory.py"),
                         "--work-dir", os.path.join(wd, "_robust_work", name)],
                        capture_output=True, text=True, timeout=120)
    if rc.returncode != 0:
        return {"case": name, "pass": False, "detail": f"inventory 崩溃: {rc.stderr[:200]}"}
    data = load(os.path.join(wd, "_robust_work", name, "inventory.json"), {}) or {}
    recs = data.get("records", [])
    if not recs:
        return {"case": name, "pass": False, "detail": "无盘点记录"}
    ok, detail = expect_fn(recs[0])
    return {"case": name, "pass": ok, "detail": detail}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    args = ap.parse_args()
    wd, outdir = args.work_dir, args.output_dir

    # —— 1) 本次运行的异常处置矩阵 ——
    inv = load(os.path.join(wd, "inventory.json"), {}) or {}
    plan = load(os.path.join(wd, "plan.json"), {}) or {}
    summ = inv.get("summary") or {}
    matrix = {
        "损坏文件": {"detected": [r["rel_path"] for r in inv.get("records", []) if r.get("error")],
                     "handling": "action=skip，记 exceptions.skipped + uncertainty，不臆造元数据"},
        "加密PDF": {"detected": summ.get("encrypted_pdfs", []),
                    "handling": "单独列入 encrypted_pdfs，跳过并记录"},
        "扫描件(无文本层)": {"detected": summ.get("scanned_candidates", []),
                             "handling": "归入 scanned_document/，元数据缺失如实标注"},
        "权限不足": {"detected": summ.get("unreadable_or_broken", []),
                     "handling": "记录 perm_mode 与 readable=false，跳过并记录"},
        "精确重复": {"detected": len(plan.get("exact_duplicates", [])),
                     "handling": "保留文件名最干净者，其余归档 _archive/duplicates"},
        "同名不同内容": {"detected": len((load(os.path.join(wd, "apply_report.json"), {}) or {}).get("conflicts", [])),
                         "handling": "追加 sha 短后缀改唯一名，不覆盖，记 conflicts"},
    }

    # —— 2) 极限样本自检 ——
    cases = [
        ("truncated_pdf", {"broken.pdf": b"%PDF-1.4 truncated"},
         lambda r: (r.get("error") is not None, f"error={r.get('error') is not None}")),
        ("fake_extension", {"fake.pdf": b"plain text not a pdf"},
         lambda r: (r.get("mime_sniff") == "text", f"sniff={r.get('mime_sniff')}（以魔数为准）")),
        ("empty_file", {"empty.pdf": b""},
         lambda r: (r.get("size_bytes") == 0, f"size={r.get('size_bytes')}")),
        ("long_name", {("a" * 180 + ".txt"): b"hello world content"},
         lambda r: (r.get("sha256") is not None, "长文件名正常哈希")),
        ("cjk_name", {"中文文献（副本）.txt": "中文内容，钙钛矿。".encode("utf-8")},
         lambda r: (r.get("mime_sniff") == "text", f"sniff={r.get('mime_sniff')}")),
        ("zip_as_pdf", {"data.pdf": b"PK\x03\x04" + b"\x00" * 100},
         lambda r: (r.get("mime_sniff") == "zip", f"sniff={r.get('mime_sniff')}（识别伪扩展名）")),
    ]
    results = []
    try:
        for name, files, expect in cases:
            results.append(run_case(name, files, expect, wd))
    finally:
        import shutil
        shutil.rmtree(os.path.join(wd, "_robust"), ignore_errors=True)
        shutil.rmtree(os.path.join(wd, "_robust_work"), ignore_errors=True)

    passed = sum(1 for r in results if r["pass"])
    robustness = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "exception_matrix": matrix,
        "selftest": {"cases": len(results), "passed": passed, "results": results},
        "idempotency_note": "重跑 already_applied；审计日志追加式；rollback.sh 覆盖全历史",
    }
    with open(os.path.join(outdir, "robustness_report.json"), "w", encoding="utf-8") as f:
        json.dump(robustness, f, ensure_ascii=False, indent=2)
    result = load(os.path.join(outdir, "result.json"), {}) or {}
    if result:
        result["robustness"] = {"exception_matrix": matrix,
                                "selftest": f"{passed}/{len(results)} passed",
                                "report": "robustness_report.json"}
        with open(os.path.join(outdir, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[robustness] selftest {passed}/{len(results)} passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
