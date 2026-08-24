# AFART 실적 대시보드 (예시)

기획 단계에서 개발팀과 커뮤니케이션하기 위해, `data/raw_query.csv` 원본 실적 데이터를 그대로 붙여서 만든 프로토타입입니다.
실제 화면 배치·데이터 매핑 기준 문서는 별도로 공유된 배치도(Artifact)를 참고하세요.

## 실행

```bash
npm install
npm run dev
```

`data/raw_query.csv`를 빌드 시점에 읽어 `getStaticProps`에서 집계하므로 별도 DB 연결이 필요 없습니다.

## 이 예시에 없는 것

raw 데이터에 없는 값은 만들어내지 않고 화면에서도 안내 배너/카드로 명시했습니다.

- 매니저별 실적 (담당 매니저 컬럼 없음 → 딜러 기준으로 대체)
- G1~G5 그룹별 배정 회원수 (딜러유형 정보 없음)
- 지급대기 / 가입취소 전환 리스트, 갱신 건, 비견(비교견적완료) 퍼널 (상태 이력 데이터 없음)
- 목표매출 달성률, 실시간 랭킹, 인센티브 계산 (정책/목표값 데이터 없음)

## 배포 (Vercel)

1. 이 저장소를 GitHub에 push
2. Vercel → New Project → 이 저장소 import
3. **Root Directory**를 `afart-dashboard-demo`로 지정 (모노레포 내 하위 폴더이기 때문)
4. Build Command / Output Directory는 기본값(Next.js 자동 감지) 그대로 두면 됩니다
