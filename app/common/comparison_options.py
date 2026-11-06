"""Comparison policies shared by both tools (without Qt dependencies)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ComparisonOptions:
    # Body mode deliberately retains the original character whitelist/deduplication.
    mode: str = 'body'
    ignore_spaces: bool = True
    ignore_line_breaks: bool = True
    ignore_case: bool = True
    ignore_symbols: bool = True

    def __post_init__(self):
        if self.mode not in ('body', 'strict', 'custom'):
            raise ValueError(f'Unknown comparison mode: {self.mode}')
        # Presets cannot accidentally become partial/custom policies.
        if self.mode != 'custom':
            for field in ('ignore_spaces', 'ignore_line_breaks', 'ignore_case', 'ignore_symbols'):
                object.__setattr__(self, field, self.mode == 'body')

    @classmethod
    def strict(cls):
        return cls(mode='strict')

    @property
    def label(self):
        return {'body': '본문', 'strict': '엄격', 'custom': '사용자 설정'}[self.mode]

    @property
    def description(self):
        if self.mode == 'body':
            return '기존 방식: 공백·줄바꿈·대소문자를 무시하고 기존 문자 필터를 적용합니다. 일부 문장부호는 비교합니다.'
        if self.mode == 'strict':
            return '공백·줄바꿈·대소문자·특수문자를 모두 포함하여 추출된 텍스트를 비교합니다.'
        items = [('공백', self.ignore_spaces), ('줄바꿈', self.ignore_line_breaks),
                 ('대소문자', self.ignore_case), ('특수문자', self.ignore_symbols)]
        return ' / '.join(f'{name}: {"무시" if ignored else "비교"}' for name, ignored in items)


def visible_whitespace(text):
    """Make otherwise invisible differences readable in the result list."""
    return (text.replace('\r', '␍').replace('\n', '↵')
            .replace('\t', '⇥').replace(' ', '␠').replace('\u00a0', '⍽'))
