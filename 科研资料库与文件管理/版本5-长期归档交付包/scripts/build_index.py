#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step2 建库：stdlib sqlite3 检索库 <output>/library/index/library_index.db。

- files 表：每文件一行（路径/大小/sha256/类型/是否文本）。
- FTS5 虚表 docs(path, content)，content 为中文 bigram + ASCII 词元。
  FTS5 不可用时退化为 LIKE 模式：content 存原文，meta 表登记 degraded=true。
- 逐文件失败不崩溃，登记 error。
"""
import argparse
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib


def fts5_available(con):
    try:
        con.execute("CREATE VIRTUAL TABLE temp._fts5_probe "
                    "USING fts5(x)")
        con.execute("DROP TABLE temp._fts5_probe")
        return True
    except sqlite3.Error:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    output_dir = os.path.abspath(args.output)
    library = os.path.join(output_dir, "library")
    index_dir = os.path.join(library, "index")
    os.makedirs(index_dir, exist_ok=True)
    db_path = os.path.join(index_dir, "library_index.db")

    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("PRAGMA journal_mode=MEMORY")
    cur.execute("DROP TABLE IF EXISTS files")
    cur.execute("CREATE TABLE files ("
                "id INTEGER PRIMARY KEY, path TEXT UNIQUE, size INTEGER, "
                "sha256 TEXT, ftype TEXT, is_text INTEGER, error TEXT)")
    use_fts = fts5_available(con)
    cur.execute("DROP TABLE IF EXISTS meta")
    cur.execute("CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT)")
    cur.execute("INSERT INTO meta VALUES ('mode', ?)",
                ("fts5_bigram" if use_fts else "like_fallback",))
    cur.execute("INSERT INTO meta VALUES ('degraded', ?)",
                ("false" if use_fts else "true",))
    cur.execute("INSERT INTO meta VALUES ('built_utc', ?)",
                (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),))
    if use_fts:
        cur.execute("DROP TABLE IF EXISTS docs")
        cur.execute("CREATE VIRTUAL TABLE docs USING fts5("
                    "path UNINDEXED, content)")
    else:
        cur.execute("DROP TABLE IF EXISTS docs_plain")
        cur.execute("CREATE TABLE docs_plain (path TEXT PRIMARY KEY, "
                    "content TEXT)")

    n_ok = n_err = 0
    rows = []
    for root, _dirs, files in os.walk(library):
        for fn in files:
            if fn.endswith(".db"):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, library).replace(os.sep, "/")
            size = 0
            sha = None
            err = None
            text = None
            try:
                st = os.stat(full)
                size = st.st_size
                sha, serr = lib.sha256_file(full)
                if sha is None:
                    err = serr
                if not lib.is_binary_path(full) and size <= 8 * 1024 * 1024:
                    text = lib.read_text(full)
            except OSError as e:
                err = str(e)
            ftype = lib.file_type(fn)
            rows.append((rel, size, sha, ftype,
                         1 if text is not None else 0, err))
            if err:
                n_err += 1
            else:
                n_ok += 1
            if text is not None:
                if use_fts:
                    toks = lib.cjk_bigrams(text)
                    cur.execute("INSERT INTO docs(path, content) "
                                "VALUES (?, ?)",
                                (rel, " ".join(toks)))
                else:
                    cur.execute("INSERT OR REPLACE INTO docs_plain"
                                "(path, content) VALUES (?, ?)", (rel, text))
    cur.executemany("INSERT INTO files(path,size,sha256,ftype,is_text,"
                    "error) VALUES (?,?,?,?,?,?)", rows)
    con.commit()
    con.execute("INSERT INTO meta VALUES ('indexed_files', ?)",
                (str(len(rows)),))
    con.commit()
    con.close()
    lib.log("build_index: mode=%s files=%d errors=%d db=%s" %
            ("fts5_bigram" if use_fts else "LIKE_fallback",
             len(rows), n_err, db_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
