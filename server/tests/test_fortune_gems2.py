import json
import tempfile
import socket
import threading
import unittest
from pathlib import Path

from server.adapters.tada.fortune_gems2 import Adapter, pack, unpack
from server.core.contracts import ServiceError
from server.core.service import GameService
from server.games.catalog import create_registry
from server.games.fortune_gems2.engine import FortuneGems2, evaluate
from server.services.fortune_gems2_demo import build_server


class FortuneGems2Tests(unittest.TestCase):
    def test_life_service_authentication_and_heartbeat(self):
        with tempfile.TemporaryDirectory() as directory:
            server = build_server(0, Path(directory) / 'wallet.sqlite3')
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                token = server.service.create_session()['token']
                def connect():
                    sock = socket.create_connection(('127.0.0.1', server.server_port), timeout=3)
                    stream = sock.makefile('rb')
                    host = f'127.0.0.1:{server.server_port}'
                    sock.sendall((f'GET /lifeservice/ws2 HTTP/1.1\r\nHost: {host}\r\nOrigin: http://{host}\r\n'
                                  'Upgrade: websocket\r\nConnection: keep-alive,Upgrade\r\n'
                                  'Sec-WebSocket-Key: MDEyMzQ1Njc4OWFiY2RlZg==\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
                    self.assertIn(b'101', stream.readline())
                    while stream.readline() != b'\r\n':
                        pass
                    return sock, stream
                def send(sock, opcode, data):
                    mask = b'abcd'
                    sock.sendall(bytes([128 | opcode, 128 | len(data)]) + mask
                                 + bytes(v ^ mask[i % 4] for i, v in enumerate(data)))
                def receive(stream):
                    opcode, length = stream.read(2)
                    return opcode & 15, stream.read(length)
                sock, stream = connect()
                try:
                    send(sock, 2, b'\x22' + bytes([len(token)]) + token.encode())
                    self.assertEqual(receive(stream), (1, b'{"error":0}'))
                    send(sock, 1, b'{"cmdType":-1,"content":{}}')
                    send(sock, 9, b'alive')
                    self.assertEqual(receive(stream), (10, b'alive'))
                    send(sock, 1, b'{"cmdType":42}')
                    self.assertEqual(receive(stream)[0], 8)
                finally:
                    stream.close()
                    sock.close()
                sock, stream = connect()
                try:
                    send(sock, 2, b'\x22\x03bad')
                    self.assertEqual(receive(stream)[0], 8)
                finally:
                    stream.close()
                    sock.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_captured_line_awards(self):
        samples = json.loads(Path(__file__).with_name('fixtures').joinpath('fortune-gems2-spins.json').read_text())
        game = FortuneGems2()
        for sample in samples:
            spin = sample['spin']
            awards = evaluate([c['Col'] for c in spin['PlateSymbol']],
                              round(sample['request']['bet'] * 10000), spin.get('LineMult', 1),
                              game.config['paytable_fifths'])
            expected = [(a.get('Line', 0), a.get('Symbol', 0), a.get('Win', 0)) for a in spin['AwardDataVec']]
            self.assertEqual([(a['Line'], a['Symbol'], a['Win']) for a in awards], expected)
            self.assertAlmostEqual(sum(a['Win'] for a in awards) + spin.get('WheelWin', 0), sample['totalWin'])
            self.assertEqual(unpack('SpinAck', pack('SpinAck', spin)), spin)

    def test_wheel_sectors_and_wallet_totals(self):
        game = FortuneGems2()
        seen = set()
        for seed in range(1000):
            extra = bool(seed % 2)
            result = game.step(game.initial_state('x'), {'bet_minor':2000, 'extra':extra}, str(seed), str(seed + 1))
            spin = result.event['spin']
            self.assertEqual(result.debit_minor, 3000 if extra else 2000)
            self.assertEqual(result.credit_minor, round((spin['LineWin'] + spin['WheelWin']) * 10000))
            if extra:
                self.assertNotIn(8, spin['PlateSymbol'][3]['Col'])
            if spin['IsBonus']:
                seen.add(extra)
                self.assertEqual(len(spin['MultShowArray']), 12)
                index = game.config['wheel_odds'].index(spin['WheelOdd'])
                self.assertEqual(spin['MultShowArray'][index], spin['WheelMult'])
                self.assertAlmostEqual(spin['WheelWin'], .2 * spin['WheelOdd'] * spin['WheelMult'])
        self.assertEqual(seen, {False, True})

    def test_retry_round_end_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'wallet.sqlite3'
            service = GameService(path, create_registry(['fortune-gems2']))
            token = service.create_session()['token']
            adapter = Adapter(service)
            payload = pack('SpinReq', {'bet':.2, 'extraSpin':{}})
            first = adapter.handle(token, 0, payload, 'extra-1')
            balance = service.wallet(token)['balance_minor']
            response = unpack('SpinResponse', first['data'])
            self.assertEqual(round(response['postMoney'] * 10000), balance)
            self.assertEqual(balance, 20000000 - 3000 + round(response['totalWin'] * 10000))
            self.assertEqual(adapter.handle(token, 0, payload, 'extra-1'), first)
            for ack in (4, 36, 4):
                adapter.handle(token, ack, [], 'end')
                self.assertEqual(service.wallet(token)['balance_minor'], balance)
            restarted = GameService(path, create_registry(['fortune-gems2']))
            self.assertEqual(Adapter(restarted).handle(token, 0, payload, 'extra-1'), first)
            with self.assertRaises(ServiceError):
                adapter.handle(token, 0, pack('SpinReq', {'bet':.4}), 'extra-1')
            for request in ({'bet':.3}, {'bet':.2, 'extraSpin':{'Index':1}}, {'bet':float('nan')}):
                with self.assertRaises(ServiceError):
                    adapter.handle(token, 0, pack('SpinReq', request), 'invalid')
            self.assertEqual(service.wallet(token)['balance_minor'], balance)


if __name__ == '__main__':
    unittest.main()
