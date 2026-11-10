# 도라미 블로그 아카이브 (구글 노출용 허브 사이트맵)

네이버 블로그 [dorami7](https://m.blog.naver.com/dorami7)의 글을 카테고리별 **모바일 주소**로 정리한 GitHub Pages 사이트입니다.
구글 서치 콘솔에 이 사이트를 등록하면 구글봇이 이 페이지의 링크를 따라 네이버 블로그 글을 수집합니다.

## 구성
| 파일 | 역할 |
|---|---|
| `config.json` | 블로그 ID, 사이트 제목, 사이트 주소, 구글 인증 코드 |
| `scripts/update.py` | 글 목록 수집 → `index.html`, `category/*.html`, `sitemap.xml`, `robots.txt` 생성 |
| `data/posts.json` | 수집한 글 목록 (자동 생성) |
| `.github/workflows/update.yml` | 6시간마다 RSS 확인 후 새 글 자동 추가 |

## 설치 순서
1. **저장소 만들기**: GitHub에서 `내아이디.github.io` 이름으로 공개(Public) 저장소를 만듭니다.
2. **파일 올리기**: 이 폴더의 파일을 모두 업로드합니다. `.github` 폴더도 포함해야 합니다.
   웹 업로드에서 숨김 폴더가 안 보이면 GitHub Desktop이나 `git push`를 사용하세요.
3. **config.json 수정**: `site_url`을 `https://내아이디.github.io`로 바꿉니다.
4. **Actions 권한 켜기**: Settings → Actions → General → Workflow permissions → **Read and write permissions** 선택 → Save.
5. **전체 글 수집 (최초 1회)**: Actions 탭 → "블로그 새 글 자동 업데이트" → **Run workflow** → `backfill` 체크 → 실행.
   글이 3천 개 이상이라 몇 분 걸립니다.
6. **Pages 켜기**: Settings → Pages → Source: *Deploy from a branch* → Branch: `main` / `(root)` → Save.
   몇 분 뒤 `https://내아이디.github.io`에서 확인됩니다.

## 구글 서치 콘솔 등록
1. [Google Search Console](https://search.google.com/search-console) → 속성 추가 → **URL 접두어**에 `https://내아이디.github.io/` 입력.
2. 인증 방법에서 **HTML 태그**를 고르고 `content="..."` 안의 값만 복사해 `config.json`의 `google_site_verification`에 붙여넣습니다.
3. Actions에서 Run workflow(backfill 체크 없이)를 한 번 실행해 페이지에 반영한 뒤, 서치 콘솔에서 **확인**을 누릅니다.
4. 왼쪽 메뉴 **Sitemaps**에 `sitemap.xml` 제출 → **URL 검사**에 메인 주소를 넣고 **색인 생성 요청**.

## 이후 자동 동작
- 6시간마다 네이버 RSS(`rss.blog.naver.com/dorami7.xml`)를 확인해 새 글을 해당 카테고리에 추가합니다.
- 카테고리 이름이 바뀌었거나 목록이 어긋나면 backfill 체크 후 다시 실행하면 전체가 새로 정리됩니다.

## 로컬에서 실행 (선택)
```bash
python scripts/update.py --backfill   # 전체 수집
python scripts/update.py              # 새 글만
python scripts/update.py --build-only # 페이지만 다시 생성
```
