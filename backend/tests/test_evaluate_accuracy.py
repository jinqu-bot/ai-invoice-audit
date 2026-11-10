"""Offline contract/scoring regressions; never call a model or production API."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('evaluate_accuracy', Path(__file__).resolve().parents[1] / 'scripts/evaluate_accuracy.py')
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


def sample(name='real_01.jpg'):
    entry = {field: 'value' for field in ev.FIELDS}
    entry.update(file=name, augment='real_photo', is_invoice=True, invoice_date='2026-10-24',
                 amount_excl_tax=0, tax_amount=0, amount_incl_tax=0, tax_rate=0.06)
    detail = {'filename': name, 'fields': {f: entry[f] for f in ev.FIELDS},
              'missing_fields': [], 'provider': 'openai-compat', 'model': 'test', 'verdict': 'reject'}
    return entry, detail


def export(details, failures=None):
    return {'batch': {'status': 'done'}, 'invoices': details, 'failures': failures or []}


def test_failed_and_missing_fields_stay_in_denominator():
    entry, detail = sample()
    other, _ = sample('real_02.jpg')
    detail['missing_fields'] = ['amount_incl_tax']  # Placeholder zero must not count.
    report = ev.score([entry, other], [export([detail])])
    assert report['summary']['total_fields'] == 22
    assert report['summary']['correct_fields'] == 10
    assert report['summary']['failed'] == 1
    assert report['summary']['missing'] == 1
    assert report['summary']['exact_all'] == 0


def test_gt_null_requires_explicit_missing_marker():
    entry, detail = sample()
    entry['amount_incl_tax'] = None
    assert ev.score([entry], [export([detail])])['summary']['exact_all'] == 0
    detail['missing_fields'] = ['amount_incl_tax']
    assert ev.score([entry], [export([detail])])['summary']['exact_all'] == 1


def test_verdict_does_not_affect_recognition():
    entry, detail = sample()
    entry['expected_verdict'] = 'pass'
    assert ev.score([entry], [export([detail])])['summary']['exact_all'] == 1


@pytest.mark.parametrize('provider', ['mock-vlm', 'fixture', None])
def test_simulated_and_unknown_sources_rejected(provider):
    entry, detail = sample()
    detail['provider'] = provider
    with pytest.raises(ValueError, match='source'):
        ev.score([entry], [export([detail])])
    assert ev.score([entry], [export([detail])], True)['integration_only']


def test_duplicate_and_unknown_filenames_rejected():
    entry, detail = sample()
    with pytest.raises(ValueError, match='duplicate'):
        ev.score([entry], [export([detail, detail])])
    detail['filename'] = 'wrong.jpg'
    with pytest.raises(ValueError, match='Unexpected'):
        ev.score([entry], [export([detail])])


def test_comparison_tolerances_and_normalization():
    assert ev.same('amount_incl_tax', 100.01, 100)
    assert not ev.same('amount_incl_tax', 100.011, 100)
    assert not ev.same('amount_incl_tax', None, 0)
    assert ev.same('invoice_date', '2026/1/2', '2026-01-02')
    assert ev.same('buyer_name', '甲 \n乙', '甲乙')
    assert not ev.same('tax_rate', 6, 0.06)


@pytest.mark.parametrize('status', ['done', 'partial', 'failed'])
def test_reads_nested_terminal_status(monkeypatch, status):
    result = {'batch': {'status': status}, 'items': [], 'failures': []}
    monkeypatch.setattr(ev, 'get_json', lambda url: result)
    assert ev.get_results('http://test', 'B1') is result


def test_uploads_preserve_groups_and_limit_then_fetch_details(monkeypatch):
    sizes, urls = [], []
    def post(base, files):
        sizes.append(len(files))
        return f'B{len(sizes)}'
    monkeypatch.setattr(ev, 'post_batch', post)
    monkeypatch.setattr(ev, 'get_results', lambda *args: {'batch': {'status': 'done'},
                         'items': [{'invoice_id': 'INV-1'}], 'failures': []})
    def get(url):
        urls.append(url)
        return {'filename': 'a.jpg', 'fields': {}}
    monkeypatch.setattr(ev, 'get_json', get)
    ev.collect_online('http://test', [[str(i) for i in range(12)], [str(i) for i in range(12)]])
    assert sizes == [12, 12]
    assert all(url.endswith('/api/invoices/INV-1') for url in urls)
    sizes.clear()
    ev.collect_online('http://test', [[str(i) for i in range(24)]])
    assert sizes == [20, 4]


def test_all_failed_report_has_no_zero_division():
    entry, _ = sample()
    report = ev.score([entry], [{'batch': {'status': 'failed'}, 'invoices': [],
                               'failures': [{'filename': entry['file'], 'message': 'timeout'}]}])
    assert report['summary']['failed'] == 1
    assert report['summary']['total_fields'] == 11
    assert '0/11' in ev.markdown(report)


def test_offline_frontend_export_never_calls_network(monkeypatch, tmp_path):
    import json
    import sys
    entry, detail = sample()
    (tmp_path / 'ground_truth.json').write_text(json.dumps([entry]), encoding='utf-8')
    source = tmp_path / 'frontend.json'
    source.write_text(json.dumps(export([detail])), encoding='utf-8')
    output = tmp_path / 'report.md'
    monkeypatch.setattr(ev, 'DATASET', tmp_path)
    monkeypatch.setattr(ev, 'get_json', lambda *args: pytest.fail('offline called network'))
    monkeypatch.setattr(ev, 'collect_online', lambda *args: pytest.fail('offline uploaded'))
    monkeypatch.setattr(sys, 'argv', ['evaluate_accuracy.py', '--files', entry['file'],
                                   '--exports', str(source), '--output', str(output)])
    ev.main()
    assert json.loads(output.with_suffix('.json').read_text(encoding='utf-8'))['summary']['exact_all'] == 1
