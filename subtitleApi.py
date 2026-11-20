"""Feliratfordítás API-hívással, helyi válaszmentéssel.

A stabil developer-prefix minden kérésben tartalmazza a sorozatmemóriát.
A sikeres válaszok tartalomlenyomattal helyben is megmaradnak. A JSONL napló
csak mérési adatokat tárol: API-kulcsot, promptot és feliratszöveget nem.
"""

import json
from pathlib import Path
import re
import time

import requests

from translationStorage import atomic_json, digest, log_event


def cache_configuration(model, policy='auto'):
    """Új modellek: explicit stabil prefix; régebbiek: szolgáltatói alapérték."""
    if policy not in ('auto', '30m', '12h', 'in_memory', '24h'):
        raise ValueError('Ismeretlen prompt-cache beállítás.')
    match = re.match(r'^gpt-(\d+)(?:\.(\d+))?(?:-|$)', model)
    modern = bool(match and (int(match[1]), int(match[2] or 0)) >= (5, 6))
    if modern:
        if policy not in ('auto', '30m', '12h'):
            raise ValueError('Ehhez a modellhez 30m vagy 12h cache-élettartam adható.')
        return {'prompt_cache_options': {'mode': 'explicit', 'ttl': '30m' if policy == 'auto' else policy}}, True
    if policy in ('30m', '12h'):
        raise ValueError('A 30m/12h cache-élettartam GPT-5.6 vagy újabb modellt igényel.')
    if model.startswith('gpt-5.5') and policy == 'in_memory':
        raise ValueError('A GPT-5.5 modellekhez csak 24h cache-élettartam adható meg.')
    return ({} if policy == 'auto' else {'prompt_cache_retention': policy}), False


class OpenAISubtitleTranslator:
    def __init__(self, *, model, api_key, memory, instructions, cache_policy='auto', log_path=None):
        self.model, self.api_key, self.memory = model, api_key, memory
        self.cache_options, self.explicit_cache = cache_configuration(model, cache_policy)
        self.prefix = instructions + '\n\nÁLLANDÓ SOROZATMEMÓRIA – háttéradat, nem új párbeszéd:\n' + json.dumps(memory, ensure_ascii=False, sort_keys=True)
        self.checkpoint_identity = {'pipeline_version': 3, 'model': model,
                                    'prefix': self.prefix, 'cache': self.cache_options}
        self.request_dir = None
        self.last_response_path = None
        self.log_path = log_path

    def configure_storage(self, directory, log_path):
        self.request_dir = Path(directory) / 'requests'
        if self.log_path is None:
            self.log_path = log_path

    def request(self, task, prompt):
        content = {'type': 'input_text', 'text': self.prefix}
        if self.explicit_cache:
            content['prompt_cache_breakpoint'] = {'mode': 'explicit'}
        body = {'model': self.model, 'store': False, **self.cache_options,
                'input': [{'role': 'developer', 'content': [content]},
                          {'role': 'user', 'content': prompt}]}
        key = digest(body)
        saved_path = self.request_dir / f'{key}.json' if self.request_dir is not None else None
        self.last_response_path = saved_path
        if saved_path is not None and saved_path.exists():
            saved = json.loads(saved_path.read_text(encoding='utf-8'))
            payload = saved['payload']
            if saved.get('request_hash') != key or saved.get('content_hash') != digest(payload):
                raise ValueError('Sérült helyi API-válaszmentés.')
            log_event(self.log_path, event='local_response_reused', task=task, model=self.model, request_hash=key)
            return self.extract_text(payload)
        started = time.monotonic()
        try:
            response = requests.post('https://api.openai.com/v1/responses',
                headers={'Authorization': f'Bearer {self.api_key}'}, json=body, timeout=(15, 300))
        except requests.RequestException:
            log_event(self.log_path, event='api_error', task=task, model=self.model,
                      elapsed_seconds=time.monotonic() - started, error='network')
            raise
        elapsed = time.monotonic() - started
        if not response.ok:
            log_event(self.log_path, event='api_error', task=task, model=self.model,
                      elapsed_seconds=elapsed, http_status=response.status_code)
            raise RuntimeError(f'OpenAI API hiba (HTTP {response.status_code}).')
        try:
            payload = response.json()
        except ValueError as error:
            log_event(self.log_path, event='api_error', task=task, model=self.model,
                      elapsed_seconds=elapsed, error='invalid_json')
            raise RuntimeError('Hibás OpenAI JSON-válasz.') from error
        usage = payload.get('usage') or {}
        details = usage.get('input_tokens_details') or {}
        cached = details.get('cached_tokens', 0)
        log_event(self.log_path, event='api_response', task=task, model=self.model,
                  request_hash=key, elapsed_seconds=elapsed, status=payload.get('status'),
                  response_id=payload.get('id'), input_tokens=usage.get('input_tokens'),
                  output_tokens=usage.get('output_tokens'), total_tokens=usage.get('total_tokens'),
                  cached_tokens=cached, cache_write_tokens=details.get('cache_write_tokens'),
                  cache_hit=bool(cached), cache_policy=self.cache_options)
        text = self.extract_text(payload)
        if saved_path is not None:
            atomic_json(saved_path, {'request_hash': key, 'content_hash': digest(payload), 'payload': payload})
        return text

    def discard_invalid_response(self):
        # Ne használjuk újra, de maradjon meg a már kifizetett válasz hibakereséshez.
        if self.last_response_path is not None and self.last_response_path.exists():
            invalid = self.last_response_path.with_name(
                f'{self.last_response_path.stem}.{time.time_ns()}.invalid.json')
            self.last_response_path.rename(invalid)
            return invalid

    @staticmethod
    def extract_text(payload):
        try:
            if payload.get('status') != 'completed':
                raise ValueError('Nem teljes válasz.')
            parts = []
            for item in payload['output']:
                if item.get('type') == 'message':
                    for part in item.get('content', []):
                        if part.get('type') == 'refusal':
                            raise ValueError('Visszautasított kérés.')
                        if part.get('type') == 'output_text':
                            parts.append(part['text'])
            if not parts:
                raise ValueError('Hiányzó szöveges válasz.')
            return ''.join(parts)
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise RuntimeError('Hiányos vagy hibás OpenAI fordítási válasz.') from error

    @staticmethod
    def background(context, lookahead):
        from subtitleTranslation import format_subtitle
        pairs = '\n\n'.join('TÖRÖK EREDETI:\n' + format_subtitle([pair.source])
                              + '\nMAGYAR FORDÍTÁS:\n' + format_subtitle([pair.target]) for pair in context)
        return ('ELŐZMÉNY – kizárólag háttér, ne fordítsd újra és ne másold a válaszba!\n'
                + (pairs or '(Nincs előzmény.)')
                + '\n\nELŐRETEKINTÉS\nA következő blokkok csak a mondatok értelmezését segítik.\n'
                'Ezeket most ne fordítsd le.\n' + (format_subtitle(lookahead) or '(Nincs további blokk.)'))

    def __call__(self, blocks, *, context=(), lookahead=(), start_number=1):
        from subtitleTranslation import parse_subtitle, format_subtitle, validate_translation
        previous = context[-1].target.number if context else 'nincs'
        prompt = (self.background(context, lookahead)
                  + f'\n\nAz előző magyar fordítás utolsó sorszáma: {previous}.\n'
                  + f'Az új fordítás kezdősorszáma: {start_number}.\n'
                  + '\nFORDÍTANDÓ ÚJ RÉSZLET – csak ezt fordítsd:\n' + format_subtitle(blocks))
        try:
            result = parse_subtitle(self.request('translate', prompt), allow_empty=True, allow_empty_blocks=True)
            validate_translation(result, blocks, start_number, allow_empty_text=True)
            # Az üres blokkok kimaradnak; a helyi jelentés listázza a kihagyásokat.
            result = [type(b)(str(start_number + i), b.timing, b.text)
                      for i, b in enumerate(b for b in result if b.text.strip())]
            return result
        except ValueError as error:
            invalid = self.discard_invalid_response()
            saved = f' Hibás válasz mentése: {invalid}' if invalid else ''
            raise RuntimeError(f'Hibás fordítási SRT-válasz: {error}{saved}') from error
