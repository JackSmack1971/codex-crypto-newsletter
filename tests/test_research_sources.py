import json
import sys
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from controlplane import ControlPlaneError
import research_sources as rs


class FakeResponse:
    status = 200
    def __init__(self, body=b'{"pairs":[]}', url='https://api.dexscreener.com/latest/dex/search?q=SOL'): self.body = body; self.url = url
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, n): return self.body[:n]
    def geturl(self): return self.url


class RedirectResponse(FakeResponse):
    def geturl(self): return 'https://attacker.invalid/collect'


class FakeOpener:
    def __init__(self, body=b'{"pairs":[]}'): self.body = body; self.calls = 0
    def open(self, request, timeout):
        self.calls += 1
        assert timeout == 12
        assert request.full_url.startswith('https://api.')
        return FakeResponse(self.body, request.full_url)


class FailingOpener:
    def open(self, request, timeout): raise URLError('offline')


class ResearchSourcesTests(unittest.TestCase):
    def setUp(self):
        rs._CACHE.clear(); rs._FAILURES.clear(); rs._OPEN_UNTIL.clear()

    def test_active_search_route_contracts(self):
        for route, query in [('dex-pair-search', 'SOL/USDC'), ('coinpaprika-search', 'AERO')]:
            result = rs.fetch(route, query, opener=FakeOpener())
            self.assertEqual(result['status'], 'OK')
            self.assertEqual(result['kind'], 'discovery')
            self.assertEqual(result['data'], {'pairs': []})
            self.assertEqual(result['source'], rs.PROVIDERS[result['provider']]['source'])
            self.assertIsNotNone(result['retrieved_at'])

    def test_coinpaprika_observation_route_normalizes_native_fields(self):
        body = b'[{"id":"sol-solana","name":"Solana","symbol":"SOL","quotes":{"USD":{"price":123,"volume_24h":456,"market_cap":789}},"last_updated":"2026-10-11T00:00:00Z"}]'
        with patch.object(rs, 'normalize_observation', wraps=rs.normalize_observation) as normalize:
            result = rs.fetch('coinpaprika-ticker', 'sol-solana', opener=FakeOpener(body))
        self.assertEqual(result['kind'], 'observation')
        self.assertEqual(len(result['observations']), 1)
        self.assertEqual(result['observations'][0]['token_id'], 'sol-solana')
        # Provider payload is preserved even when this schema needs a future mapping refinement.
        self.assertEqual(result['observations'][0]['raw']['symbol'], 'SOL')

    def test_normalizer_handles_dex_pair_nested_market_fields(self):
        row = {'chainId': 'base', 'dexId': 'uniswap', 'pairAddress': '0xpair', 'priceUsd': '2.5',
               'baseToken': {'address': '0xtoken'}, 'volume': {'h24': 500}, 'liquidity': {'usd': 900},
               'pairCreatedAt': 123456789}
        obs = rs.normalize_observation('dexscreener', row)[0]
        self.assertEqual((obs['price'], obs['volume'], obs['liquidity']), ('2.5', 500, 900))
        self.assertEqual((obs['exchange'], obs['chain'], obs['contract_address']), ('uniswap', 'base', '0xtoken'))
        self.assertIsNone(obs['native_observation_time'])

    def test_registry_records_candidates_but_keeps_them_disabled(self):
        reg = rs.registry()
        for name in ('defillama', 'geckoterminal', 'ccxt-public', 'hyperliquid'):
            self.assertFalse(reg[name]['active'])
            self.assertEqual(reg[name]['operations'], [])
            self.assertIn('fees', reg[name]); self.assertIn('quota', reg[name])

    def test_unauthorized_and_candidate_requests_fail_closed_before_network(self):
        with self.assertRaises((PermissionError, ControlPlaneError)):
            rs.fetch('dex-pair-search', 'SOL', policy_path=Path(__file__).parent / 'missing-policy.json', opener=FakeOpener())
        with self.assertRaises(ValueError): rs.fetch('hyperliquid-mids', 'allMids', opener=FakeOpener())

    def test_policy_denies_removed_source_before_network(self):
        policy_path = Path(__file__).resolve().parents[1] / '.codex/source-policy.json'
        policy = json.loads(policy_path.read_text(encoding='utf-8'))
        policy['sources'] = [s for s in policy['sources'] if s['id'] != 'dexscreener-market-data']
        with patch.object(rs, 'load_source_policy', return_value=policy):
            with self.assertRaises(PermissionError): rs.fetch('dex-pair-search', 'SOL', opener=FakeOpener())

    def test_outage_is_explicit_unknown_and_circuit_breaker_opens(self):
        now = [100.0]
        for _ in range(3):
            result = rs.fetch('dex-pair-search', 'SOL', opener=FailingOpener(), retries=0, now=lambda: now[0])
            self.assertEqual(result['status'], 'UNKNOWN')
        blocked = rs.fetch('dex-pair-search', 'SOL', opener=FakeOpener(), now=lambda: now[0])
        self.assertEqual(blocked['reason'], 'circuit_open')

    def test_cache_avoids_duplicate_request_and_does_not_merge_observations(self):
        op = FakeOpener(b'[{"price":1},{"price":2}]')
        a = rs.fetch('coinpaprika-ticker', 'same-id', opener=op)
        b = rs.fetch('coinpaprika-ticker', 'same-id', opener=op)
        self.assertEqual(op.calls, 1)
        self.assertEqual(len(a['observations']), 2)
        self.assertEqual([x['price'] for x in a['observations']], [1, 2])
        self.assertEqual(a, b)

    def test_offline_replay_preserves_conflicting_fixture_rows(self):
        fixture = Path(__file__).parent / 'fixtures' / 'market-observations.json'
        values = rs.replay(fixture)
        self.assertEqual(len(values), 2)
        self.assertEqual([v['price'] for v in values], [1.0, 1.1])
        self.assertNotEqual(values[0]['provider'], values[1]['provider'])

    def test_bad_route_query_and_retry_bound_rejected(self):
        with self.assertRaises(ValueError): rs.fetch('arbitrary-url', 'x', opener=FakeOpener())
        with self.assertRaises(ValueError): rs.fetch('dex-pair-search', 'x' * 97, opener=FakeOpener())
        with self.assertRaises(ValueError): rs.fetch('dex-pair-search', 'SOL', retries=3, opener=FakeOpener())

    def test_adapter_replay_is_authorized_offline_and_provenance_hashes_are_stable(self):
        fixture = Path(__file__).parent / 'fixtures' / 'market-observations.json'
        first = rs.execute('replay', replay_path=fixture)
        second = rs.execute('replay', replay_path=fixture)
        self.assertEqual(first, second)
        self.assertEqual(first['status'], 'OK')
        item = first['observations'][0]
        self.assertFalse(item['provenance']['live_source_verified'])
        self.assertEqual('SIMULATED_REPLAY', item['provenance']['source_status'])
        self.assertEqual(rs._digest(item['observation']), item['provenance']['normalized_artifact_sha256'])
        with self.assertRaises(ValueError): rs.execute('unknown')

    def test_live_rest_requires_authorization_known_operation_and_budget(self):
        spec = [{'route': 'dex-pair-search', 'query': 'SOL'}]
        op = FakeOpener(b'{"pairs":[{"chainId":"base","baseToken":{"address":"0xabc"},"priceUsd":"1.2"}]}')
        with self.assertRaises(PermissionError): rs.execute('live-rest', requests=spec, opener=op)
        with self.assertRaises(ValueError): rs.execute('live-rest', requests=[{'route': 'not-a-route', 'query': 'SOL'}], authorized=True, opener=op)
        with self.assertRaises(PermissionError): rs.execute('live-rest', requests=spec * 2, authorized=True, opener=op, max_requests=1)
        result = rs.execute('live-rest', requests=spec, authorized=True, opener=op)
        self.assertEqual(result['status'], 'OK')
        self.assertEqual(op.calls, 1)
        p = result['observations'][0]['provenance']
        self.assertEqual('LIVE_RETRIEVED', p['source_status'])
        self.assertEqual('network_contract', p['canonical_asset_identity']['method'])
        self.assertEqual(rs._digest(result['observations'][0]['observation']), p['normalized_artifact_sha256'])
        self.assertEqual(1, p['request_count'])

    def test_redirect_rejected_and_host_allowlist_is_enforced(self):
        class Opener:
            calls = 0
            def open(self, request, timeout):
                self.calls += 1
                return RedirectResponse(b'{"pairs":[]}')
        op = Opener()
        result = rs.fetch('dex-pair-search', 'SOL', opener=op, retries=0)
        self.assertEqual('UNKNOWN', result['status'])
        self.assertEqual(1, op.calls)
        original = rs.ROUTES['dex-pair-search']
        try:
            rs.ROUTES['dex-pair-search'] = ('dexscreener', 'https://attacker.invalid/search', 'q', 'discovery')
            with self.assertRaises(PermissionError): rs.fetch('dex-pair-search', 'SOL', opener=FakeOpener(), retries=0)
        finally:
            rs.ROUTES['dex-pair-search'] = original

    def test_timeout_malformed_oversized_and_partial_failures_are_explicit(self):
        class TimeoutOpener:
            def open(self, request, timeout): raise TimeoutError('secret response text')
        result = rs.execute('live-rest', requests=[{'route': 'dex-pair-search', 'query': 'X'}], authorized=True, opener=TimeoutOpener())
        self.assertEqual('DEGRADED', result['status'])
        self.assertEqual('TimeoutError', result['failures'][0]['error_type'])
        with self.assertRaises(json.JSONDecodeError): rs.fetch('dex-pair-search', 'bad-json', opener=FakeOpener(b'{'), retries=0)
        with self.assertRaises(ValueError): rs.fetch('dex-pair-search', 'too-big', opener=FakeOpener(b' ' * (rs.MAX_RESPONSE_BYTES + 1)), retries=0)
        rs._CACHE.clear(); rs._FAILURES.clear(); rs._OPEN_UNTIL.clear()
        class PartialOpener:
            calls = 0
            def open(self, request, timeout):
                self.calls += 1
                if self.calls == 1:
                    return FakeResponse(b'{"pairs":[{"chainId":"base","baseToken":{"address":"0xab"}}]}', request.full_url)
                raise TimeoutError('provider failed')
        partial = rs.execute('live-rest', requests=[{'route': 'dex-pair-search', 'query': 'good'}, {'route': 'dex-pair-search', 'query': 'bad'}],
                             authorized=True, opener=PartialOpener())
        self.assertEqual('PARTIAL', partial['status'])

    def test_rate_limit_is_explicit_and_does_not_retry_in_adapter(self):
        class RateLimited:
            calls = 0
            def open(self, request, timeout):
                self.calls += 1
                raise HTTPError(request.full_url, 429, 'rate limited', {}, None)
        opener = RateLimited()
        result = rs.execute('live-rest', requests=[{'route': 'dex-pair-search', 'query': 'limited'}],
                             authorized=True, opener=opener)
        self.assertEqual('DEGRADED', result['status'])
        self.assertEqual(1, opener.calls)
        self.assertEqual(1, result['request_count'])

    def test_unresolved_identity_and_live_mcp_fail_closed(self):
        with self.assertRaises(ValueError): rs._canonical_identity({'ticker': 'SAME'})
        mcp = rs.execute('live-mcp')
        self.assertEqual('BLOCKED', mcp['status'])
        self.assertFalse(mcp['observations'])

    def test_adapter_drops_sensitive_provider_fields_before_artifact(self):
        body = b'{"pairs":[{"chainId":"base","baseToken":{"address":"0xabc"},"email":"private@example.test","api_key":"secret"}]}'
        result = rs.execute('live-rest', requests=[{'route': 'dex-pair-search', 'query': 'sanitize'}],
                            authorized=True, opener=FakeOpener(body))
        row = result['observations'][0]['observation']
        self.assertNotIn('email', row['raw'])
        self.assertNotIn('api_key', row['raw'])


if __name__ == '__main__': unittest.main()
