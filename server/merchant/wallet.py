"""Signed wallet callbacks. A transport failure always leaves the outcome uncertain."""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from server.core.contracts import ServiceError
from .common import encode, signed_headers


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class WalletClient:
    def __init__(self, merchants, timeout=3):
        self.merchants, self.timeout = merchants, timeout
        self.opener = build_opener(NoRedirect)

    def call(self, merchant_id, action, payload):
        merchant = self.merchants[merchant_id]
        base = merchant['wallet_url']
        url = urlsplit(base)
        if (url.query or url.fragment or url.username or url.password or url.path not in ('', '/')
                or (url.scheme != 'https' and not
                    (url.scheme == 'http' and url.hostname in ('127.0.0.1', 'localhost', '::1')))):
            raise ServiceError('WALLET_CONFIG_INVALID', 'Use HTTPS, or a loopback HTTP wallet origin.', 503)
        path = '/wallet/v1/' + action
        body = encode(payload).encode()
        headers = signed_headers(merchant_id, merchant['merchant_secret'], path, body)
        request = Request(base.rstrip('/') + path, data=body, headers=headers, method='POST')
        try:
            try:
                response = self.opener.open(request, timeout=self.timeout)
            except HTTPError as error:
                response = error
            with response:
                raw = response.read(65537)
                if len(raw) > 65536:
                    raise ValueError('Oversized wallet response')
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise ValueError('Invalid wallet response envelope')
                if response.status >= 500:
                    raise ValueError('Wallet server error')
                if response.status != 200:
                    error = result.get('error') or {}
                    if not isinstance(error, dict):
                        raise ValueError('Invalid wallet error envelope')
                    # Only these outcomes are definitive application rejections.
                    if error.get('code') in ('INSUFFICIENT_BALANCE', 'TRANSACTION_CANCELED',
                                             'TRANSACTION_CONFLICT', 'ACCOUNT_NOT_FOUND',
                                             'CURRENCY_MISMATCH', 'ALREADY_REFUNDED', 'REFERENCE_INVALID'):
                        raise ServiceError(error['code'], error.get('message', error['code']), 409)
                    raise ValueError('Wallet rejected the callback')
            data = result['data']
            if (not isinstance(data, dict) or data.get('player_id') != payload.get('player_id')
                    or data.get('currency') != merchant['currency']
                    or type(data.get('minor_unit')) is not int or data['minor_unit'] != 100):
                raise ValueError('Wallet response identity or currency mismatch')
            def money(value):
                # Invalid replies are uncertain, never definitive rejections:
                # the remote wallet may already have committed the transaction.
                if type(value) is not int or not 0 <= value <= 9_000_000_000_000_000:
                    raise ValueError('Invalid wallet response amount')
                return value
            money(data['balance_minor'])
            if action in ('debit', 'credit', 'refund'):
                if (data.get('transaction_id') != payload['transaction_id'] or data.get('status') != 'applied'
                        or money(data.get('amount_minor')) != payload['amount_minor']):
                    raise ValueError('Wallet response transaction mismatch')
                before = money(data['balance_before_minor'])
                applied = money(data['applied_minor'])
                if (applied not in ((0, payload['amount_minor']) if action == 'refund' else (payload['amount_minor'],))
                        or data['balance_minor'] != before + (-applied if action == 'debit' else applied)):
                    raise ValueError('Wallet response balance equation mismatch')
            return data
        except ServiceError:
            raise
        except (OSError, URLError, ValueError, KeyError, TypeError):
            raise ServiceError('WALLET_UNCERTAIN', 'Wallet result is unknown; retry the same transaction.', 503) from None
