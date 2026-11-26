"""Export TTPV receiver comparisons as one long-form CSV per benchmark."""

import argparse
import csv
import hashlib
import io
import json
import math
import platform
import re
import sqlite3
import sys
import warnings
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from itertools import combinations
from multiprocessing import get_context
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from threading import Event, Thread
from time import perf_counter, process_time, time_ns
from zipfile import BadZipFile, ZipFile

import numpy as np
import pandas as pd
from scipy.signal import butter, sosfiltfilt

BODY = ("x-disp", "x-vel", "y-disp", "y-vel", "z-disp", "z-vel")
VARIABLES = {
    "el_sf_body": BODY,
    "ac_sf_body": (*BODY, "pprime", "dp"),
    "ac_ss_body": (*BODY, "pprime", "dp"),
    "faultst": ("h-slip", "h-slip-rate", "h-shear-stress", "v-slip", "v-slip-rate",
                "v-shear-stress", "n-stress"),
}
WINDOWS = {"eg": (0.0, 240.0), "nrmse": (30.0, 240.0)}
METRICS = tuple(WINDOWS)
ENDPOINT_ATOL = 1e-8  # seconds; tolerate printed timestamps at the nominal endpoint
CACHE_VERSION = 1
FIELDS = (
    "benchmark_id", "receiver_type", "receiver_id", "x_km", "y_km", "w_km",
    "variable", "dataset_a", "dataset_b", "metric", "value", "status", "display_excluded",
    "t_start_s", "t_end_s", "sample_count", "dt_s", "lowpass_hz", "filter_order", "fmin_hz", "fmax_hz",
)


@contextmanager
def timed(timings, stage):
    start = perf_counter()
    try:
        yield
    finally:
        timings[stage] += perf_counter() - start


def read_receiver(source, variables, timings):
    path, member = source
    context = path if member is None else f"{path}!{member}"
    with timed(timings, "read_input"):
        if member is None:
            raw = path.read_bytes()
        else:
            with ZipFile(path) as archive:
                raw = archive.read(member)
    with timed(timings, "parse_csv"):
        time, frame = parse_receiver(raw, context, variables)
    return time, frame, len(raw)


def parse_receiver(raw, context, variables):
    with io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8-sig") as source:
        header = next((line for line in source if line.strip() and not line.lstrip().startswith("#")), "")
    separator = "," if "," in header else r"\s+"
    try:
        frame = pd.read_csv(io.BytesIO(raw), comment="#", sep=separator, encoding="utf-8-sig")
    except ValueError as exc:
        raise ValueError(f"{context}: {exc}") from exc
    frame.columns = frame.columns.str.strip()
    missing = {"t", *variables} - set(frame.columns)
    if missing:
        raise ValueError(f"{context}: missing columns {', '.join(sorted(missing))}")
    frame = frame.loc[:, ["t", *variables]].apply(pd.to_numeric, errors="coerce")
    time = frame["t"].to_numpy(dtype=float)
    if time.size == 0 or not np.isfinite(time).all() or np.any(np.diff(time) <= 0):
        raise ValueError(f"{context}: expected finite, strictly increasing time samples")
    return time, frame


def align(time, values, grid, cutoff, order, context):
    dt = float(np.median(np.diff(time)))
    if cutoff is not None and np.isfinite(values).all():
        if cutoff >= 0.5 / dt:
            warnings.warn(f"{context}: filter cutoff reaches native Nyquist. Using unfiltered samples.")
        else:
            sos = butter(order, cutoff, btype="lowpass", fs=1 / dt, output="sos")
            try:
                values = sosfiltfilt(sos, values)
            except ValueError as exc:
                warnings.warn(f"{context}: {exc} Using unfiltered samples.")
    return np.interp(grid, time, values)


def envelope_score(a, b):
    # ObsPy single-component envelope misfit with st2_isref=False and A=10, k=1.
    a_amp, a_peak, a_norm = a
    b_amp, b_peak, b_norm = b
    norm = a_norm if a_peak > b_peak else b_norm
    if norm == 0:
        return math.nan
    em = np.sqrt(np.sum(np.sum((a_amp - b_amp) ** 2, axis=1))) / norm
    return 10 * np.exp(-em)


def nrmse(a, b):
    span = max(np.ptp(a), np.ptp(b))
    if span > 0:
        return np.sqrt(np.mean((a - b) ** 2)) / span
    return 0.0 if np.array_equal(a, b) else math.nan


def receiver_coordinates(kind, receiver):
    if kind == "faultst":
        match = re.fullmatch(r"faultst(\d+)dp(\d+)", receiver)
        if match:
            y, w = (int(value) / 10 for value in match.groups())
            return None, y, w
    else:
        match = re.fullmatch(rf"{kind}(-?\d+)st(\d+)", receiver)
        if match:
            x, y = (int(value) / 10 for value in match.groups())
            return x, y, None
    return None, None, None


def display_excluded(receiver, variable):
    return (receiver.startswith("faultst000") and variable in {"h-slip", "h-slip-rate", "h-shear-stress"}
            or receiver.endswith("st000") and variable in {"y-disp", "y-vel"}
            or receiver.startswith("ac_ss_body") and variable == "dp")


def trim_envelopes(db, budget):
    used, = db.execute("SELECT coalesce(sum(length(data)), 0) FROM envelopes").fetchone()
    if used > budget:
        for key, size in db.execute("SELECT key, length(data) FROM envelopes ORDER BY accessed").fetchall():
            db.execute("DELETE FROM envelopes WHERE key=?", (key,))
            used -= size
            if used <= budget:
                break


def prepare_envelope(values, args, db):
    from obspy.signal.tf_misfit import cwt

    if db is not None:
        # Hash the actual aligned inputs. Equivalent traces can share an envelope across submissions.
        settings = [CACHE_VERSION, args.library_versions, args.time_range or WINDOWS["eg"],
                    args.dt, args.fmin, args.fmax, 6, 100]
        digest = hashlib.sha256(json.dumps(settings).encode())
        digest.update(values.astype("<f8", copy=False).tobytes())
        key = digest.hexdigest()
        row = db.execute("SELECT data FROM envelopes WHERE key=?", (key,)).fetchone()
        if row:
            with db:
                db.execute("UPDATE envelopes SET accessed=? WHERE key=?", (time_ns(), key))
            return np.frombuffer(row[0], dtype="<f8").reshape(100, len(values)), True

    amp = np.abs(cwt(values, args.dt, 6, args.fmin, args.fmax, nf=100))
    if db is not None and amp.nbytes <= args.envelope_budget:
        with db:
            db.execute("BEGIN IMMEDIATE")
            trim_envelopes(db, args.envelope_budget - amp.nbytes)
            db.execute("INSERT OR REPLACE INTO envelopes VALUES (?,?,?)",
                       (key, time_ns(), amp.astype("<f8", copy=False).tobytes()))
    return amp, False


def receiver_rows(task):
    args = task[0]
    if args.envelope_budget:
        with closing(sqlite3.connect(args.output.with_suffix(".envelopes.sqlite3"), timeout=120)) as cache:
            return score_receiver(task, cache)
    return score_receiver(task, None)


def score_receiver(task, envelope_cache):
    args, kind, receiver, paths, pending = task
    started = perf_counter()
    cpu_start = process_time()
    timings = Counter()
    traces = {label: read_receiver(source, VARIABLES[kind], timings) for label, source in paths.items()}
    grids = {}
    eligible = {}
    for metric in {metric for _, _, metric in pending}:
        start, end = args.time_range or WINDOWS[metric]
        grid = start + np.arange(math.floor((end - start) / args.dt + 1e-10) + 1) * args.dt
        grids[metric] = grid
        eligible[metric] = {
            label for label, (time, _, _) in traces.items()
            if time.size >= 2 and time[0] <= start + ENDPOINT_ATOL and time[-1] >= end - ENDPOINT_ATOL
        }

    # Share native filtering and interpolation between metrics, even for a non-default dt.
    union_grid = np.unique(np.concatenate(list(grids.values())))
    indices = {metric: np.searchsorted(union_grid, grid) for metric, grid in grids.items()}
    accepted = [(a, b, metric) for a, b, metric in pending if {a, b} <= eligible[metric]]
    skipped = len(pending) - len(accepted)
    active = {label for a, b, _ in accepted for label in (a, b)}
    x, y, w = receiver_coordinates(kind, receiver)
    blocks = {item: [] for item in pending}
    transforms = 0
    envelope_hits = 0

    for variable in VARIABLES[kind]:
        with timed(timings, "filter_and_interpolate"):
            aligned = {label: align(traces[label][0], traces[label][1][variable].to_numpy(dtype=float),
                                    union_grid, args.lowpass, args.filter_order, f"{label}/{receiver}/{variable}")
                       for label in active}
        for metric, grid in grids.items():
            pairs = [(a, b) for a, b, m in accepted if m == metric]
            uses = Counter(label for pair in pairs for label in pair)
            prepared = {}
            for a, b in pairs:
                for label in (a, b):
                    if label in prepared:
                        continue
                    values = aligned[label][indices[metric]]
                    prepared[label] = None
                    if np.isfinite(values).all():
                        if metric == "eg":
                            with timed(timings, "wavelet"):
                                amp, hit = prepare_envelope(values, args, envelope_cache)
                                prepared[label] = (amp, amp.max(), np.sqrt(np.sum(amp ** 2)))
                                transforms += int(not hit)
                                envelope_hits += int(hit)
                                del amp
                        else:
                            prepared[label] = values
                left, right = prepared[a], prepared[b]
                value = math.nan
                if left is not None and right is not None:
                    with timed(timings, "score_pairs"):
                        value = envelope_score(left, right) if metric == "eg" else nrmse(left, right)
                valid = math.isfinite(value)
                blocks[a, b, metric].append((
                    args.benchmark, kind, receiver, x, y, w, variable, a, b, metric,
                    value if valid else None, "ok" if valid else "undefined",
                    int(display_excluded(receiver, variable)), grid[0], grid[-1], grid.size, args.dt,
                    args.lowpass, args.filter_order, args.fmin if metric == "eg" else None,
                    args.fmax if metric == "eg" else None,
                ))
                # Keep shared envelopes only until their last pending comparison.
                del left, right
                for label in (a, b):
                    uses[label] -= 1
                    if not uses[label]:
                        del prepared[label]

    return {key: blocks[item] for item, key in pending.items()}, {
        "receiver": receiver, "datasets": list(paths), "variables": len(VARIABLES[kind]),
        "pairs": len({(a, b) for a, b, _ in pending}), "skipped_pair_metrics": skipped,
        "short_inputs": {m: sorted(set(traces) - ok) for m, ok in eligible.items()},
        "native_samples": [len(time) for time, _, _ in traces.values()],
        "aligned_samples": len(union_grid), "samples_by_metric": {m: len(g) for m, g in grids.items()},
        "input_bytes": sum(size for _, _, size in traces.values()), "wavelet_transforms": transforms,
        "envelope_cache_hits": envelope_hits,
        "rows": sum(map(len, blocks.values())), "elapsed_s": perf_counter() - started,
        "cpu_s": process_time() - cpu_start, "stages_s": dict(timings),
    }


def index_input(path):
    files = {}

    def add(name, source, revision):
        stem, suffix = name.stem, name.suffix
        if suffix.lower() == ".csv" and stem.startswith(tuple(VARIABLES)):
            if stem in files:
                raise ValueError(f"{path}: duplicate receiver filename {name}")
            files[stem] = (source, revision)

    if path.is_dir():
        for entry in path.iterdir():
            if entry.is_file():
                add(entry, (entry, None), None)
    else:
        with ZipFile(path) as archive:
            for member in archive.infolist():
                name = PurePosixPath(member.filename)
                if not member.is_dir() and "__MACOSX" not in name.parts:
                    add(name, (path, member.filename), (member.CRC, member.file_size))
    if not files:
        raise ValueError(f"No supported receiver CSV files found in {path}")
    return files


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True, choices=("ttpv1", "ttpv2"))
    parser.add_argument("--dataset", action="append", nargs="+", default=[], metavar="INPUT",
                        help="PATH or LABEL PATH. Use a directory or ZIP. Default: all ZIPs in resources/<BENCHMARK>_results.")
    parser.add_argument("--source", action="append", nargs=2, default=[], metavar=("LABEL", "PATH"),
                        help="Locate a dataset already in the output if its local source is missing or moved.")
    parser.add_argument("--output", type=Path, help="Default: metrics.csv beside discovered ZIPs, or in the current directory for explicit inputs.")
    parser.add_argument("--data", action="append", choices=VARIABLES, help="Receiver type. Default: all.")
    parser.add_argument("--receiver", action="append", help="Exact receiver filename stem. Default: all shared.")
    parser.add_argument("--metric", action="append", choices=METRICS, help="Metric to export. Default: EG and NRMSE.")
    parser.add_argument("--dt", type=float, default=0.01)
    parser.add_argument("--time-range", type=float, nargs=2, metavar=("START", "END"))
    parser.add_argument("--lowpass", type=float, default=5.0, help="Cutoff in Hz. Use 0 to disable.")
    parser.add_argument("--filter-order", type=int, default=1)
    parser.add_argument("--fmin", type=float, default=0.01)
    parser.add_argument("--fmax", type=float, default=5.0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--envelope-cache-gib", type=float, default=0, metavar="GIB",
                        help="Maximum stored EG envelope payload in GiB. Default: in-memory reuse only.")
    parser.add_argument("--profile", action="store_true", help="Write a unique JSON performance report (uses psutil).")
    args = parser.parse_args()
    if not math.isfinite(args.envelope_cache_gib) or args.envelope_cache_gib < 0:
        parser.error("Use a finite nonnegative envelope cache size.")
    args.envelope_budget = int(args.envelope_cache_gib * 2**30)
    args.library_versions = [np.__version__, pd.__version__, version("scipy")]
    try:
        args.library_versions.append(version("obspy"))
    except PackageNotFoundError:
        args.library_versions.append(None)
    datasets = {}
    if not args.dataset:
        folder = Path(__file__).resolve().parents[1] / "resources" / f"{args.benchmark.upper()}_results"
        args.dataset = [[str(path)] for path in sorted(folder.glob("*.zip"))]
        if not args.dataset:
            parser.error(f"No submission ZIPs in {folder}. Supply --dataset or add ZIPs there.")
        args.output = args.output or folder / "metrics.csv"
    args.output = (args.output or Path("metrics.csv")).resolve()
    for item in args.dataset:
        if len(item) not in (1, 2):
            parser.error("Use --dataset PATH or --dataset LABEL PATH.")
        path = Path(item[-1])
        label = item[0] if len(item) == 2 else path.stem if path.suffix.lower() == ".zip" else path.resolve().name
        if not label.strip() or label in datasets:
            parser.error("Dataset labels must be unique and nonempty.")
        datasets[label] = path.resolve()
    args.dataset = datasets
    if len(dict(args.source)) != len(args.source):
        parser.error("Specify each --source label only once.")
    if not all(map(math.isfinite, (args.dt, args.lowpass, args.fmin, args.fmax))):
        parser.error("Sampling and frequency settings must be finite.")
    if not (args.dt > 0 and args.lowpass >= 0 and 0 < args.fmin < args.fmax
            and args.filter_order >= 1 and args.workers >= 1):
        parser.error("Use positive sampling interval, filter order, and workers, cutoff >= 0, and 0 < fmin < fmax.")
    if args.time_range and (not all(map(math.isfinite, args.time_range))
                            or args.time_range[0] >= args.time_range[1]):
        parser.error("The time range must have finite, increasing endpoints.")
    if any(args.dt > end - start for start, end in [args.time_range or WINDOWS[m] for m in args.metric or METRICS]):
        parser.error("Sampling interval exceeds the metric window.")
    args.lowpass = args.lowpass or None
    args.data = tuple(dict.fromkeys(args.data or VARIABLES))
    args.metric = tuple(dict.fromkeys(args.metric or METRICS))
    return args


def plan_export(args, manifest):
    # Preserve published coverage when a run requests extra receivers or metrics.
    history = defaultdict(set)
    previous = set()
    recorded = {}
    if manifest.exists():
        recorded = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(recorded, dict) or any(not isinstance(path, str) for path in recorded.values()):
            raise ValueError(f"{manifest}: expected a map of dataset labels to paths.")
        previous.update(recorded)
    full_selection = (len(args.dataset) >= 2 and not args.receiver and set(args.data) == set(VARIABLES)
                      and set(args.metric) == set(METRICS))
    if args.output.is_file():
        with args.output.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if reader.fieldnames != list(FIELDS):
                raise ValueError(f"{args.output}: expected the exporter CSV schema.")
            for row in reader:
                if row["benchmark_id"] != args.benchmark:
                    raise ValueError(f"{args.output}: benchmark mismatch.")
                if full_selection and recorded:
                    # The manifest supplies all runs and the ZIP indexes supply all receivers.
                    break
                labels = tuple(sorted((row["dataset_a"], row["dataset_b"])))
                previous.update(labels)
                if row["metric"] in WINDOWS:
                    history[row["receiver_id"]].add((*labels, row["metric"]))
    if set(dict(args.source)) - previous:
        raise ValueError("--source must refer to a previously recorded dataset label.")
    recorded.update(dict(args.source))
    missing = previous - args.dataset.keys() - recorded.keys()
    if missing:
        raise ValueError(f"Supply --source LABEL PATH for {', '.join(sorted(missing))}.")
    sources = {label: Path(recorded[label]).resolve() for label in sorted(previous - args.dataset.keys())}
    sources.update(args.dataset)
    if len(sources) < 2:
        raise ValueError("At least two different submissions are needed to score a pair.")
    return sources, history


def comparison_tasks(args, sources, history, db):
    indexed = {label: index_input(path) for label, path in sources.items()}
    receivers = sorted(set.union(*(set(files) for files in indexed.values())))
    available = set()
    output_keys = []
    output_pairs = set()
    output_receivers = set()
    tasks = []
    for receiver in receivers:
        kind = next(kind for kind in VARIABLES if receiver.startswith(kind))
        entries = {label: files[receiver] for label, files in indexed.items() if receiver in files}
        pairs = list(combinations(sorted(entries), 2))
        if pairs and kind in args.data:
            available.add(receiver)
        wanted = set(history[receiver])
        if kind in args.data and (not args.receiver or receiver in args.receiver):
            wanted.update((a, b, m) for a, b in pairs for m in args.metric
                          if len(args.dataset) != 1 or a in args.dataset or b in args.dataset)
        pending = {}
        revisions = {}
        for a, b, metric in sorted(wanted):
            if a not in entries or b not in entries:
                continue
            for label in (a, b):
                if label not in revisions:
                    (path, _), revision = entries[label]
                    revisions[label] = revision or hashlib.sha256(path.read_bytes()).hexdigest()
            key = json.dumps([CACHE_VERSION, args.benchmark, receiver, a, revisions[a], b, revisions[b],
                              metric, args.time_range or WINDOWS[metric], args.dt, args.lowpass, args.filter_order,
                              (args.fmin, args.fmax) if metric == "eg" else None,
                              args.library_versions if metric == "eg" else args.library_versions[:3]])
            output_keys.append(key)
            output_pairs.add((a, b))
            output_receivers.add(receiver)
            if db.execute("SELECT 1 FROM scores WHERE key=?", (key,)).fetchone() is None:
                pending[a, b, metric] = key
        if pending:
            paths = {label: entries[label][0] for a, b, _ in pending for label in (a, b)}
            tasks.append((args, kind, receiver, paths, pending))
    missing = set(args.receiver or ()) - available
    if missing or not output_keys:
        raise ValueError(f"No comparable receivers for selection: {', '.join(sorted(missing)) or args.data}")
    return tasks, output_keys, len(output_pairs), len(output_receivers)


@contextmanager
def export_lock(path):
    lock = path.with_suffix(path.suffix + ".lock")
    # SQLite releases the OS lock even when an exporter is killed mid-run.
    with closing(sqlite3.connect(lock, timeout=0)) as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            raise ValueError(f"Could not lock {path}: {exc}") from exc
        yield


@contextmanager
def sample_memory(enabled, report):
    if not enabled:
        yield
        return
    import psutil

    root = psutil.Process()
    done = Event()

    def poll():
        while True:
            rss = 0
            for process in [root, *root.children(recursive=True)]:
                try:
                    rss += process.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            report["peak_sampled_tree_rss_bytes"] = max(rss, report.get("peak_sampled_tree_rss_bytes", 0))
            if done.wait(0.05):
                break

    monitor = Thread(target=poll)
    monitor.start()
    try:
        yield
    finally:
        done.set()
        monitor.join()


def write_profile(args, report):
    samples = report["tasks"]
    stages = Counter()
    for task in samples:
        stages.update(task["stages_s"])
    report["task_stage_sums_s"] = dict(stages)
    report["task_cpu_s"] = sum(task["cpu_s"] for task in samples)
    if samples:
        durations = [task["elapsed_s"] for task in samples]
        report["task_elapsed_s"] = {
            "p50": float(np.percentile(durations, 50)),
            "p95": float(np.percentile(durations, 95)),
            "max": max(durations),
        }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.output.parent,
                            prefix=f"{args.output.stem}.profile-{stamp}-", suffix=".json", delete=False) as out:
        json.dump(report, out, indent=2)
        out.write("\n")
    print(f"Performance report: {out.name}")


def save_results(db, results, tasks, report):
    for index, (blocks, stats) in enumerate(results, start=1):
        with db:
            db.executemany("INSERT OR REPLACE INTO scores VALUES (?,?)",
                           ((key, json.dumps(rows, allow_nan=False)) for key, rows in blocks.items()))
        if report is not None:
            report["tasks"].append(stats)
        print(f"[{index}/{len(tasks)}] {stats['receiver']} ({', '.join(stats['datasets'])}), "
              f"{stats['rows']} rows, {stats['skipped_pair_metrics']} pair-metrics skipped", flush=True)


def run_export(args, report, timings):
    manifest = args.output.with_suffix(".sources.json")
    temporary_paths = []
    db = sqlite3.connect(args.output.with_suffix(".cache.sqlite3"))
    try:
        db.execute("CREATE TABLE IF NOT EXISTS scores (key TEXT PRIMARY KEY, result TEXT NOT NULL)")
        if args.envelope_budget:
            with closing(sqlite3.connect(args.output.with_suffix(".envelopes.sqlite3"))) as cache, cache:
                cache.execute("CREATE TABLE IF NOT EXISTS envelopes (key TEXT PRIMARY KEY, accessed INTEGER, data BLOB)")
                trim_envelopes(cache, args.envelope_budget)
        with timed(timings, "discover"):
            sources, history = plan_export(args, manifest)
            if len(set(sources.values())) != len(sources):
                raise ValueError("Each dataset must use a different input path.")
            for path in sources.values():
                if not (path.is_dir() or path.is_file() and path.suffix.lower() == ".zip"):
                    raise ValueError(f"Expected a directory or ZIP at {path}. Use --source to relocate it.")
                if args.output == path or (args.output.parent == path and args.output.stem.startswith(tuple(VARIABLES))):
                    raise ValueError("Output path collides with a submission input.")
            tasks, keys, pair_count, receiver_count = comparison_tasks(args, sources, history, db)
        hits = len(keys) - sum(len(task[-1]) for task in tasks)
        print(f"{hits}/{len(keys)} receiver/pair/metric results cached. {len(tasks)} receiver tasks.", flush=True)
        if report is not None:
            report.update(dataset_count=len(sources), cache_hits=hits, cache_misses=len(keys)-hits,
                          task_count=len(tasks), comparison_count=pair_count, receiver_count=receiver_count)
        if args.workers == 1 or not tasks:
            save_results(db, map(receiver_rows, tasks), tasks, report)
        else:
            with ProcessPoolExecutor(max_workers=args.workers, mp_context=get_context("spawn")) as pool:
                save_results(db, pool.map(receiver_rows, tasks), tasks, report)
        with timed(timings, "write_csv"), NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=args.output.parent,
            prefix=".metrics-", suffix=".tmp", delete=False,
        ) as output:
            temporary_paths.append(Path(output.name))
            writer = csv.writer(output)
            writer.writerow(FIELDS)
            row_count = 0
            for key in keys:
                payload, = db.execute("SELECT result FROM scores WHERE key=?", (key,)).fetchone()
                rows = json.loads(payload)
                writer.writerows(rows)
                row_count += len(rows)
            if report is not None:
                report["retained_rows"] = row_count - sum(task["rows"] for task in report["tasks"])
        with timed(timings, "publish_local_files"):
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.output.parent,
                                    prefix=".sources-", suffix=".tmp", delete=False) as source_file:
                temporary_paths.append(Path(source_file.name))
                json.dump({label: str(path) for label, path in sources.items()}, source_file, indent=2)
                source_file.write("\n")
            temporary_paths[1].replace(manifest)
            temporary_paths[0].replace(args.output)
    finally:
        db.close()
        for temporary in temporary_paths:
            temporary.unlink(missing_ok=True)
    print(f"Wrote {args.output} for {args.benchmark}.")


def main():
    args = parse_args()
    started = perf_counter()
    timings = Counter()
    report = {
        "benchmark_id": args.benchmark, "python": platform.python_version(), "platform": platform.platform(),
        "envelope_budget_bytes": args.envelope_budget,
        "workers": args.workers, "metrics": args.metric, "dt_s": args.dt,
        "time_range_s": args.time_range, "lowpass_hz": args.lowpass, "filter_order": args.filter_order,
        "fmin_hz": args.fmin, "fmax_hz": args.fmax, "tasks": [], "status": "failed",
    }
    status = 1
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with export_lock(args.output), sample_memory(args.profile, report):
            run_export(args, report if args.profile else None, timings)
        report["status"] = "ok"
        status = 0
    except (ValueError, OSError, ImportError, BadZipFile, sqlite3.Error) as exc:
        report["error"] = str(exc)
        print(f"Export failed: {exc}", file=sys.stderr)
    finally:
        if args.profile:
            report.update(elapsed_s=perf_counter() - started, main_stages_s=dict(timings))
            try:
                write_profile(args, report)
            except OSError as exc:
                print(f"Could not write performance report: {exc}", file=sys.stderr)
                status = 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
