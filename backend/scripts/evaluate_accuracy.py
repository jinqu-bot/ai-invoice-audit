"""11-field GT comparison. --exports reads frontend JSON offline; no verdict scoring.
Missing/failed records stay in the denominator; simulated data requires explicit opt-in.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import mimetypes
import re
import time
import urllib.parse
import urllib.request
import uuid
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from pathlib import Path

DATASET = Path(__file__).resolve().parents[1] / 'data' / 'dataset'
FIELDS = ('invoice_number', 'invoice_date', 'seller_name', 'seller_tax_id',
          'buyer_name', 'buyer_tax_id', 'amount_excl_tax', 'tax_amount',
          'amount_incl_tax', 'tax_rate', 'category')
AMOUNTS = {'amount_excl_tax', 'tax_amount', 'amount_incl_tax'}


def same(field, got, want):
    if got is None or want is None:
        return False  # Never coerce unknown amounts to zero.
    if field in AMOUNTS or field == 'tax_rate':
        try:
            delta = abs(Decimal(str(got)) - Decimal(str(want)))
            return delta <= (Decimal('0.01') if field in AMOUNTS else Decimal('0'))
        except (InvalidOperation, ValueError):
            return False
    def norm(value):
        text = ''.join(str(value).split())
        if field == 'invoice_date':
            match = re.fullmatch(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', text)
            if match:
                y, m, d = map(int, match.groups())
                return f'{y:04}-{m:02}-{d:02}'
        return text
    return norm(got) == norm(want)


def get_json(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def post_batch(base, files):
    boundary = '----eval-' + uuid.uuid4().hex
    parts = []
    for file in files:
        mime = mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
        header = (f'--{boundary}\r\nContent-Disposition: form-data; name="files"; '
                  f'filename="{file.name}"\r\nContent-Type: {mime}\r\n\r\n')
        parts.append(header.encode() + file.read_bytes() + b'\r\n')
    body = b''.join(parts) + f'--{boundary}--\r\n'.encode()
    request = urllib.request.Request(base + '/api/batches', data=body,
        headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)['batch_id']


def get_results(base, batch_id, timeout=600):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = get_json(f"{base}/api/batches/{urllib.parse.quote(batch_id, safe='')}/results")
        status = result['batch']['status']
        if status in ('done', 'partial', 'failed'):
            return result
        if status != 'processing':
            raise ValueError(f'Unknown batch status: {status}')
        time.sleep(2)
    raise TimeoutError(f'Batch {batch_id} timed out; preserve its ID before retrying')


def collect_online(base, groups):
    exports = []
    for group in groups:
        for offset in range(0, len(group), 20):
            batch_id = post_batch(base, [DATASET / name for name in group[offset:offset + 20]])
            print(f'Submitted {batch_id}', flush=True)
            result = get_results(base, batch_id)
            details, failures = [], list(result.get('failures', []))
            for item in result['items']:
                try:
                    details.append(get_json(f"{base}/api/invoices/{urllib.parse.quote(item['invoice_id'], safe='')}"))
                except Exception as exc:
                    failures.append({'filename': item.get('filename'), 'code': 'DETAIL_FETCH_FAILED',
                                     'message': type(exc).__name__})
            exports.append({'batch': result['batch'], 'invoices': details, 'failures': failures})
    return exports


def summarize(rows):
    per_field = {f: {'correct': sum(r['fields'][f]['status'] in ('correct', 'correct_missing') for r in rows),
                     'total': len(rows)} for f in FIELDS}
    return {'count': len(rows), 'exact_all': sum(r['exact_all'] for r in rows),
            'failed': sum(all(v['status'] == 'failed' for v in r['fields'].values()) for r in rows),
            'missing': sum(v['status'] == 'missing' for r in rows for v in r['fields'].values()),
            'correct_fields': sum(v['correct'] for v in per_field.values()),
            'total_fields': len(rows) * len(FIELDS), 'per_field': per_field}


def score(entries, exports, allow_simulated=False):
    expected = {e['file']: e for e in entries}
    if not expected or len(expected) != len(entries):
        raise ValueError('Expected filenames must be nonempty and unique')
    if any(not e.get('is_invoice', True) for e in entries):
        raise ValueError('Score non-invoice detection separately')
    details, failures = {}, {}
    for export in exports:
        if export['batch']['status'] not in ('done', 'partial', 'failed'):
            raise ValueError('Cannot evaluate an unfinished batch')
        for failure in export.get('failures', []):
            failures[failure.get('filename')] = failure
        for detail in export['invoices']:
            name = detail.get('filename')
            if name not in expected or name in details:
                raise ValueError(f'Unexpected or duplicate result: {name}')
            if detail.get('provider') != 'openai-compat' and not allow_simulated:
                raise ValueError(f'{name}: simulated/unknown source; --allow-simulated is for integration only')
            details[name] = detail
    rows = []
    for name, entry in expected.items():
        detail = details.get(name)
        missing = set(detail.get('missing_fields', [])) if detail else set()
        got = detail.get('fields', {}) if detail else {}
        comparisons = {}
        for field in FIELDS:
            want, value = entry.get(field), got.get(field)
            if not detail:
                state = 'failed'
            elif want is None:
                state = 'correct_missing' if field in missing else 'unexpected_value'
            elif field in missing or value is None:
                state = 'missing'
            else:
                state = 'correct' if same(field, value, want) else 'wrong'
            comparisons[field] = {'status': state, 'expected': want, 'actual': value}
        rows.append({'file': name, 'group': str(entry.get('augment', 'unknown')),
                     'provider': detail.get('provider') if detail else None,
                     'model': detail.get('model') if detail else None,
                     'failure': failures.get(name, {'code': 'NO_RESULT', 'message': 'No detail returned for expected file'}) if not detail else None,
                     'fields': comparisons,
                     'exact_all': all(v['status'] in ('correct', 'correct_missing') for v in comparisons.values())})
    return {'integration_only': allow_simulated, 'summary': summarize(rows),
            'by_group': {g: summarize([r for r in rows if r['group'] == g]) for g in sorted({r['group'] for r in rows})},
            'batches': [e['batch'] for e in exports], 'rows': rows}


def markdown(report):
    title = '联调测试（不可作为真实识别准确率）' if report['integration_only'] else '识别字段对拍（11 字段口径）'
    lines = [f'# {title}', '', '只比识别字段，不评分 verdict。金额容差 0.01、税率数值相等、文本去空白、日期规范为 YYYY-MM-DD。',
             '缺失和失败保留在分母；GT-null 仅显式标缺失才正确。provider 不是准确率证明，输入导出由操作者提供。', '',
             '| 分组 | 样本数 | 11 字段全对 | 字段正确/总数 | 失败样本 | 缺失字段 |', '|---|---|---|---|---|---|']
    for group, v in {'all': report['summary'], **report['by_group']}.items():
        lines.append(f"| {group} | {v['count']} | {v['exact_all']}/{v['count']} | {v['correct_fields']}/{v['total_fields']} | {v['failed']} | {v['missing']} |")
    lines += ['', '| 字段 | 正确/总数 |', '|---|---|']
    for field, v in report['summary']['per_field'].items():
        lines.append(f"| {field} | {v['correct']}/{v['total']} |")
    lines += ['', '逐票实际值、预期值、来源和错误见同名 JSON。历史 9 字段成绩不能直接并入此 11 字段指标。']
    return '\n'.join(lines) + '\n'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    inputs = ap.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--files', nargs='+')
    inputs.add_argument('--manifest', type=Path)
    ap.add_argument('--base', default='http://127.0.0.1:8000')
    ap.add_argument('--exports', type=Path, nargs='+', help='Offline frontend JSON exports: no network calls')
    ap.add_argument('--allow-simulated', action='store_true')
    ap.add_argument('--output', type=Path, default=Path('verification/recognition-field-report.md'))
    a = ap.parse_args()
    if a.output.suffix.lower() != '.md':
        ap.error('--output must end in .md (a matching .json evidence file is also written)')
    manifest = json.loads(a.manifest.read_text(encoding='utf-8-sig')) if a.manifest else None
    groups = [[e['filename'] for e in b['files']] for b in manifest['batches']] if manifest else [a.files]
    names = [n for group in groups for n in group]
    gt = {e['file']: e for e in json.loads((DATASET / 'ground_truth.json').read_text(encoding='utf-8'))}
    if not names or len(set(names)) != len(names) or any(n not in gt for n in names):
        ap.error('Filenames must be nonempty, unique and present in GT')
    if any(not gt[n].get('is_invoice', True) for n in names):
        ap.error('Non-invoices require a separate detection benchmark')
    if manifest:
        for batch in manifest['batches']:
            for item in batch['files']:
                if hashlib.sha256((DATASET / item['filename']).read_bytes()).hexdigest() != item['sha256']:
                    ap.error(f"Input hash changed: {item['filename']}")
    if a.exports:
        exports = [json.loads(p.read_text(encoding='utf-8-sig')) for p in a.exports]
    else:
        base = a.base.rstrip('/')
        if not a.allow_simulated and get_json(base + '/api/health').get('recognition_provider') != 'openai-compat':
            ap.error('Backend is not configured for real recognition')
        exports = collect_online(base, groups)
    report = score([gt[n] for n in names], exports, a.allow_simulated)
    report['input_manifest'] = manifest
    report['exports'] = [str(p) for p in a.exports or []]
    report['generated_at'] = datetime.now(timezone.utc).isoformat()
    report['source'] = 'offline exports' if a.exports else a.base.rstrip('/')
    report['ground_truth_sha256'] = hashlib.sha256((DATASET / 'ground_truth.json').read_bytes()).hexdigest()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    a.output.write_text(markdown(report), encoding='utf-8')
    print(f'Report: {a.output}')


if __name__ == '__main__':
    main()
