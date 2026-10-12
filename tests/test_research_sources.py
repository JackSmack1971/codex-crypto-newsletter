import json
import sys
import unittest
from pathlib import Path
from urllib.error import URLError
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from controlplane import ControlPlaneError
import research_sources as rs


class FakeResponse:
    status = 200
    def __init__(self, body=b'{"pairs":[]}'): self.body = body
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, n): return self.body[:n]


class FakeOpener:
    def __init__(self, body=b'{"pairs":[]}'): self.body = body; self.calls = 0
    def open(self, request, timeout):
        self.calls += 1
        assert timeout == 12
        assert request.full_url.startswith('https://api.')
        return FakeResponse(self.body)


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


if __name__ == '__main__': unittest.main()
