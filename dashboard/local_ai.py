"""Local-only Ollama transport. Never falls back to a paid provider."""
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def configuration():
    provider = os.environ.get('ASCENTIQ_AI_PROVIDER', 'openai').strip().lower()
    enabled = os.environ.get('ASCENTIQ_AI_ENABLED', 'true') == 'true'
    if provider == 'ollama':
        model = os.environ.get('OLLAMA_MODEL', 'qwen3.5:4b').strip() or 'qwen3.5:4b'
        return {'provider': provider, 'model': model, 'configured': enabled and valid_model(model),
                'local': True}
    return {'provider': provider, 'model': os.environ.get('OPENAI_MODEL', 'gpt-5'),
            'configured': enabled and provider == 'openai' and bool(os.environ.get('OPENAI_API_KEY', '').strip()),
            'local': False}


def valid_model(model):
    return bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}', model)) and 'cloud' not in model.lower()


def base_url():
    value = os.environ.get('OLLAMA_BASE_URL', 'http://ollama:11434').rstrip('/')
    parsed = urlsplit(value)
    if (parsed.scheme != 'http' or parsed.hostname not in {'ollama', 'localhost', '127.0.0.1', 'host.docker.internal'}
            or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
        raise ValueError('Configure um endereço local do Ollama; provedores de nuvem não são permitidos neste modo.')
    return value


def messages(instructions, content):
    result = [{'role': 'system', 'content': instructions}]
    if isinstance(content, str):
        return result + [{'role': 'user', 'content': content}]
    for message in content:
        parts = message.get('content', [])
        if isinstance(parts, str):
            result.append({'role': message.get('role', 'user'), 'content': parts})
            continue
        text, images = [], []
        for part in parts:
            if part.get('type') == 'input_text':
                text.append(part.get('text', ''))
            elif part.get('type') == 'input_image':
                image = part.get('image_url', '')
                if not image.startswith(('data:image/jpeg;base64,', 'data:image/png;base64,', 'data:image/webp;base64,')):
                    raise ValueError('A análise local aceita somente imagens anexadas, sem URLs externas.')
                images.append(image.split(',', 1)[1])
        result.append({'role': message.get('role', 'user'), 'content': '\n'.join(text),
                       **({'images': images} if images else {})})
    return result


def request_text(instructions, content, *, json_output=False, schema=None, max_tokens=2000):
    config = configuration()
    if config['provider'] != 'ollama' or not config['configured']:
        raise ValueError('O modelo local não está configurado.')
    payload = {'model': config['model'], 'messages': messages(instructions, content),
               'stream': False, 'think': False, 'keep_alive': '5m',
               'options': {'temperature': 0, 'num_ctx': 8192, 'num_predict': max_tokens}}
    if schema or json_output:
        payload['format'] = schema or 'json'
    request = Request(base_url() + '/api/chat', data=json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=180) as response:
            result = json.loads(response.read(2 * 1024 * 1024))
    except HTTPError as error:
        detail = ('O modelo local não foi encontrado no Ollama. Baixe o modelo configurado.' if error.code == 404
                  else 'O Ollama não conseguiu executar o modelo. Confira o serviço e a memória disponível.')
        raise RuntimeError(detail) from error
    except (URLError, TimeoutError, OSError) as error:
        raise RuntimeError('O Ollama local não respondeu. Confira se o container está ligado e tente novamente.') from error
    except (ValueError, TypeError) as error:
        raise RuntimeError('O Ollama retornou uma resposta inválida; seus registros foram preservados.') from error
    text = result.get('message', {}).get('content', '').strip()
    if not result.get('done') or result.get('done_reason') == 'length' or not text:
        raise RuntimeError('O modelo local não concluiu a estimativa. Simplifique a descrição ou tente novamente.')
    return text
