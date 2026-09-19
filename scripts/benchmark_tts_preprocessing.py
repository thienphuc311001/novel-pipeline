"""Offline benchmark: python scripts/benchmark_tts_preprocessing.py --size-mb 10.

Size is UTF-8 input MiB, RSS is process peak (including input and interpreter).
No wall-clock threshold is imposed on CI. Each size should use a fresh process.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cleaning.tts_text_preprocessor import preprocess_with_diagnostics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--size-mb', type=int, choices=(1, 10, 50), required=True)
    args = parser.parse_args()
    sample = 'Ngươi là ai?Ta không biết..... “Hắn sống!”Lâm hét. Giá 3.14, lúc 08:30:15.<br>\n\n'
    block = sample.encode('utf-8')
    target = args.size_mb * 1024 * 1024
    data = (block * (target // len(block))) + b' ' * (target % len(block))
    text = data.decode('utf-8')
    del data
    started = time.perf_counter()
    result = preprocess_with_diagnostics(text)
    elapsed = time.perf_counter() - started
    status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines())
    peak_rss = int(status['VmHWM'].split()[0]) / 1024
    print(json.dumps({'input_mib': args.size_mb, 'input_chars': len(text),
                      'output_chars': len(result.text), 'seconds': round(elapsed, 3),
                      'peak_rss_mib': round(peak_rss, 1)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
