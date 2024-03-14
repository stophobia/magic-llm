# https://docs.anthropic.com/claude/reference/messages-streaming

import json
import traceback
import urllib.request
import time

from magic_llm.engine.base_chat import BaseChat
from magic_llm.model import ModelChat, ModelChatResponse


class EngineAnthropic(BaseChat):
    def __init__(self,
                 api_key: str,
                 **kwargs) -> None:
        super().__init__(**kwargs)
        self.base_url = 'https://api.anthropic.com/v1/messages'
        self.api_key = api_key

    def prepare_data(self, chat: ModelChat, **kwargs):
        # Construct the header and data to be sent in the request.
        preamble = None
        if chat.messages[0]['role'] == 'system':
            preamble = c if (c := chat.messages.pop(0)['content']) else None

        headers = {
            'Content-Type': 'application/json',
            'x-api-key': f'{self.api_key}',
            'anthropic-version': '2023-06-01',
            'anthropic-beta': 'messages-2023-12-15',
            'accept': 'application/json',
            'user-agent': 'arz-magic-llm-engine',
            **self.headers
        }

        data = {
            "model": self.model,
            "messages": chat.messages,
            "stream": self.stream,
            **self.kwargs
        }
        if preamble is not None:
            data['system'] = preamble

        # Convert the data dictionary to a JSON string.
        json_data = json.dumps(data).encode('utf-8')

        # Create a request object with the URL, data, and headers.
        return urllib.request.Request(self.base_url, data=json_data, headers=headers)

    def generate(self, chat: ModelChat, **kwargs) -> ModelChatResponse:
        raise NotImplementedError

    def stram_generate(self, chat: ModelChat, **kwargs):
        # Make the request and read the response.
        with urllib.request.urlopen(self.prepare_data(chat, **kwargs)) as response:
            idx = None
            usage = None
            finish_reason = None
            for chunk in response:
                if chunk:
                    evt = chunk.decode().split('data:')
                    if len(evt) != 2:
                        continue
                    event = json.loads(evt[-1])
                    if event['type'] == 'message_start':
                        idx = event['message']['id']
                        meta = event['message']['usage']
                        usage = {
                            "prompt_tokens": meta['input_tokens'],
                            "completion_tokens": meta['output_tokens'],
                            "total_tokens": meta['input_tokens'] + meta['output_tokens']
                        }
                    elif event['type'] == 'content_block_start':
                        print(event)
                        pass
                    elif event['type'] == 'message_delta':
                        finish_reason = event['delta']['stop_reason']
                        meta = event['usage']
                        usage['completion_tokens'] = meta['output_tokens']
                        usage['total_tokens'] += meta['output_tokens']
                    elif event['type'] == 'content_block_delta':
                        chunk = {
                            'id': idx,
                            'choices':
                                [{
                                    'delta':
                                        {
                                            'content': event['delta']['text'],
                                            'role': None
                                        },
                                    'finish_reason': finish_reason,
                                    'index': 0
                                }],
                            'created': int(time.time()),
                            'model': self.model,
                            'usage': usage,
                            'object': 'chat.completion.chunk'
                        }
                        chunk = json.dumps(chunk)
                        yield f'data: {chunk}\n'
                        yield f'\n'
            chunk = {
                'id': idx,
                'choices':
                    [{
                        'delta':
                            {
                                'content': '',
                                'role': None
                            },
                        'finish_reason': None,
                        'index': 0
                    }],
                'created': int(time.time()),
                'model': self.model,
                'usage': usage,
                'object': 'chat.completion.chunk'
            }
            chunk = json.dumps(chunk)
            yield f'data: {chunk}\n'
            yield f'\n'
            yield f'[DONE]'
            yield f'\n'
