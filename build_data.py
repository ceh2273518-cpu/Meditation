#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CHOI 대시보드 데이터 빌드
  docs/research/ 조사 산출물 + fixtures/ 실측 결과  →  dashboard/data.json + data.js

data.js 를 함께 만드는 이유:
  브라우저는 file:// 에서 fetch() 를 차단한다. <script src> 는 차단하지 않는다.
  따라서 data.js 가 있으면 index.html 을 **더블클릭만으로** 열 수 있다.
  data.json 은 서버 모드와 다른 도구(파이썬·엑셀)용으로 함께 남긴다.

실행:  python dashboard/build_data.py        (프로젝트 루트에서)
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = os.path.join(ROOT, 'docs', 'research')
DASH = os.path.join(ROOT, 'dashboard')
FIX = os.path.join(ROOT, 'fixtures')


def load_experts():
    """docs/research/P2_프로그램명_전문가인덱스.md → 유형·프로그램명·이름·소속·자격·연락처 행 리스트.

    원본은 마크다운 표라 코드 없이 못 고치지만(P2.md 자체를 편집), '표 안의
    프로그램명/이름/전문가 정보'라는 단순한 구조만 걷어내는 얕은 파서라 P2.md
    서식이 유지되는 한 안전하다.
    """
    path = os.path.join(R, 'P2_프로그램명_전문가인덱스.md')
    if not os.path.exists(path):
        print(f"  ! 없음: {path} (전문가 풀 탭이 비어 보입니다)")
        return []
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    def clean(text):
        text = text.strip()
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', text)
        return text.replace('**', '').strip()

    def parse_info(info):
        parts = {'소속': '-', '자격': '-', '연락처': '-'}
        for seg in info.split('<br>'):
            seg = seg.strip()
            for label in parts:
                prefix = f'＊{label}:'
                if seg.startswith(prefix):
                    parts[label] = seg[len(prefix):].strip()
        return parts

    rows = []
    current_type = None
    in_table = False
    last_program = None
    for raw in lines:
        line = raw.rstrip('\n')
        if line.startswith('## '):
            heading = line[3:].strip()
            in_table = not heading.startswith('룩업')
            current_type = heading.split('(')[0].strip() if in_table else None
            last_program = None
            continue
        if not in_table or not line.startswith('|') or '---' in line:
            continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        if len(cells) < 3 or cells[0] == '프로그램명':
            continue
        program = clean(cells[0])
        if program:
            last_program = program
        else:
            program = last_program
        info = parse_info(cells[2])
        rows.append({
            'type': current_type, 'program': program, 'name': clean(cells[1]),
            'affiliation': info['소속'], 'qualification': info['자격'], 'contact': info['연락처'],
        })
    return rows


def load(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        if default is None:
            print(f"  ! 없음: {path}")
        return default


def build():
    s1 = load(os.path.join(R, '_raw_synthesis1.json'), {})
    s2 = load(os.path.join(R, '_raw_synthesis2.json'), {})
    raw1 = load(os.path.join(R, '_raw_survey1.json'), [])
    hits = load(os.path.join(FIX, 'keyword_hit_report.json'), {})

    out = {'generated_at': '2026-08-29', 'project': 'CHOI'}

    # ── 채널 (실측) ──
    channels = []
    for v in raw1:
        if isinstance(v, dict) and v.get('channels') and 'access_method' in (v['channels'][0] or {}):
            for c in v['channels']:
                channels.append({
                    'cluster': v.get('cluster'), 'name': c.get('name'), 'url': c.get('url'),
                    'access': c.get('access_method'), 'priority': c.get('priority'),
                    'attachment': (c.get('attachment_format') or '')[:120],
                    'tos': (c.get('tos_note') or '')[:160],
                    'fetch': (c.get('fetch_result') or '')[:120],
                })
    out['channels'] = channels

    # ── 우선순위 채널 ──
    out['priority_channels'] = [{
        'rank': c['rank'], 'name': c['name'], 'url': c.get('url', ''), 'access': c.get('access_method'),
        'effort': c.get('effort'), 'coverage': (c.get('coverage') or '')[:220],
        'rationale': (c.get('rationale') or '')[:400], 'blockers': (c.get('blockers') or '')[:400],
    } for c in s1.get('priority_channels', [])]

    # ── 공고 사례 (골든셋 후보) ──
    programs = []
    for v in raw1:
        if isinstance(v, dict) and v.get('programs'):
            for p in v['programs']:
                programs.append({
                    'name': p.get('name'), 'agency': p.get('agency'), 'budget': p.get('budget'),
                    'period': p.get('period'), 'target': p.get('target'), 'url': p.get('url'),
                    'relevance': (p.get('relevance_to_meditation') or '')[:200],
                    'topic': (v.get('topic') or '')[:40],
                })
    out['programs'] = programs

    # ── 공공데이터셋 (2차 조사) ──
    datasets = []
    j2 = os.path.join(R, '_raw_datasets2.json')
    cached = load(j2, None)
    if cached:
        datasets = cached
    else:
        # 최초 1회는 워크플로 journal 에서 추출해 캐시로 남긴다
        jpath = os.environ.get('CHOI_WF2_JOURNAL', '')
        if jpath and os.path.exists(jpath):
            for line in open(jpath, encoding='utf-8'):
                d = json.loads(line)
                v = d.get('result')
                if isinstance(v, dict) and v.get('datasets'):
                    for x in v['datasets']:
                        datasets.append({
                            'name': x.get('name'), 'id': x.get('dataset_id'), 'provider': x.get('provider'),
                            'type': x.get('data_type'), 'commercial': x.get('commercial_use'),
                            'license': (x.get('license_note') or '')[:120],
                            'use_case': (x.get('use_case_for_choi') or '')[:200],
                            'category': (v.get('category') or '')[:40], 'url': x.get('url'),
                            'confidence': x.get('confidence'),
                        })
            if datasets:
                json.dump(datasets, open(j2, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    out['datasets'] = datasets

    # ── 전문가 풀 (프로그램명 → 섭외 가능한 전문가) ──
    out['experts'] = load_experts()

    # 키워드는 **정본(config/keywords.yaml)** 에서 읽는다.
    # 예전에는 조사 시점 스냅샷(_raw_synthesis1.json)을 읽어, 사전을 증설해도
    # 화면이 계속 「284」를 보여줬다(실측 2026-08-31 — 실제는 363어였다).
    try:
        sys.path.insert(0, os.path.join(ROOT, 'src'))
        from choi import config as _cfg
        kw_live = _cfg.yaml_config('keywords') or {}
        out['keywords'] = {k: [str(x) for x in v]
                          for k, v in kw_live.items() if isinstance(v, list)}
        kg = _cfg.yaml_config('keywords_general') or {}
        out['keywords_general'] = {k: [str(x) for x in v]
                                   for k, v in kg.items() if isinstance(v, list)}
    except Exception as e:
        print(f'  ! keywords.yaml 읽기 실패({type(e).__name__}) — 조사 스냅샷 사용')
        out['keywords'] = s1.get('keyword_dictionary', {})

    # ── API 실측 ──
    g2b = hits.get('g2b용역(최근3일 500건)', {})
    biz = hits.get('bizinfo(최근500건 제목)', {})
    ks = hits.get('kstartup(최근500건 전문)', {})
    sub = hits.get('subsidy(2026, 300건 표본)', {})
    out['api_verification'] = {
        'verified_at': '2026-08-29',
        'apis': [
            {'name': '나라장터 용역', 'endpoint': 'apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch',
             'status': 200, 'kind': '공고', 'sample': 500, 'total': g2b.get('total'),
             'hits': g2b.get('hits', {}), 'samples': g2b.get('samples', []), 'license': '제한없음'},
            {'name': '기업마당', 'endpoint': 'apis.data.go.kr/1421000/bizinfo/pblancBsnsService',
             'status': 200, 'kind': '공고', 'sample': 500, 'total': None,
             'hits': biz.get('hits', {}), 'samples': biz.get('samples', []), 'license': 'KOGL 제3유형 (변경금지)'},
            {'name': 'K-Startup', 'endpoint': 'apis.data.go.kr/B552735/kisedKstartupService01/getAnnouncementInformation01',
             'status': 200, 'kind': '공고', 'sample': 500, 'total': ks.get('total'),
             'hits': ks.get('hits', {}), 'samples': [], 'license': '제한없음'},
            {'name': '국고보조금', 'endpoint': 'apis.data.go.kr/1051000/MoefOpenAPI2025/T_OPD_ASBS_PBNS_UNITY',
             'status': 200, 'kind': '예산편성(공고 아님)', 'sample': 300, 'total': sub.get('totalCount_2026'),
             'hits': sub.get('hits', {}), 'samples': [], 'license': '제한없음'},
        ]
    }

    out['narrative'] = {
        'executive_summary': s1.get('executive_summary', ''),
        'facility_funding': s1.get('facility_funding_summary', ''),
        'market': s1.get('market_summary', ''),
        'hwp_risk': s1.get('hwp_risk_assessment', ''),
        'api_verdict': s2.get('api_verdict', ''),
        'data_strategy_summary': s2.get('executive_summary', ''),
    }
    out['license_warnings'] = s2.get('license_warnings', [])
    out['collection_steps'] = s1.get('collection_steps', [])
    out['ingest_steps'] = s2.get('ingest_steps', [])
    out['pms_model'] = s2.get('pms_data_model', [])
    out['open_questions'] = (s1.get('open_questions', []) + s2.get('open_questions', []))
    return out


def write(out):
    js_path = os.path.join(DASH, 'data.js')
    json_path = os.path.join(DASH, 'data.json')
    payload = json.dumps(out, ensure_ascii=False, separators=(',', ':'))

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    with open(js_path, 'w', encoding='utf-8') as f:
        f.write('/* 자동 생성 — build_data.py. 직접 수정하지 마세요. */\n')
        f.write('window.CHOI_DATA = ')
        f.write(payload)
        f.write(';\n')

    print(f"  data.json  {os.path.getsize(json_path):>9,} bytes")
    print(f"  data.js    {os.path.getsize(js_path):>9,} bytes  (file:// 더블클릭 지원)")
    for k in ('channels', 'priority_channels', 'programs', 'datasets', 'experts',
              'license_warnings', 'collection_steps', 'ingest_steps', 'pms_model', 'open_questions'):
        print(f"    {k:20s} {len(out.get(k, []))}")
    kw = sum(len(v) for v in out.get('keywords', {}).values())
    print(f"    {'keywords':20s} {kw}")


if __name__ == '__main__':
    print("CHOI 대시보드 데이터 빌드")
    write(build())
    print("\n완료. dashboard/index.html 을 더블클릭하거나,")
    print("     python -m http.server 8099 --directory dashboard 로 여세요.")
