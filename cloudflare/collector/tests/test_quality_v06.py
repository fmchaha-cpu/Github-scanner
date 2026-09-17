from genshin_collector.main import _quality_metrics
from genshin_collector.models import ListingObservation, CoverageRow


def test_quality_metrics_surface_source_zero_yield_and_platform_seller_gap():
    rows = [
        ListingObservation(platform='PlayerUp', url=f'https://x/{i}', title='EU account', server='EU', price_value=20, currency='USD')
        for i in range(5)
    ]
    coverage = [CoverageRow(
        platform='PlayerAuctions', query_family='eu_all', status='ok:browser', result_count=0,
        fetch_mode='browser', html_bytes=20000, text_chars=5000, anchor_count=50,
        detail_link_count=0, parsed_count=0, content_hash='same', fallback_reason='zero_detail_links',
    )]
    m = _quality_metrics(rows, coverage, [])
    assert 'source_zero_yield:PlayerAuctions' in m['improvement_signals']
    assert 'seller_extraction_low:PlayerUp' in m['improvement_signals']
    assert m['coverage_diagnostics']['PlayerAuctions']['zero_detail_link_pages'] == 1


def test_quality_metrics_detect_repeated_page_content_across_queries():
    coverage = []
    for i in range(3):
        coverage.append(CoverageRow(
            platform='PlayerAuctions', query_family=f'q{i}', query_text=f'query {i}', path_key=f'p{i}',
            status='ok:http', result_count=0, fetch_mode='http', html_bytes=20000, text_chars=5000,
            anchor_count=20, detail_link_count=0, parsed_count=0, content_hash='identical',
        ))
    m = _quality_metrics([], coverage, [])
    assert 'same_content_across_queries' in m['improvement_signals']
    assert m['repeated_content_groups'][0]['paths'] == 3


def test_quality_metrics_surface_detail_pattern_drift_samples():
    coverage = [CoverageRow(
        platform='PlayerAuctions', query_family='eu_all', status='ok:browser', result_count=0,
        fetch_mode='browser', html_bytes=25000, text_chars=7000, anchor_count=80,
        detail_link_count=0, parsed_count=0, content_hash='x',
        unmatched_listing_like_count=2,
        sample_unmatched_listing_like_urls=['https://example/offer-1', 'https://example/offer-2'],
    )]
    m = _quality_metrics([], coverage, [])
    assert 'detail_pattern_drift_suspected:PlayerAuctions' in m['improvement_signals']
    assert m['coverage_diagnostics']['PlayerAuctions']['unmatched_listing_like_links'] == 2


def test_quality_metrics_detect_repeated_http_probe_content_across_queries():
    coverage = []
    for i in range(3):
        coverage.append(CoverageRow(
            platform='PlayerAuctions', query_family=f'q{i}', query_text=f'query {i}', path_key=f'p{i}',
            status='ok:browser', result_count=1, fetch_mode='browser', html_bytes=20000, text_chars=5000,
            anchor_count=20, detail_link_count=1, parsed_count=1, content_hash=f'final-{i}',
            http_probe_content_hash='same-http-shell', http_probe_detail_link_count=0,
            fallback_reason='zero_detail_links',
        ))
    m = _quality_metrics([], coverage, [])
    assert 'same_http_probe_content_across_queries' in m['improvement_signals']
    assert m['repeated_http_probe_content_groups'][0]['paths'] == 3
